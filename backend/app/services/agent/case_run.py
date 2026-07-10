from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import CaseRun, FileRecord
from app.services.agent.prompt_loader import MAIN_AGENT_PROMPT_VERSION


def _now() -> datetime:
    return datetime.now(timezone.utc)


_RUN_TRANSITIONS = {
    "queued": {"running", "cancelled", "failed"},
    "running": {"completed", "needs_review", "accepted", "cancelled", "failed"},
    "needs_review": {"accepted"},
}


def _file_digest(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rules_version() -> str:
    rules_dir = Path(__file__).resolve().parents[3] / "rules"
    digest = sha256()
    for path in sorted(rules_dir.glob("*.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()[:16]}"


def snapshot_case_inputs(db: Session, project_id: str, meeting_id: str) -> dict[str, Any]:
    files = (
        db.query(FileRecord)
        .filter_by(project_id=project_id, meeting_id=meeting_id)
        .order_by(FileRecord.file_name.asc())
        .all()
    )
    items: list[dict[str, Any]] = []
    for item in files:
        path = Path(item.storage_path)
        stat = path.stat() if path.exists() else None
        items.append(
            {
                "file_id": item.id,
                "file_name": item.file_name,
                "file_type": item.file_type,
                "document_category": item.document_category,
                "size_bytes": stat.st_size if stat else None,
                "modified_ns": stat.st_mtime_ns if stat else None,
                "sha256": _file_digest(path),
            }
        )
    return {"file_count": len(items), "files": items}


def runtime_snapshot() -> dict[str, Any]:
    return {
        "text_model": settings.text_model,
        "vision_model": settings.vision_model,
        "agent_execution_mode": settings.agent_execution_mode,
        "vision_high_risk_min_passes": settings.vision_high_risk_min_passes,
        "vision_max_workers": settings.vision_max_workers,
        "prompt_version": MAIN_AGENT_PROMPT_VERSION,
        "rule_version": _rules_version(),
    }


def create_case_run(
    db: Session,
    project_id: str,
    meeting_id: str,
    *,
    job_id: str | None = None,
    run_kind: str = "full",
    execution_mode: str = "compliance_harness",
) -> CaseRun:
    run = CaseRun(
        project_id=project_id,
        meeting_id=meeting_id,
        job_id=job_id,
        run_kind=run_kind,
        execution_mode=execution_mode,
        status="queued",
        input_snapshot_json=snapshot_case_inputs(db, project_id, meeting_id),
        runtime_snapshot_json=runtime_snapshot(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def latest_case_run(db: Session, project_id: str, meeting_id: str) -> CaseRun | None:
    return (
        db.query(CaseRun)
        .filter_by(project_id=project_id, meeting_id=meeting_id)
        .order_by(CaseRun.created_at.desc())
        .first()
    )


def case_run_for_job(db: Session, job_id: str) -> CaseRun | None:
    return db.query(CaseRun).filter_by(job_id=job_id).order_by(CaseRun.created_at.desc()).first()


def mark_case_run_started(db: Session, run: CaseRun) -> CaseRun:
    transition_case_run(db, run, "running")
    run.started_at = run.started_at or _now()
    db.commit()
    return run


def transition_case_run(db: Session, run: CaseRun, target: str) -> CaseRun:
    if run.status == target:
        return run
    allowed = _RUN_TRANSITIONS.get(run.status, set())
    if target not in allowed:
        raise ValueError(f"invalid CaseRun transition: {run.status} -> {target}")
    run.status = target
    return run


def finish_case_run(
    db: Session,
    run: CaseRun,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> CaseRun:
    transition_case_run(db, run, status)
    run.result_json = result or run.result_json
    run.error_message = error
    run.finished_at = _now()
    db.commit()
    return run
