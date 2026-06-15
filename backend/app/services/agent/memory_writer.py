from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Memory, Risk, ReviewRecord
from app.services.agent.meeting_scope import scoped_query
from app.services.embedding_service import embed_memory_content


CONFIDENCE_THRESHOLD = 0.75
MAX_AUTO_MEMORIES = 12


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _memory_exists(db: Session, content: str) -> bool:
    h = _content_hash(content)
    for m in db.query(Memory).limit(500).all():
        if _content_hash(m.content) == h:
            return True
    return False


def _save_memory(
    db: Session,
    *,
    memory_type: str,
    content: str,
    tags: List[str],
) -> Optional[Memory]:
    if _memory_exists(db, content):
        return None
    mem = Memory(
        memory_type=memory_type,
        content=content[:2000],
        tags=tags,
        embedding_json=embed_memory_content(content, tags),
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


def write_adjudication_memory(db: Session, risk: Risk) -> Optional[Memory]:
    """将高置信度研判沉淀为长期记忆案例。"""
    if not risk.analysis or risk.confidence < CONFIDENCE_THRESHOLD:
        return None
    if risk.manual_review_required:
        return None

    content = (
        f"案例[{risk.risk_category}] {risk.problem}。"
        f"研判：{risk.analysis} "
        f"建议：{risk.suggestion}"
    )
    tags = list({risk.risk_category, "adjudication", risk.risk_level})
    return _save_memory(db, memory_type="case", content=content, tags=tags)


def write_review_memory(db: Session, risk: Risk, review: ReviewRecord) -> Optional[Memory]:
    """复核结论写回记忆（确认=正例，驳回=误报参考）。"""
    status = review.review_status
    comment = (review.review_comment or "").strip()
    if status not in ("confirmed", "dismissed"):
        return None

    if status == "confirmed":
        content = (
            f"复核确认[{risk.risk_category}] {risk.problem}。"
            f"研判：{risk.analysis or '—'} "
            f"意见：{comment or '人工确认属实'}"
        )
        tags = [risk.risk_category, "review_confirmed", risk.risk_level]
        mem_type = "confirmed_case"
    else:
        content = (
            f"误报参考[{risk.risk_category}] {risk.problem}。"
            f"驳回原因：{comment or '人工判定为误报'}"
        )
        tags = [risk.risk_category, "review_dismissed", "false_positive"]
        mem_type = "false_positive"

    return _save_memory(db, memory_type=mem_type, content=content, tags=tags)


def _agent_should_persist_risk(
    risk: Risk,
    *,
    validated_risk_ids: set[str],
    critic_flagged_ids: set[str],
) -> bool:
    """Agent 自决：是否将 Finding 沉淀为长期记忆。"""
    if risk.status == "dismissed":
        return bool(risk.analysis and risk.confidence >= 0.8)
    if risk.id in critic_flagged_ids:
        return False
    if risk.manual_review_required:
        return False
    if not risk.analysis:
        return False
    if risk.confidence < CONFIDENCE_THRESHOLD:
        return False
    if risk.id in validated_risk_ids:
        return True
    return risk.risk_level == "高" and risk.confidence >= 0.85


def _write_feedback_policy(db: Session, feedback: str) -> Optional[Memory]:
    text = (feedback or "").strip()
    if len(text) < 8:
        return None
    content = f"交付反馈口径：{text}"
    return _save_memory(
        db,
        memory_type="risk_policy",
        content=content,
        tags=["deliverable_feedback", "agent_learned"],
    )


@dataclass
class MemoryWriteSummary:
    written: int = 0
    skipped: int = 0
    types: Dict[str, int] = field(default_factory=dict)


def decide_and_persist_memories(
    db: Session,
    project_id: str,
    meeting_id: Optional[str] = None,
    *,
    critic_results: Optional[List[Any]] = None,
    deliverable_feedback: Optional[str] = None,
    limit: int = MAX_AUTO_MEMORIES,
) -> MemoryWriteSummary:
    """Agent 决策步：按置信度、Critic 与状态自决写回全局长期记忆。"""
    summary = MemoryWriteSummary()
    validated_ids: set[str] = set()
    flagged_ids: set[str] = set()
    for c in critic_results or []:
        rid = getattr(c, "risk_id", None) or (c.get("risk_id") if isinstance(c, dict) else None)
        if not rid:
            continue
        valid = getattr(c, "valid", None)
        if valid is None and isinstance(c, dict):
            valid = c.get("valid")
        if valid:
            validated_ids.add(str(rid))
        else:
            flagged_ids.add(str(rid))

    risks = (
        scoped_query(db, Risk, project_id, meeting_id)
        .filter(Risk.status != "dismissed")
        .order_by(Risk.risk_score.desc())
        .limit(limit * 2)
        .all()
    )
    for risk in risks:
        if summary.written >= limit:
            break
        if not _agent_should_persist_risk(
            risk,
            validated_risk_ids=validated_ids,
            critic_flagged_ids=flagged_ids,
        ):
            summary.skipped += 1
            continue
        mem = (
            write_review_memory(
                db,
                risk,
                ReviewRecord(
                    project_id=project_id,
                    risk_id=risk.id,
                    review_status="dismissed" if risk.status == "dismissed" else "confirmed",
                    review_comment="Agent 自动沉淀",
                ),
            )
            if risk.status == "dismissed"
            else write_adjudication_memory(db, risk)
        )
        if mem:
            summary.written += 1
            summary.types[mem.memory_type] = summary.types.get(mem.memory_type, 0) + 1
        else:
            summary.skipped += 1

    if deliverable_feedback:
        if _write_feedback_policy(db, deliverable_feedback):
            summary.written += 1
            summary.types["risk_policy"] = summary.types.get("risk_policy", 0) + 1

    return summary


def persist_adjudication_memories(
    db: Session,
    project_id: str,
    meeting_id: Optional[str] = None,
    limit: int = 20,
) -> int:
    """兼容旧调用：委托 Agent 决策步。"""
    summary = decide_and_persist_memories(db, project_id, meeting_id, limit=limit)
    return summary.written
