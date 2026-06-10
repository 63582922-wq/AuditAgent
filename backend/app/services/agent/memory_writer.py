from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Memory, Risk, ReviewRecord
from app.services.embedding_service import embed_memory_content


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _memory_exists(db: Session, content: str) -> bool:
    h = _content_hash(content)
    for m in db.query(Memory).limit(500).all():
        if _content_hash(m.content) == h:
            return True
    return False


def write_adjudication_memory(db: Session, risk: Risk) -> Optional[Memory]:
    """将高置信度研判沉淀为长期记忆案例。"""
    if not risk.analysis or risk.confidence < 0.75:
        return None
    if risk.manual_review_required:
        return None

    content = (
        f"案例[{risk.risk_category}] {risk.problem}。"
        f"研判：{risk.analysis} "
        f"建议：{risk.suggestion}"
    )
    if _memory_exists(db, content):
        return None

    tags = list({risk.risk_category, "adjudication", risk.risk_level})
    mem = Memory(
        memory_type="case",
        content=content[:2000],
        tags=tags,
        embedding_json=embed_memory_content(content, tags),
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


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

    if _memory_exists(db, content):
        return None

    mem = Memory(
        memory_type=mem_type,
        content=content[:2000],
        tags=tags,
        embedding_json=embed_memory_content(content, tags),
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


def persist_adjudication_memories(db: Session, project_id: str, limit: int = 20) -> int:
    risks = (
        db.query(Risk)
        .filter_by(project_id=project_id)
        .filter(Risk.status != "dismissed")
        .order_by(Risk.risk_score.desc())
        .limit(limit)
        .all()
    )
    written = 0
    for r in risks:
        if write_adjudication_memory(db, r):
            written += 1
    return written
