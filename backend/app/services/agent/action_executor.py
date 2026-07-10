from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.exceptions import FXPGError
from app.models import AgentActionProposal, AgentRunLog, LearningProposal
from app.services.agent.agent_trace import trace_code_location
from app.services.harness_job_service import start_harness_job
from app.services.meeting_service import accept_meeting_deliverables, reject_meeting_deliverables


def _result(
    proposal: AgentActionProposal,
    *,
    status: str,
    message: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "proposal_id": proposal.id,
        "action_id": proposal.action_id,
        "status": status,
        "message": message,
        "job_id": job_id,
    }


def _mark_executed(db: Session, proposal: AgentActionProposal, result: dict[str, Any]) -> dict[str, Any]:
    proposal.status = "executed"
    proposal.result_json = result
    proposal.executed_at = datetime.now(timezone.utc)
    db.add(
        AgentRunLog(
            project_id=proposal.project_id,
            meeting_id=proposal.meeting_id,
            step="agent_action_execute",
            status="completed",
            detail_json={
                "kind": "tool",
                "name": f"审批执行 {proposal.action_id}",
                "message": result.get("message") or result.get("status"),
                "proposal_id": proposal.id,
                "action_id": proposal.action_id,
                "result": result,
                "code_location": trace_code_location(),
            },
        )
    )
    db.commit()
    return result


def approve_agent_action(
    db: Session,
    proposal_id: str,
    *,
    comment: str | None = None,
) -> dict[str, Any]:
    proposal = db.get(AgentActionProposal, proposal_id)
    if not proposal:
        raise HTTPException(404, "动作不存在")
    if proposal.status != "pending":
        raise FXPGError("动作已处理，不能重复执行", code="ACTION_NOT_PENDING", status=409)
    if not proposal.meeting_id:
        raise FXPGError("该动作缺少子会议上下文", code="ACTION_SCOPE_REQUIRED", status=400)

    if proposal.action_id == "accept":
        meeting = accept_meeting_deliverables(db, proposal.project_id, proposal.meeting_id)
        return _mark_executed(db, proposal, _result(proposal, status=meeting.status, message="验收已通过"))

    if proposal.action_id == "reject":
        payload = proposal.payload_json or {}
        final_comment = (comment or payload.get("comment") or "").strip()
        if not final_comment:
            raise FXPGError("退回动作需要填写原因", code="COMMENT_REQUIRED", status=400)
        meeting = reject_meeting_deliverables(db, proposal.project_id, proposal.meeting_id, final_comment)
        return _mark_executed(db, proposal, _result(proposal, status=meeting.status, message="交付已退回"))

    if proposal.action_id == "reanalyze":
        job, created = start_harness_job(db, proposal.project_id, proposal.meeting_id)
        message = "重新分析已启动" if created else "已有分析任务进行中"
        return _mark_executed(db, proposal, _result(proposal, status="running", message=message, job_id=job.id))

    if proposal.action_id == "learn_rule_feedback":
        payload = proposal.payload_json or {}
        feedback = str(payload.get("feedback_text") or payload.get("user_message") or "").strip()
        if len(feedback) < 8:
            raise FXPGError("学习提案缺少明确纠错内容", code="LEARNING_FEEDBACK_REQUIRED", status=400)
        learning_id = str(payload.get("learning_proposal_id") or "")
        learning = db.get(LearningProposal, learning_id) if learning_id else None
        if learning:
            learning.status = "approved_pending_regression"
            learning.approved_at = datetime.now(timezone.utc)
            db.add(learning)
        else:
            learning = LearningProposal(
                project_id=proposal.project_id,
                meeting_id=proposal.meeting_id,
                feedback_text=feedback,
                proposed_patch_json=payload.get("learning_patch") or {},
                required_case_ids=["A1P260307357", "SMS202606090070"],
                regression_plan_json={"status": "required"},
                status="approved_pending_regression",
                approved_at=datetime.now(timezone.utc),
            )
            db.add(learning)
            db.flush()
        return _mark_executed(
            db,
            proposal,
            _result(
                proposal,
                status="approved_pending_regression",
                message="学习提案已批准，必须通过 A1P 与 SMS 基准回归后才能写入正式规则记忆。",
            ),
        )

    raise FXPGError("暂不支持执行该动作", code="ACTION_UNSUPPORTED", status=400)
