from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.logging_config import get_logger, log_event
from app.exceptions import FXPGError
from app.models import AnalysisJob, CaseRun, Meeting, Project
from app.services.agent.agent_trace import AgentTrace
from app.services.agent.runtime import AgentRuntime
from app.services.agent.harness import ComplianceHarness
from app.services.agent.case_run import case_run_for_job, finish_case_run
from app.services.seed import seed_memories, seed_rules

logger = get_logger("fxpg.jobs")
_executor = ThreadPoolExecutor(max_workers=settings.job_workers)


class JobCancelled(Exception):
    """Expected control-flow error used to preserve cancellation as an audit state."""


def _cancel_requested(db: Session, job_id: str) -> bool:
    job = db.get(AnalysisJob, job_id)
    return bool(job and job.status in {"cancel_requested", "cancelled"})


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


def recover_pending_jobs() -> int:
    """Re-enqueue persisted work after a process restart.

    The DB remains the source of truth.  Only queued jobs and clearly stale
    running jobs are reclaimed, preventing a fresh worker from duplicating an
    active run in a healthy process.
    """
    db = SessionLocal()
    try:
        stale_before = datetime.now(timezone.utc) - timedelta(seconds=max(settings.job_recovery_stale_sec, 30))
        jobs = (
            db.query(AnalysisJob)
            .filter(AnalysisJob.status.in_(["queued", "running"]))
            .order_by(AnalysisJob.created_at.asc())
            .all()
        )
        recovered: list[tuple[AnalysisJob, CaseRun | None]] = []
        for job in jobs:
            is_stale = job.status == "running" and (job.started_at is None or job.started_at < stale_before)
            if job.status == "running" and not is_stale:
                continue
            if is_stale:
                job.status = "queued"
                job.current_step = "recovered"
                job.retry_count = int(job.retry_count or 0) + 1
            run = db.query(CaseRun).filter_by(job_id=job.id).order_by(CaseRun.created_at.desc()).first()
            recovered.append((job, run))
        db.commit()
        for job, run in recovered:
            if run and job.meeting_id:
                enqueue_harness(job.id, job.project_id, job.meeting_id)
            else:
                enqueue_analysis(job.id, job.project_id)
        return len(recovered)
    finally:
        db.close()


def _run_job(job_id: str, project_id: str, scope: str = "full") -> None:
    db = SessionLocal()
    job = db.get(AnalysisJob, job_id)
    if not job:
        db.close()
        return
    try:
        if _cancel_requested(db, job_id):
            raise JobCancelled()
        job.status = "running"
        job.started_at = job.started_at or datetime.now(timezone.utc)
        if scope != "full":
            job.current_step = scope
        db.commit()

        seed_rules(db)
        seed_memories(db)

        def on_progress(step: str, pct: int) -> None:
            if _cancel_requested(db, job_id):
                raise JobCancelled()
            j = db.get(AnalysisJob, job_id)
            if j:
                j.current_step = step
                j.progress_pct = pct
                db.commit()

        result = AgentRuntime(
            db, project_id, progress_callback=on_progress, meeting_id=job.meeting_id
        ).run(scope=scope)
        if _cancel_requested(db, job_id):
            raise JobCancelled()

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
    except JobCancelled:
        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = "cancelled"
            job.current_step = "cancelled"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
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
        case_run = case_run_for_job(db, job_id)
        if _cancel_requested(db, job_id):
            raise JobCancelled()
        job.status = "running"
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.current_step = "planning"
        job.progress_pct = 5
        db.commit()

        seed_rules(db)
        seed_memories(db)

        from app.models import Meeting

        def on_progress(step: str, pct: int) -> None:
            if _cancel_requested(db, job_id):
                raise JobCancelled()
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
            case_run_id=case_run.id if case_run else None,
        )
        if _cancel_requested(db, job_id):
            raise JobCancelled()

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
    except JobCancelled:
        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = "cancelled"
            job.current_step = "cancelled"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        case_run = case_run_for_job(db, job_id)
        if case_run:
            finish_case_run(db, case_run, status="cancelled", error="用户取消任务")
        meeting = db.get(Meeting, meeting_id)
        if meeting and meeting.status not in {"completed", "needs_review", "accepted"}:
            meeting.status = "ready"
            state = dict(meeting.state_json or {})
            state["runtime_live"] = {
                "step": "cancelled",
                "pct": 0,
                "updated_at": datetime.now(timezone.utc).isoformat() + "Z",
            }
            meeting.state_json = state
            db.commit()
    except Exception as exc:
        logger.exception("harness.failed job_id=%s", job_id)
        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        case_run = case_run_for_job(db, job_id)
        if case_run:
            finish_case_run(db, case_run, status="failed", error=str(exc))
        err_code = exc.code if isinstance(exc, FXPGError) else "INTERNAL_ERROR"
        try:
            AgentTrace(db, project_id, meeting_id, run_id=case_run.id if case_run else None).log(
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
