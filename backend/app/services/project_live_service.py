from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AgentRunLog, AnalysisJob, FileRecord, Output, Project, Risk
from app.schemas import ProjectLiveOut
from app.services.meeting_service import get_meeting


def _compact_agent_plan(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    compact = {}
    if isinstance(value.get("reasoning"), str):
        compact["reasoning"] = value["reasoning"]
    if isinstance(value.get("sub_agents"), list):
        compact["sub_agents"] = value["sub_agents"]
    return compact or None


def _compact_execution_graph(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    compact = {}
    if isinstance(value.get("agent_message"), str):
        compact["agent_message"] = value["agent_message"]
    if isinstance(value.get("sub_agents"), list):
        compact["sub_agents"] = value["sub_agents"]
    return compact or None


def _compact_mission(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    compact = {}
    if isinstance(value.get("objective"), str):
        compact["objective"] = value["objective"]
    if isinstance(value.get("registered_agents"), list):
        compact["registered_agents"] = value["registered_agents"]
    return compact or None


def _compact_runtime(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    compact = {}
    if isinstance(value.get("scope"), str):
        compact["scope"] = value["scope"]
    if isinstance(value.get("critic"), dict):
        compact["critic"] = value["critic"]
    if isinstance(value.get("human_gate"), dict):
        compact["human_gate"] = value["human_gate"]
    return compact or None


def _compact_briefs(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    compact = {}
    for key, raw in value.items():
        if not isinstance(raw, dict):
            continue
        item = {}
        if isinstance(raw.get("title"), str):
            item["title"] = raw["title"]
        if isinstance(raw.get("summary"), str):
            item["summary"] = raw["summary"]
        if isinstance(raw.get("tools_used"), list):
            item["tools_used"] = raw["tools_used"]
        if item:
            compact[key] = item
    return compact or None


def _compact_synthesis(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    compact = {}
    if isinstance(value.get("summary"), str):
        compact["summary"] = value["summary"]
    if isinstance(value.get("priority_findings"), list):
        compact["priority_findings"] = value["priority_findings"]
    return compact or None


def compact_live_state(state_json: dict | None, deliverable_json: dict | None = None) -> dict | None:
    state = dict(state_json or {})
    compact = {}
    passthrough_keys = ("execution_mode", "agent_domain", "runtime_live", "meeting_case", "missing_documents")
    for key in passthrough_keys:
        if key in state:
            compact[key] = state[key]

    if agent_plan := _compact_agent_plan(state.get("agent_plan")):
        compact["agent_plan"] = agent_plan
    if execution_graph := _compact_execution_graph(state.get("execution_graph")):
        compact["execution_graph"] = execution_graph
    if mission := _compact_mission(state.get("mission")):
        compact["mission"] = mission
    if runtime := _compact_runtime(state.get("runtime")):
        compact["runtime"] = runtime
    if briefs := _compact_briefs(state.get("sub_agent_briefs")):
        compact["sub_agent_briefs"] = briefs
    if synthesis := _compact_synthesis(state.get("synthesis_brief")):
        compact["synthesis_brief"] = synthesis
    if deliverable_json:
        compact["deliverable"] = deliverable_json
    return compact or None


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


def build_meeting_live(db: Session, project_id: str, meeting_id: str) -> ProjectLiveOut:
    project = _get_project_or_404(db, project_id)
    meeting = get_meeting(db, project_id, meeting_id)
    return ProjectLiveOut(
        id=project.id,
        name=f"{project.name} · {meeting.meeting_code}",
        status=meeting.status,
        summary=meeting.summary or project.summary,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
        state_json=compact_live_state(meeting.state_json, meeting.deliverable_json),
        file_count=db.query(FileRecord).filter_by(meeting_id=meeting_id).count(),
        risk_count=db.query(Risk).filter_by(meeting_id=meeting_id).count(),
        output_count=db.query(Output).filter_by(meeting_id=meeting_id).count(),
    )


def build_project_live(db: Session, project_id: str) -> ProjectLiveOut:
    project = _get_project_or_404(db, project_id)
    return ProjectLiveOut(
        id=project.id,
        name=project.name,
        status=project.status,
        summary=project.summary,
        created_at=project.created_at,
        updated_at=project.updated_at,
        state_json=compact_live_state(project.state_json),
        file_count=db.query(FileRecord).filter_by(project_id=project_id).count(),
        risk_count=db.query(Risk).filter_by(project_id=project_id).count(),
        output_count=db.query(Output).filter_by(project_id=project_id).count(),
    )


def latest_meeting_job(db: Session, project_id: str, meeting_id: str) -> AnalysisJob | None:
    get_meeting(db, project_id, meeting_id)
    return (
        db.query(AnalysisJob)
        .filter_by(project_id=project_id, meeting_id=meeting_id)
        .order_by(AnalysisJob.created_at.desc())
        .first()
    )


def latest_project_job(db: Session, project_id: str) -> AnalysisJob | None:
    _get_project_or_404(db, project_id)
    return (
        db.query(AnalysisJob)
        .filter_by(project_id=project_id, meeting_id=None)
        .order_by(AnalysisJob.created_at.desc())
        .first()
    )


def serialize_logs(rows: list[AgentRunLog]) -> list[dict]:
    return [
        {
            "id": row.id,
            "step": row.step,
            "status": row.status,
            "detail_json": row.detail_json,
            "duration_ms": row.duration_ms,
            "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
        }
        for row in rows
    ]


def list_meeting_logs(db: Session, project_id: str, meeting_id: str) -> list[dict]:
    get_meeting(db, project_id, meeting_id)
    rows = (
        db.query(AgentRunLog)
        .filter_by(project_id=project_id, meeting_id=meeting_id)
        .order_by(AgentRunLog.created_at)
        .all()
    )
    return serialize_logs(rows)


def list_project_logs(db: Session, project_id: str) -> list[dict]:
    _get_project_or_404(db, project_id)
    rows = db.query(AgentRunLog).filter_by(project_id=project_id).order_by(AgentRunLog.created_at).all()
    return serialize_logs(rows)
