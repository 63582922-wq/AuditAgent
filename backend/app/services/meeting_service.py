from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import FXPGError
from app.models import (
    AgentRunLog,
    AnalysisJob,
    ExtractedEntity,
    FileRecord,
    Meeting,
    Output,
    ParsedDocument,
    Project,
    RecordLink,
    ReviewRecord,
    Risk,
)
from app.services.output_scope import primary_output_count
from app.services.domain.compliance.constants import PRIMARY_DELIVERABLE_TYPES


def _normalize_code(code: str) -> str:
    return re.sub(r"\s+", "", (code or "").strip().upper())[:64]


def meeting_to_dict(m: Meeting, *, counts: bool = False, db: Session | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": m.id,
        "project_id": m.project_id,
        "meeting_code": m.meeting_code,
        "meeting_title": m.meeting_title,
        "observation_type": m.observation_type,
        "meeting_type": m.meeting_type,
        "meeting_date": m.meeting_date,
        "status": m.status,
        "summary": m.summary,
        "state_json": m.state_json,
        "deliverable_json": m.deliverable_json,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
        "last_run_at": m.last_run_at,
    }
    if counts and db is not None:
        out["file_count"] = db.query(FileRecord).filter_by(meeting_id=m.id).count()
        out["risk_count"] = db.query(Risk).filter_by(meeting_id=m.id).count()
        out["output_count"] = primary_output_count(db, meeting_id=m.id)
    return out


def get_meeting(db: Session, project_id: str, meeting_id: str) -> Meeting:
    m = db.query(Meeting).filter_by(id=meeting_id, project_id=project_id).first()
    if not m:
        raise FXPGError("子会议不存在", code="MEETING_NOT_FOUND", status=404)
    return m


_DELIVERY_GATE_LABELS = {
    "evidence_gate": "关键事实证据存在冲突、缺失或待核实",
    "evaluation_gate": "自动评估存在严重失败",
    "template_gate": "143 列固定模板尚未达到正式交付质量门禁",
    "primary_deliverables": "主交付物不完整（需固定模板 Excel 和 ZIP 归档）",
}


def delivery_acceptance_gate(db: Session, meeting: Meeting) -> dict[str, Any]:
    """Return the one formal-delivery gate used by API, UI and the Main Agent.

    Preview artifacts are useful while facts or handoff fields remain unresolved,
    but they must never be accepted as the official delivery.
    """
    state = dict(meeting.state_json or {})
    deliverable = dict(meeting.deliverable_json or state.get("deliverable") or {})
    blocks: list[dict[str, Any]] = []
    for key in ("evidence_gate", "evaluation_gate", "template_gate"):
        gate = deliverable.get(key)
        if not isinstance(gate, dict) and key == "evidence_gate":
            gate = state.get("evidence_gate")
        if isinstance(gate, dict) and gate.get("blocked"):
            blocks.append({"code": key, "detail": gate})

    template_quality = deliverable.get("template_quality")
    if not isinstance(template_quality, dict) or template_quality.get("status") != "pass":
        if not any(item["code"] == "template_gate" for item in blocks):
            blocks.append(
                {
                    "code": "template_gate",
                    "detail": {
                        "blocked": True,
                        "reason": "template_quality_not_passed" if isinstance(template_quality, dict) else "template_quality_missing",
                        "status": template_quality.get("status") if isinstance(template_quality, dict) else None,
                    },
                }
            )

    output_types = {
        row[0]
        for row in db.query(Output.output_type)
        .filter_by(project_id=meeting.project_id, meeting_id=meeting.id)
        .filter(Output.output_type.in_(PRIMARY_DELIVERABLE_TYPES))
        .all()
    }
    missing_outputs = [item for item in PRIMARY_DELIVERABLE_TYPES if item not in output_types]
    if missing_outputs:
        blocks.append(
            {
                "code": "primary_deliverables",
                "detail": {"blocked": True, "reason": "required_outputs_missing", "missing_output_types": missing_outputs},
            }
        )

    messages = [_DELIVERY_GATE_LABELS[item["code"]] for item in blocks]
    return {
        "blocked": bool(blocks),
        "reason": "formal_delivery_ready" if not blocks else "formal_delivery_blocked",
        "blocks": blocks,
        "message": "；".join(messages) if messages else "正式交付门禁已通过",
    }


def list_meetings(db: Session, project_id: str) -> list[Meeting]:
    if not db.get(Project, project_id):
        raise FXPGError("项目不存在", code="PROJECT_NOT_FOUND", status=404)
    meetings = db.query(Meeting).filter_by(project_id=project_id).order_by(Meeting.created_at.desc()).all()
    if len(meetings) <= 1:
        return meetings
    return [m for m in meetings if not _is_empty_default_meeting(db, m)]


def _is_empty_default_meeting(db: Session, meeting: Meeting) -> bool:
    if _normalize_code(meeting.meeting_code) != "DEFAULT":
        return False
    filters = {"project_id": meeting.project_id, "meeting_id": meeting.id}
    return (
        db.query(FileRecord).filter_by(**filters).count() == 0
        and db.query(Risk).filter_by(**filters).count() == 0
        and db.query(Output).filter_by(**filters).count() == 0
        and db.query(ParsedDocument).filter_by(**filters).count() == 0
    )


def create_meeting(
    db: Session,
    project_id: str,
    *,
    meeting_code: str,
    meeting_title: Optional[str] = None,
    observation_type: Optional[str] = None,
    meeting_type: Optional[str] = None,
    meeting_date: Optional[str] = None,
) -> Meeting:
    project = db.get(Project, project_id)
    if not project:
        raise FXPGError("项目不存在", code="PROJECT_NOT_FOUND", status=404)
    code = _normalize_code(meeting_code)
    if not code:
        raise FXPGError("会议编码不能为空", code="INVALID_MEETING_CODE", status=400)
    exists = db.query(Meeting).filter_by(project_id=project_id, meeting_code=code).first()
    if exists:
        raise FXPGError(f"会议编码 {code} 已存在", code="MEETING_CODE_EXISTS", status=400)

    meeting = Meeting(
        project_id=project_id,
        meeting_code=code,
        meeting_title=(meeting_title or "").strip() or None,
        observation_type=(observation_type or "").strip() or None,
        meeting_type=(meeting_type or "").strip() or None,
        meeting_date=(meeting_date or "").strip() or None,
        status="draft",
        state_json={"agent_domain": "compliance", "meeting_case": {"meeting_code": code}},
        deliverable_json={"status": "pending", "comment": ""},
    )
    db.add(meeting)
    if project.status == "created":
        project.status = "active"
    db.commit()
    db.refresh(meeting)
    return meeting


def update_meeting(
    db: Session,
    project_id: str,
    meeting_id: str,
    *,
    meeting_code: Optional[str] = None,
    meeting_title: Optional[str] = None,
    observation_type: Optional[str] = None,
    meeting_type: Optional[str] = None,
    meeting_date: Optional[str] = None,
    summary: Optional[str] = None,
) -> Meeting:
    meeting = get_meeting(db, project_id, meeting_id)
    if meeting_code is not None:
        code = _normalize_code(meeting_code)
        if not code:
            raise FXPGError("会议编码不能为空", code="INVALID_MEETING_CODE", status=400)
        dup = (
            db.query(Meeting)
            .filter(Meeting.project_id == project_id, Meeting.meeting_code == code, Meeting.id != meeting_id)
            .first()
        )
        if dup:
            raise FXPGError(f"会议编码 {code} 已存在", code="MEETING_CODE_EXISTS", status=400)
        meeting.meeting_code = code
        state = dict(meeting.state_json or {})
        mc = dict(state.get("meeting_case") or {})
        mc["meeting_code"] = code
        state["meeting_case"] = mc
        meeting.state_json = state
    if meeting_title is not None:
        meeting.meeting_title = meeting_title.strip() or None
    if observation_type is not None:
        meeting.observation_type = observation_type.strip() or None
    if meeting_type is not None:
        meeting.meeting_type = meeting_type.strip() or None
    if meeting_date is not None:
        meeting.meeting_date = meeting_date.strip() or None
    if summary is not None:
        meeting.summary = summary.strip() or None
    meeting.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(meeting)
    return meeting


def _delete_meeting_storage(project_id: str, meeting_id: str) -> None:
    for sub in ("uploads", "outputs"):
        path = settings.storage_path / sub / project_id / meeting_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def delete_meeting_cascade(db: Session, project_id: str, meeting_id: str) -> None:
    meeting = get_meeting(db, project_id, meeting_id)
    risk_ids = [
        r[0]
        for r in db.query(Risk.id).filter_by(project_id=project_id, meeting_id=meeting_id).all()
    ]
    if risk_ids:
        db.query(ReviewRecord).filter(ReviewRecord.risk_id.in_(risk_ids)).delete(synchronize_session=False)
    db.query(Risk).filter_by(project_id=project_id, meeting_id=meeting_id).delete(synchronize_session=False)
    db.query(ParsedDocument).filter_by(project_id=project_id, meeting_id=meeting_id).delete(synchronize_session=False)
    db.query(ExtractedEntity).filter_by(project_id=project_id, meeting_id=meeting_id).delete(synchronize_session=False)
    db.query(RecordLink).filter_by(project_id=project_id, meeting_id=meeting_id).delete(synchronize_session=False)
    db.query(AgentRunLog).filter_by(project_id=project_id, meeting_id=meeting_id).delete(synchronize_session=False)
    db.query(AnalysisJob).filter_by(project_id=project_id, meeting_id=meeting_id).delete(synchronize_session=False)
    db.query(Output).filter_by(project_id=project_id, meeting_id=meeting_id).delete(synchronize_session=False)
    db.query(FileRecord).filter_by(project_id=project_id, meeting_id=meeting_id).delete(synchronize_session=False)
    db.delete(meeting)
    _delete_meeting_storage(project_id, meeting_id)


def delete_meetings_batch(db: Session, project_id: str, meeting_ids: list[str]) -> int:
    if not meeting_ids:
        return 0
    deleted = 0
    for mid in meeting_ids:
        if db.query(Meeting).filter_by(id=mid, project_id=project_id).first():
            delete_meeting_cascade(db, project_id, mid)
            deleted += 1
    db.commit()
    return deleted


def ensure_default_meeting(db: Session, project_id: str) -> Meeting:
    """旧数据或无子会议时，确保至少有一条 Meeting。"""
    existing = db.query(Meeting).filter_by(project_id=project_id).order_by(Meeting.created_at).first()
    if existing:
        return existing
    project = db.get(Project, project_id)
    if not project:
        raise FXPGError("项目不存在", code="PROJECT_NOT_FOUND", status=404)
    state = project.state_json or {}
    mc = state.get("meeting_case") or {}
    code = _normalize_code(str(mc.get("meeting_code") or "DEFAULT"))
    meeting = Meeting(
        project_id=project_id,
        meeting_code=code,
        meeting_title=project.name,
        status=project.status if project.status not in ("created",) else "draft",
        summary=project.summary,
        state_json=state,
        deliverable_json=state.get("deliverable") or {"status": "pending", "comment": ""},
    )
    db.add(meeting)
    db.flush()
    for model in (FileRecord, Risk, Output, ParsedDocument, ExtractedEntity, RecordLink, AgentRunLog, AnalysisJob):
        db.query(model).filter_by(project_id=project_id, meeting_id=None).update(
            {"meeting_id": meeting.id}, synchronize_session=False
        )
    db.commit()
    db.refresh(meeting)
    return meeting


def accept_meeting_deliverables(db: Session, project_id: str, meeting_id: str) -> Meeting:
    meeting = get_meeting(db, project_id, meeting_id)
    if meeting.status not in ("completed", "needs_review", "deliverable_rejected"):
        raise FXPGError("分析尚未完成，无法验收", code="NOT_READY", status=400)
    gate = delivery_acceptance_gate(db, meeting)
    if gate["blocked"]:
        raise FXPGError(
            f"正式验收已阻断：{gate['message']}。请完成复核、补件或重跑后再验收。",
            code="DELIVERY_GATE_BLOCKED",
            status=409,
        )
    deliverable = dict(meeting.deliverable_json or {})
    deliverable.update(
        {
            "status": "accepted",
            "comment": "",
            "accepted_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    meeting.deliverable_json = deliverable
    state = dict(meeting.state_json or {})
    state["deliverable"] = deliverable
    meeting.state_json = state
    meeting.status = "accepted"
    meeting.updated_at = datetime.now(timezone.utc)
    db.commit()
    sync_project_rollups(db, project_id)
    db.refresh(meeting)
    return meeting


def reject_meeting_deliverables(
    db: Session,
    project_id: str,
    meeting_id: str,
    comment: str,
) -> Meeting:
    meeting = get_meeting(db, project_id, meeting_id)
    if meeting.status not in ("completed", "needs_review", "accepted"):
        raise FXPGError("当前状态不可退回", code="NOT_READY", status=400)
    deliverable = {
        "status": "rejected",
        "comment": comment,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
    }
    meeting.deliverable_json = deliverable
    state = dict(meeting.state_json or {})
    state["deliverable"] = deliverable
    if comment:
        state["deliverable_feedback"] = comment
        plan = dict(state.get("agent_plan") or {})
        plan["deliverable_feedback"] = comment
        state["agent_plan"] = plan
    meeting.state_json = state
    meeting.status = "deliverable_rejected"
    meeting.updated_at = datetime.now(timezone.utc)
    db.commit()
    sync_project_rollups(db, project_id)
    db.refresh(meeting)
    return meeting


def sync_project_rollups(db: Session, project_id: str) -> None:
    """从子会议聚合更新项目摘要态（轻量）。"""
    project = db.get(Project, project_id)
    if not project:
        return
    meetings = db.query(Meeting).filter_by(project_id=project_id).all()
    if not meetings:
        return
    if any(m.status in ("running", "planning", "classifying", "queued") for m in meetings):
        project.status = "active"
    elif all(m.status == "accepted" for m in meetings):
        project.status = "accepted"
    elif any(m.status == "completed" for m in meetings):
        project.status = "completed"
    else:
        project.status = "active"
    db.commit()
