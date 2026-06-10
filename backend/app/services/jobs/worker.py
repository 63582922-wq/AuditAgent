from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.logging_config import get_logger, log_event
from app.models import AnalysisJob
from app.services.agent.runtime import AgentRuntime
from app.services.seed import seed_memories, seed_rules

logger = get_logger("fxpg.jobs")
_executor = ThreadPoolExecutor(max_workers=settings.job_workers)


def create_job(db: Session, project_id: str, scope: str = "full") -> AnalysisJob:
    job = AnalysisJob(
        project_id=project_id,
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


def _run_job(job_id: str, project_id: str, scope: str = "full") -> None:
    db = SessionLocal()
    job = db.get(AnalysisJob, job_id)
    if not job:
        db.close()
        return
    try:
        job.status = "running"
        job.started_at = job.started_at or datetime.utcnow()
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

        result = AgentRuntime(db, project_id, progress_callback=on_progress).run(scope=scope)

        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = "completed"
            job.progress_pct = 100
            job.current_step = result.status if result.status == "needs_review" else "completed"
            job.finished_at = datetime.utcnow()
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
            job.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
