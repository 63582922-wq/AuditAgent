from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.exceptions import FXPGError
from app.models import AnalysisJob, FileRecord, Project
from app.services.jobs.worker import create_job, enqueue_harness
from app.services.meeting_service import get_meeting


def start_harness_job(
    db: Session,
    project_id: str,
    meeting_id: str,
    *,
    skip_orchestrator: bool = False,
) -> tuple[AnalysisJob, bool]:
    """启动异步 Harness（单个子会议）。返回 (job, created)。"""
    get_meeting(db, project_id, meeting_id)
    running = (
        db.query(AnalysisJob)
        .filter_by(project_id=project_id, meeting_id=meeting_id)
        .filter(AnalysisJob.status.in_(["queued", "running"]))
        .first()
    )
    if running:
        return running, False

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if db.query(FileRecord).filter_by(project_id=project_id, meeting_id=meeting_id).count() == 0:
        raise FXPGError("请先为该子会议上传统计资料", code="NO_FILES", status=400)

    job = create_job(db, project_id, meeting_id=meeting_id)
    meeting = get_meeting(db, project_id, meeting_id)
    meeting.status = "planning"
    state = dict(meeting.state_json or {})
    state["execution_mode"] = "compliance_harness"
    state["agent_domain"] = state.get("agent_domain") or "compliance"
    meeting.state_json = state
    project.status = "active"
    db.commit()
    enqueue_harness(job.id, project_id, meeting_id, skip_orchestrator=skip_orchestrator)
    return job, True
