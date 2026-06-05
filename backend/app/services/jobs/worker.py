from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.logging_config import get_logger, log_event
from app.models import AnalysisJob
from app.services.agent.workflow import AgentWorkflow, enrich_risks_with_llm
from app.services.seed import seed_memories, seed_rules

logger = get_logger("fxpg.jobs")
_executor = ThreadPoolExecutor(max_workers=settings.job_workers)


def create_job(db: Session, project_id: str) -> AnalysisJob:
    job = AnalysisJob(project_id=project_id, status="queued", progress_pct=0, current_step="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def enqueue_analysis(job_id: str, project_id: str) -> None:
    _executor.submit(_run_job, job_id, project_id)


def _run_job(job_id: str, project_id: str) -> None:
    db = SessionLocal()
    job = db.get(AnalysisJob, job_id)
    if not job:
        db.close()
        return
    try:
        job.status = "running"
        job.started_at = job.started_at or datetime.utcnow()
        db.commit()

        seed_rules(db)
        seed_memories(db)

        def on_progress(step: str, pct: int) -> None:
            j = db.get(AnalysisJob, job_id)
            if j:
                j.current_step = step
                j.progress_pct = pct
                db.commit()

        AgentWorkflow(db, project_id, progress_callback=on_progress).run()

        import asyncio

        asyncio.run(enrich_risks_with_llm(db, project_id))

        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = "completed"
            job.progress_pct = 100
            job.current_step = "completed"
            job.finished_at = datetime.utcnow()
            db.commit()
        log_event(logger, "job.completed", job_id=job_id, project_id=project_id)
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
