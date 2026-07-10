from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    AgentActionProposal,
    AgentRunLog,
    AnalysisJob,
    FileRecord,
    Meeting,
    Memory,
    LearningProposal,
    ParsedDocument,
    Project,
    Risk,
)
from app.schemas import AgentChatAction, AgentChatMessage, AgentChatResponse
from app.services.agent.agent_trace import trace_code_location
from app.services.agent import llm_client
from app.services.agent.memory_consolidator import consolidate_chat_memories
from app.services.agent.prompt_loader import MAIN_AGENT_PROMPT_VERSION, main_agent_system_prompt
from app.services.embedding_service import embed_memory_content
from app.services.memory_rag import retrieve_memories
from app.services.output_scope import primary_output_count
from app.services.domain.compliance.evidence_graph import fact_citations
from app.services.meeting_service import delivery_acceptance_gate


@dataclass(frozen=True)
class MemoryWriteResult:
    written: int = 0
    skipped: int = 0
    memory_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"written": self.written, "skipped": self.skipped, "memory_type": self.memory_type}


@dataclass(frozen=True)
class ChatContext:
    project_id: str | None
    project_name: str | None
    meeting_id: str | None
    meeting_code: str | None
    status: str
    files: int
    findings: int
    outputs: int
    latest_job_status: str | None
    latest_job_step: str | None
    latest_job_progress: int | None
    recent_logs: list[str]
    memories: list[str]
    meeting_case: dict[str, Any]
    present_categories: list[str]
    missing_documents: list[dict[str, Any]]
    category_counts: dict[str, int]
    findings_summary: list[dict[str, Any]]
    current_facts: dict[str, Any]
    citations: list[dict[str, Any]]
    delivery_gate: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "meeting_id": self.meeting_id,
            "meeting_code": self.meeting_code,
            "status": self.status,
            "files": self.files,
            "findings": self.findings,
            "outputs": self.outputs,
            "latest_job": {
                "status": self.latest_job_status,
                "step": self.latest_job_step,
                "progress": self.latest_job_progress,
            },
            "recent_logs": self.recent_logs,
            "reference_memories": self.memories,
            "memories": self.memories,
            "memory_count": len(self.memories),
            "meeting_case": self.meeting_case,
            "present_categories": self.present_categories,
            "missing_documents": self.missing_documents,
            "category_counts": self.category_counts,
            "findings_summary": self.findings_summary,
            "current_facts": self.current_facts,
            "citations": self.citations,
            "delivery_gate": self.delivery_gate,
        }


ACTION_DEFS: dict[str, AgentChatAction] = {
    "projects": AgentChatAction(
        id="projects",
        label="打开观察项目",
        description="选择或导入一场观察案件",
        segment="projects",
    ),
    "files": AgentChatAction(
        id="files",
        label="补充资料",
        description="上传缺件或重新运行分析",
        segment="files",
        requires_meeting=True,
    ),
    "findings": AgentChatAction(
        id="risks",
        label="查看 Finding",
        description="核对命中项和证据链",
        segment="risks",
        requires_meeting=True,
    ),
    "review": AgentChatAction(
        id="review",
        label="逐条复核",
        description="在审核结论中确认、排除或标记需补充",
        segment="risks",
        requires_meeting=True,
    ),
    "outputs": AgentChatAction(
        id="outputs",
        label="交付验收",
        description="下载、验收或退回交付物",
        segment="outputs",
        requires_meeting=True,
    ),
    "logs": AgentChatAction(
        id="logs",
        label="查看 Agent 日志",
        description="定位执行步骤和工具调用",
        segment="logs",
        requires_meeting=True,
    ),
    "accept": AgentChatAction(
        id="accept",
        label="去验收通过",
        description="跳到交付页执行验收",
        segment="outputs",
        requires_meeting=True,
        requires_approval=True,
        tone="warning",
    ),
    "reject": AgentChatAction(
        id="reject",
        label="去退回交付",
        description="跳到交付页填写退回原因",
        segment="outputs",
        requires_meeting=True,
        requires_approval=True,
        tone="warning",
    ),
    "reanalyze": AgentChatAction(
        id="reanalyze",
        label="去重新分析",
        description="跳到资料页发起重跑",
        segment="files",
        requires_meeting=True,
        requires_approval=True,
        tone="warning",
    ),
    "learn_rule_feedback": AgentChatAction(
        id="learn_rule_feedback",
        label="提交规则学习提案",
        description="将本次纠错整理为待审批规则/记忆变更，不会直接改全局规则",
        segment="risks",
        requires_meeting=True,
        requires_approval=True,
        tone="warning",
    ),
}


def _contains_any(text: str, words: list[str]) -> bool:
    low = text.lower()
    return any(word.lower() in low for word in words)


def _is_correction_feedback(message: str) -> bool:
    if _contains_any(message, ["请记住", "记住：", "记住:"]):
        return False
    return _contains_any(message, ["不对", "不是这样", "错了", "误判", "漏判", "应该", "不应该"])


def _is_actionable_learning_feedback(message: str) -> bool:
    text = " ".join(message.strip().split())
    if not _is_correction_feedback(text):
        return False
    has_directive = _contains_any(text, ["以后", "下次", "应该", "不应该", "不能", "必须", "要"])
    return has_directive and len(text) >= 18


def _is_delivery_artifact_question(message: str) -> bool:
    return _contains_any(
        message,
        ["固定模板", "143", "excel", "xlsx", "zip", "交付物", "输出表格", "deliverable", "output"],
    ) and _contains_any(message, ["交付", "下载", "哪里", "在哪里", "输出", "验收", "deliver", "download"])


def _actions(*ids: str, has_meeting: bool) -> list[AgentChatAction]:
    out = []
    for action_id in ids:
        action = ACTION_DEFS[action_id]
        if not action.requires_meeting or has_meeting:
            out.append(action)
    return out or [ACTION_DEFS["projects"]]


def _latest_job(db: Session, project_id: str, meeting_id: str | None) -> AnalysisJob | None:
    query = db.query(AnalysisJob).filter_by(project_id=project_id)
    if meeting_id:
        query = query.filter_by(meeting_id=meeting_id)
    return query.order_by(AnalysisJob.created_at.desc()).first()


def _recent_logs(db: Session, project_id: str, meeting_id: str | None) -> list[str]:
    query = db.query(AgentRunLog).filter_by(project_id=project_id)
    if meeting_id:
        query = query.filter_by(meeting_id=meeting_id)
    logs = (
        query.filter(AgentRunLog.step != "main_agent_chat")
        .order_by(AgentRunLog.created_at.desc())
        .limit(5)
        .all()
    )
    lines: list[str] = []
    for log in logs:
        detail = log.detail_json or {}
        message = detail.get("message") or detail.get("name") or log.step
        lines.append(f"{log.step}:{log.status}:{message}")
    return lines


def _relevant_memories(
    db: Session,
    query_text: str | None,
    *,
    project_id: str | None = None,
    meeting_id: str | None = None,
) -> list[str]:
    memories = retrieve_memories(
        db,
        tags=[tag for tag in ["main_agent_chat", f"project:{project_id}" if project_id else "", f"meeting:{meeting_id}" if meeting_id else ""] if tag],
        query_text=query_text,
        limit=10,
    )
    allowed_types = {"user_preference", "rule_feedback_policy", "memory_summary"}
    memories = [m for m in memories if m.memory_type in allowed_types]
    return [f"[{m.memory_type}] {m.content[:240]}" for m in memories if m.content]


def _category_counts(files: list[FileRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in files:
        counts[f.document_category] = counts.get(f.document_category, 0) + 1
    return counts


def _risk_summary(rows: list[Risk]) -> list[dict[str, Any]]:
    return [
        {
            "risk_id": r.risk_id,
            "problem": r.problem,
            "suggestion": r.suggestion,
            "evidence_json": r.evidence_json or {},
            "status": r.status,
            "confidence": r.confidence,
        }
        for r in rows[:8]
    ]


def _vision_review_facts(db: Session, *, project_id: str, meeting_id: str | None) -> dict[str, Any]:
    query = (
        db.query(ParsedDocument, FileRecord)
        .join(FileRecord, ParsedDocument.file_id == FileRecord.id)
        .filter(ParsedDocument.project_id == project_id)
    )
    if meeting_id:
        query = query.filter(ParsedDocument.meeting_id == meeting_id)

    total = 0
    manual = 0
    consensus_needs_review = 0
    reasons: list[str] = []
    files: list[dict[str, Any]] = []
    for doc, file_record in query.all():
        content = doc.content_json or {}
        consensus = content.get("vision_consensus") if isinstance(content.get("vision_consensus"), dict) else {}
        is_vision_doc = bool(
            content.get("vision_agent")
            or content.get("vision_quality")
            or content.get("recognition_plan")
            or consensus
        )
        if not is_vision_doc:
            continue
        total += 1
        doc_reasons = list(
            dict.fromkeys([*(content.get("review_reasons") or []), *(consensus.get("review_reasons") or [])])
        )
        if content.get("manual_review_required") or consensus.get("manual_review_required"):
            manual += 1
        if consensus.get("status") == "needs_review":
            consensus_needs_review += 1
        reasons.extend(str(item) for item in doc_reasons if item)
        if doc_reasons or consensus.get("status") == "needs_review":
            files.append(
                {
                    "file_name": file_record.file_name,
                    "document_category": file_record.document_category,
                    "consensus_status": consensus.get("status"),
                    "review_reasons": doc_reasons,
                }
            )

    return {
        "vision_document_count": total,
        "vision_manual_review_count": manual,
        "vision_consensus_needs_review_count": consensus_needs_review,
        "vision_review_reasons": sorted(set(reasons)),
        "vision_review_files": files[:8],
    }


def _current_facts(
    meeting_case: dict[str, Any],
    present_categories: list[str],
    missing_documents: list[dict[str, Any]],
    category_counts: dict[str, int],
    vision_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proof_categories = {
        "observation_confirmation",
        "meeting_screenshot",
        "coordination_sms",
        "sign_in_record",
        "meeting_agenda",
    }
    meeting_reality_evidence_count = sum(category_counts.get(category, 0) for category in proof_categories)
    facts = {
        "actual_sign_in_count": meeting_case.get("actual_sign_in_count"),
        "planned_attendees": meeting_case.get("planned_attendees"),
        "attendance_delta": meeting_case.get("attendance_delta"),
        "has_sign_in_record": "sign_in_record" in present_categories,
        "sign_in_file_count": category_counts.get("sign_in_record", 0),
        "has_a1_meeting_export": "a1_meeting_export" in present_categories,
        "has_observation_confirmation": "observation_confirmation" in present_categories,
        "has_meeting_screenshot": "meeting_screenshot" in present_categories,
        "has_coordination_sms": "coordination_sms" in present_categories,
        "meeting_reality_evidence_count": meeting_reality_evidence_count,
        "missing_document_count": len(missing_documents),
    }
    facts["materials_sufficient_by_structure"] = len(missing_documents) == 0
    facts.update(vision_facts or {})
    return facts


def build_chat_context(
    db: Session,
    project_id: str | None,
    meeting_id: str | None,
    query_text: str | None = None,
) -> ChatContext:
    project: Project | None = None
    meeting: Meeting | None = None

    if project_id:
        project = db.get(Project, project_id)
        if not project:
            raise HTTPException(404, "项目不存在")

    if meeting_id:
        if not project_id:
            raise HTTPException(400, "meeting_id 需要同时提供 project_id")
        meeting = db.query(Meeting).filter_by(project_id=project_id, id=meeting_id).first()
        if not meeting:
            raise HTTPException(404, "子会议不存在")

    if not project:
        return ChatContext(
            project_id=None,
            project_name=None,
            meeting_id=None,
            meeting_code=None,
            status="global",
            files=0,
            findings=0,
            outputs=0,
            latest_job_status=None,
            latest_job_step=None,
            latest_job_progress=None,
            recent_logs=[],
            memories=_relevant_memories(db, query_text),
            meeting_case={},
            present_categories=[],
            missing_documents=[],
            category_counts={},
            findings_summary=[],
            current_facts={},
            citations=[],
            delivery_gate={},
        )

    filters: dict[str, Any] = {"project_id": project.id}
    if meeting:
        filters["meeting_id"] = meeting.id

    files = db.query(FileRecord).filter_by(**filters).all()
    risks = db.query(Risk).filter_by(**filters).order_by(Risk.created_at.desc()).all()
    state = dict((meeting.state_json if meeting else project.state_json) or {})
    meeting_case = dict(state.get("meeting_case") or {})
    present_categories = sorted(set(state.get("present_categories") or [f.document_category for f in files if f.document_category]))
    missing_documents = list(state.get("missing_documents") or [])
    category_counts = _category_counts(files)
    vision_facts = _vision_review_facts(db, project_id=project.id, meeting_id=meeting.id if meeting else None)
    current_facts = _current_facts(
        meeting_case,
        present_categories,
        missing_documents,
        category_counts,
        vision_facts,
    )

    job = _latest_job(db, project.id, meeting.id if meeting else None)
    citations = fact_citations(db, project.id, meeting.id, limit=12) if meeting else []
    delivery_gate = delivery_acceptance_gate(db, meeting) if meeting else {}
    return ChatContext(
        project_id=project.id,
        project_name=project.name,
        meeting_id=meeting.id if meeting else None,
        meeting_code=meeting.meeting_code if meeting else None,
        status=meeting.status if meeting else project.status,
        files=len(files),
        findings=len(risks),
        outputs=primary_output_count(db, **filters),
        latest_job_status=job.status if job else None,
        latest_job_step=job.current_step if job else None,
        latest_job_progress=job.progress_pct if job else None,
        recent_logs=_recent_logs(db, project.id, meeting.id if meeting else None),
        memories=_relevant_memories(db, query_text, project_id=project.id, meeting_id=meeting.id if meeting else None),
        meeting_case=meeting_case,
        present_categories=present_categories,
        missing_documents=missing_documents,
        category_counts=category_counts,
        findings_summary=_risk_summary(risks),
        current_facts=current_facts,
        citations=citations,
        delivery_gate=delivery_gate,
    )


def suggest_actions(message: str, ctx: ChatContext) -> list[AgentChatAction]:
    has_meeting = bool(ctx.meeting_id)
    if not ctx.project_id:
        return _actions("projects", has_meeting=has_meeting)
    if _is_actionable_learning_feedback(message):
        return _actions("learn_rule_feedback", "review", "logs", has_meeting=has_meeting)
    if _contains_any(message, ["状态", "进度", "卡", "日志", "status", "progress", "where", "log"]):
        return _actions("logs", "files", "outputs", has_meeting=has_meeting)
    if _contains_any(message, ["图片", "识别", "视觉", "手写", "置信", "ocr", "OCR"]):
        return _actions("files", "review", "logs", has_meeting=has_meeting)
    if _contains_any(message, ["资料", "补充", "缺", "上传", "文件", "material", "missing", "upload"]):
        if has_meeting and not ctx.missing_documents:
            return _actions("findings", "review", "outputs", "logs", "files", has_meeting=has_meeting)
        return _actions("files", "reanalyze", "logs", has_meeting=has_meeting)
    if _contains_any(message, ["finding", "风险", "证据", "复核", "review", "evidence"]):
        return _actions("findings", "review", "files", has_meeting=has_meeting)
    if _contains_any(message, ["交付", "验收", "下载", "退回", "accept", "reject", "deliver", "output"]):
        if has_meeting and ctx.delivery_gate.get("blocked"):
            return _actions("outputs", "review", "reanalyze", "logs", has_meeting=has_meeting)
        return _actions("outputs", "accept", "reject", has_meeting=has_meeting)
    if _contains_any(message, ["重跑", "重新", "再分析", "reanalyze", "rerun"]):
        return _actions("reanalyze", "review", "logs", has_meeting=has_meeting)
    return _actions("files", "review", "outputs", "logs", has_meeting=has_meeting)


def persist_action_proposals(
    db: Session,
    ctx: ChatContext,
    message: str,
    actions: list[AgentChatAction],
) -> list[AgentChatAction]:
    if not ctx.project_id:
        return actions
    next_actions: list[AgentChatAction] = []
    for action in actions:
        if not action.requires_approval:
            next_actions.append(action)
            continue
        payload: dict[str, Any] = {"source": "main_agent_chat", "user_message": message}
        if action.id == "learn_rule_feedback":
            learning_patch = build_learning_patch(message, ctx)
            learning = LearningProposal(
                project_id=ctx.project_id,
                meeting_id=ctx.meeting_id,
                feedback_text=message.strip(),
                original_conclusion="；".join(
                    str(item.get("problem") or "") for item in ctx.findings_summary[:3] if item.get("problem")
                )
                or None,
                proposed_patch_json=learning_patch,
                required_case_ids=list(learning_patch["evaluation_gate"]["required_cases"]),
                regression_plan_json=learning_patch["evaluation_gate"],
            )
            db.add(learning)
            db.flush()
            payload.update(
                {
                    "proposal_type": "rule_memory_patch",
                    "feedback_text": message.strip(),
                    "learning_patch": learning_patch,
                    "learning_proposal_id": learning.id,
                    "requires_evaluation": True,
                    "approval_required_reason": "用户纠错可能改变后续同类案件研判，需先审批并保留回滚依据",
                }
            )
        proposal = AgentActionProposal(
            project_id=ctx.project_id,
            meeting_id=ctx.meeting_id,
            action_id=action.id,
            label=action.label,
            description=action.description,
            segment=action.segment,
            payload_json=payload,
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)
        next_actions.append(action.model_copy(update={"proposal_id": proposal.id}))
    return next_actions


def classify_chat_intent(message: str) -> str:
    if _is_correction_feedback(message):
        return "learning_feedback"
    if _contains_any(message, ["删除", "验收", "退回", "重跑", "重新分析", "上传", "补充资料", "执行", "处理"]):
        return "operation"
    if _contains_any(message, ["分析", "核对", "比较", "检查", "识别", "提取", "统计"]):
        return "analysis_request"
    return "consult"


def submit_agent_feedback(
    db: Session,
    *,
    feedback: str,
    project_id: str,
    meeting_id: str | None = None,
    original_conclusion: str | None = None,
) -> LearningProposal:
    value = feedback.strip()
    if len(value) < 8:
        raise HTTPException(400, "请提供具体的纠错依据或后续规则")
    ctx = build_chat_context(db, project_id, meeting_id, value)
    patch = build_learning_patch(value, ctx)
    proposal = LearningProposal(
        project_id=project_id,
        meeting_id=meeting_id,
        feedback_text=value,
        original_conclusion=original_conclusion,
        proposed_patch_json=patch,
        required_case_ids=list(patch["evaluation_gate"]["required_cases"]),
        regression_plan_json=patch["evaluation_gate"],
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


def build_learning_patch(message: str, ctx: ChatContext) -> dict[str, Any]:
    text = " ".join(message.strip().split())
    meeting_code = ctx.meeting_code or ctx.meeting_case.get("meeting_code")
    return {
        "domain": "compliance",
        "source": "main_agent_chat",
        "scope": "future_similar_cases",
        "approval_state": "pending",
        "policy_text": text,
        "current_case": {
            "project_id": ctx.project_id,
            "meeting_id": ctx.meeting_id,
            "meeting_code": meeting_code,
            "status": ctx.status,
        },
        "evidence_requirements": [
            "必须引用当前案件资料、ParsedDocument 或固定模板字段证据",
            "不得用长期记忆覆盖当前案件事实",
            "涉及图片/手写/低置信字段时必须进入复核或补资料路径",
        ],
        "evaluation_gate": {
            "required_cases": ["A1P260307357", "SMS202606090070"],
            "must_pass": [
                "classification_distribution",
                "core_fact_regression",
                "fixed_template_143_columns",
                "delivery_scope",
            ],
        },
    }


def fallback_reply(message: str, ctx: ChatContext) -> str:
    if not ctx.project_id:
        return "我可以先帮你进入观察项目。选择或导入一场观察案件后，我会带上该场资料、Finding、交付和日志上下文回答。"

    scope = f"子会议 {ctx.meeting_code or ctx.meeting_id}" if ctx.meeting_id else f"项目 {ctx.project_name}"
    base = (
        f"当前上下文是{scope}：状态 {ctx.status}，资料 {ctx.files} 份，"
        f"Finding {ctx.findings} 条，交付物 {ctx.outputs} 个。"
    )
    facts = ctx.current_facts or {}
    material_status = (
        f"结构化缺件清单 {len(ctx.missing_documents)} 项；"
        f"签到表 {facts.get('sign_in_file_count') or 0} 份，"
        f"实际签到 {facts.get('actual_sign_in_count') if facts.get('actual_sign_in_count') is not None else '未确定'} 人，"
        f"计划参会 {facts.get('planned_attendees') if facts.get('planned_attendees') is not None else '未确定'} 人；"
        f"会议真实性证据 {facts.get('meeting_reality_evidence_count') or 0} 份。"
    )
    if ctx.findings_summary:
        finding_text = "当前 Finding：" + "；".join(
            f"{item.get('problem')}（证据：{item.get('evidence_json') or {}}）"
            for item in ctx.findings_summary[:3]
        )
    else:
        finding_text = "当前没有 Finding。"

    if _is_actionable_learning_feedback(message):
        return (
            base
            + "我会把这次纠错整理成待审批的规则学习提案。批准前不会改全局规则；批准后会写入长期记忆，并要求后续通过回放评测再进入正式规则。"
        )
    if _is_correction_feedback(message):
        return (
            base
            + "请说明正确判法、依据哪份资料，以及这是只适用本案，还是以后同类案件都适用。信息完整后我会生成待审批的规则学习提案。"
        )
    if _is_delivery_artifact_question(message):
        return (
            base
            + material_status
            + "正式交付入口只有两个：固定模板输出.xlsx（fixed_template_excel，143列主表）和交付物归档包 ZIP（deliverable_package）。"
            + "A1 会议导出、现场确认单、证据索引、Finding 报告等是资料或 ZIP 内支撑文件，不是固定模板主交付。请到交付验收页下载固定模板或 ZIP 后再验收。"
        )
    if _contains_any(message, ["图片", "识别", "视觉", "手写", "置信", "ocr", "OCR"]):
        review_files = facts.get("vision_review_files") or []
        reason_text = "、".join(facts.get("vision_review_reasons") or []) or "无"
        file_text = "；".join(
            f"{item.get('file_name')}({','.join(item.get('review_reasons') or [])})"
            for item in review_files[:3]
        )
        if not file_text:
            file_text = "暂无需复核图片"
        return (
            base
            + material_status
            + f"视觉资料 {facts.get('vision_document_count') or 0} 份；"
            + f"视觉复核 {facts.get('vision_manual_review_count') or 0} 份；"
            + f"共识待复核 {facts.get('vision_consensus_needs_review_count') or 0} 份；"
            + f"原因：{reason_text}。"
            + f"重点文件：{file_text}。"
        )
    if _contains_any(message, ["资料", "补充", "缺", "上传", "文件", "material", "missing", "upload"]):
        if not ctx.missing_documents:
            return (
                base
                + material_status
                + "按当前结构化资料判断，没有系统级缺件；如仍需复核，应针对具体 Finding 或固定模板字段核对，而不是要求补签到表或现场照片。"
            )
        missing_text = "、".join(str(item.get("document_type") or item) for item in ctx.missing_documents[:6])
        return base + material_status + f"当前仍有缺件：{missing_text}。应先补对应资料，再重新运行分析。"
    if _contains_any(message, ["交付", "验收", "下载", "退回", "accept", "reject", "deliver", "output"]):
        if ctx.delivery_gate.get("blocked"):
            return (
                base
                + f"当前正式验收已阻断：{ctx.delivery_gate.get('message') or '交付门禁未通过'}。"
                + "可以下载预览 Excel 和 ZIP 核对，但应先完成复核、补件或重跑，不能标记为已验收。"
            )
        return base + "交付动作应在交付验收页完成，下载核对后再验收；退回和重新分析都应保留结构化记录。"
    if _contains_any(message, ["finding", "风险", "证据", "复核", "review", "evidence"]):
        return base + material_status + finding_text
    if _contains_any(message, ["重跑", "重新", "再分析", "reanalyze", "rerun"]):
        return base + "重新分析是高影响动作，应从资料页或复核页发起，并保留原因和执行日志。"
    if ctx.latest_job_status:
        return base + f"最近任务为 {ctx.latest_job_status}，步骤 {ctx.latest_job_step or '-'}，进度 {ctx.latest_job_progress or 0}%。"
    return base + "你可以继续问缺资料、Finding 证据链、复核、交付验收或下一步操作。"


def clean_agent_reply(text: str) -> str:
    return (
        text.strip()
        .replace("**", "")
        .replace("__", "")
        .replace("```", "")
    )


def _extract_user_preference(message: str) -> str | None:
    text = " ".join(message.strip().split())
    markers = ["请记住：", "请记住:", "记住：", "记住:", "以后"]
    for marker in markers:
        if marker in text:
            value = text.split(marker, 1)[1].strip(" ，。；;")
            if len(value) >= 6:
                return value[:500]
    return None


def persist_chat_memory(db: Session, ctx: ChatContext, message: str) -> MemoryWriteResult:
    if _is_actionable_learning_feedback(message):
        return MemoryWriteResult(skipped=1, memory_type="learning_proposal")
    preference = _extract_user_preference(message)
    if not preference:
        return MemoryWriteResult()

    content = f"用户偏好：{preference}"
    existing = db.query(Memory).filter_by(memory_type="user_preference", content=content).first()
    if existing:
        return MemoryWriteResult(written=0, skipped=1, memory_type="user_preference")

    tags = ["main_agent_chat", "user_preference"]
    if ctx.project_id:
        tags.append(f"project:{ctx.project_id}")
    if ctx.meeting_id:
        tags.append(f"meeting:{ctx.meeting_id}")
    mem = Memory(
        memory_type="user_preference",
        content=content,
        tags=tags,
        embedding_json=embed_memory_content(content, tags),
    )
    db.add(mem)
    db.commit()
    return MemoryWriteResult(written=1, memory_type="user_preference")


def llm_reply(message: str, history: list[AgentChatMessage], ctx: ChatContext) -> str | None:
    if not llm_client.llm_available():
        return None

    system = main_agent_system_prompt()
    context_text = json.dumps(ctx.as_dict(), ensure_ascii=False, default=str)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "system", "content": f"当前系统上下文 JSON：{context_text}"},
    ]
    for item in history[-6:]:
        role = "assistant" if item.role == "agent" else "user"
        messages.append({"role": role, "content": item.content[:1000]})
    messages.append({"role": "user", "content": message})

    try:
        result = llm_client.chat_completion(messages, temperature=0.2)
    except Exception:
        return None
    reply = (result.get("content") or "").strip()
    return clean_agent_reply(reply) or None


def record_chat(
    db: Session,
    ctx: ChatContext,
    message: str,
    reply: str,
    actions: list[AgentChatAction],
    mode: str,
    intent: str,
) -> None:
    if not ctx.project_id:
        return
    db.add(
        AgentRunLog(
            project_id=ctx.project_id,
            meeting_id=ctx.meeting_id,
            step="main_agent_chat",
            status="completed",
            detail_json={
                "kind": "chat",
                "name": "主 Agent 对话",
                "message": reply,
                "user_message": message,
                "actions": [a.model_dump() for a in actions],
                "mode": mode,
                "intent": intent,
                "citations": ctx.citations,
                "code_location": trace_code_location(),
            },
        )
    )
    db.commit()


def run_main_agent_chat(
    db: Session,
    *,
    message: str,
    project_id: str | None = None,
    meeting_id: str | None = None,
    history: list[AgentChatMessage] | None = None,
) -> AgentChatResponse:
    value = message.strip()
    if not value:
        raise HTTPException(400, "消息不能为空")

    ctx = build_chat_context(db, project_id, meeting_id, value)
    intent = classify_chat_intent(value)
    actions = suggest_actions(value, ctx)
    actions = persist_action_proposals(db, ctx, value, actions)
    memory_write = persist_chat_memory(db, ctx, value)
    memory_consolidation = consolidate_chat_memories(db, project_id=ctx.project_id, meeting_id=ctx.meeting_id)
    governed_feedback = _is_correction_feedback(value)
    deterministic_delivery = _is_delivery_artifact_question(value)
    reply = None if governed_feedback or deterministic_delivery else llm_reply(value, history or [], ctx)
    mode = "governed_feedback" if governed_feedback else ("fallback" if deterministic_delivery else ("llm" if reply else "fallback"))
    if governed_feedback or not reply:
        reply = fallback_reply(value, ctx)
    record_chat(db, ctx, value, reply, actions, mode, intent)
    context = ctx.as_dict()
    context["prompt_version"] = MAIN_AGENT_PROMPT_VERSION
    context["memory_write"] = memory_write.as_dict()
    context["memory_consolidation"] = memory_consolidation.as_dict()
    return AgentChatResponse(
        reply=reply,
        answer=reply,
        actions=actions,
        planned_actions=actions,
        citations=ctx.citations,
        intent=intent,
        mode=mode,
        context=context,
    )
