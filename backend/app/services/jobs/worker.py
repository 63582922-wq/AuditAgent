from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.logging_config import get_logger, log_event
from app.exceptions import FXPGError
from app.models import AnalysisJob, Meeting, Project
from app.services.agent.agent_trace import AgentTrace
from app.services.agent.runtime import AgentRuntime
from app.services.agent.harness import ComplianceHarness
from app.services.seed import seed_memories, seed_rules

logger = get_logger("fxpg.jobs")
_executor = ThreadPoolExecutor(max_workers=settings.job_workers)


def get_executor() -> ThreadPoolExecutor:
    """Expose the module-level executor so the FastAPI lifespan can shut it down."""
    return _executor


def create_job(db: Session, project_id: str, scope: str = "full", meeting_id: str | None = None) -> AnalysisJob:
    job = AnalysisJob(
        project_id=project_id,
        meeting_id=meeting_id,
        status="queued",
        progress_pct=0,
        current_step="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    # scope 暂存于 job error_message 字段不合适；写入 project state 由 API 设置
    return job


def enqueue_analysis(job_id: str, project_id: str, scope: str = "full") -> None:
    _executor.submit(_run_job, job_id, project_id, scope)


def enqueue_harness(
    job_id: str,
    project_id: str,
    meeting_id: str,
    *,
    skip_orchestrator: bool = False,
) -> None:
    _executor.submit(_run_harness_job, job_id, project_id, meeting_id, skip_orchestrator)


def _run_job(job_id: str, project_id: str, scope: str = "full") -> None:
    db = SessionLocal()
    job = db.get(AnalysisJob, job_id)
    if not job:
        db.close()
        return
    try:
        job.status = "running"
        job.started_at = job.started_at or datetime.now(timezone.utc)
        if scope != "full":
            job.current_step = scope
        db.commit()

        seed_rules(db)
        seed_memories(db)

        def on_progress(step: str, pct: int) -> None:
            j = db.get(AnalysisJob, job_id)
            if j:
                j.current_step = step
                j.progress_pct = pct
                db.commit()

        result = AgentRuntime(
            db, project_id, progress_callback=on_progress, meeting_id=job.meeting_id
        ).run(scope=scope)

        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = "completed"
            job.progress_pct = 100
            job.current_step = result.status if result.status == "needs_review" else "completed"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        log_event(
            logger,
            "job.completed",
            job_id=job_id,
            project_id=project_id,
            scope=scope,
            status=result.status,
        )
    except Exception as exc:
        logger.exception("job.failed job_id=%s", job_id)
        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def _run_harness_job(
    job_id: str,
    project_id: str,
    meeting_id: str,
    skip_orchestrator: bool = False,
) -> None:
    db = SessionLocal()
    job = db.get(AnalysisJob, job_id)
    if not job:
        db.close()
        return
    try:
        job.status = "running"
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.current_step = "planning"
        job.progress_pct = 5
        db.commit()

        seed_rules(db)
        seed_memories(db)

        from app.models import Meeting

        def on_progress(step: str, pct: int) -> None:
            j = db.get(AnalysisJob, job_id)
            if j:
                j.current_step = step
                j.progress_pct = max(j.progress_pct or 0, pct)
                db.commit()
            meeting = db.get(Meeting, meeting_id)
            if meeting:
                meeting.status = step
                st = dict(meeting.state_json or {})
                st["runtime_live"] = {
                    "step": step,
                    "pct": max((st.get("runtime_live") or {}).get("pct", 0), pct),
                    "updated_at": datetime.now(timezone.utc).isoformat() + "Z",
                }
                meeting.state_json = st
                db.commit()

        result = ComplianceHarness(db, progress_callback=on_progress).run(
            project_id,
            meeting_id,
            skip_orchestrator=skip_orchestrator,
        )

        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = "completed"
            job.progress_pct = 100
            job.current_step = "completed" if result.status == "completed" else result.status
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        log_event(
            logger,
            "harness.completed",
            job_id=job_id,
            project_id=project_id,
            status=result.status,
            finding_count=result.finding_count,
        )
    except Exception as exc:
        logger.exception("harness.failed job_id=%s", job_id)
        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        err_code = exc.code if isinstance(exc, FXPGError) else "INTERNAL_ERROR"
        try:
            AgentTrace(db, project_id, meeting_id).log(
                "harness",
                "failed",
                kind="runtime",
                name="ComplianceHarness",
                message=str(exc),
                detail={"error": str(exc), "code": err_code, "job_id": job_id},
            )
        except Exception:
            logger.exception("harness.trace_failed job_id=%s", job_id)
        project = db.get(Project, project_id)
        meeting = db.get(Meeting, meeting_id)
        if meeting and meeting.status not in ("completed", "needs_review", "accepted"):
            meeting.status = "failed"
            st = dict(meeting.state_json or {})
            st["runtime_live"] = {
                "step": "failed",
                "pct": 0,
                "error": str(exc),
                "updated_at": datetime.now(timezone.utc).isoformat() + "Z",
            }
            meeting.state_json = st
            db.commit()
    finally:
        db.close()
