from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Memory
from app.services.embedding_service import cosine_similarity, embed_text
from app.services.vector_store import pgvector_enabled, search_memories_by_vector


def retrieve_memories(
    db: Session,
    risk_category: Optional[str] = None,
    tags: Optional[List[str]] = None,
    query_text: Optional[str] = None,
    limit: int = 5,
) -> List[Memory]:
    """混合检索：PostgreSQL pgvector 优先，否则 JSON 向量 + 标签匹配。"""
    query_vec = None
    if query_text:
        query_vec = embed_text(query_text)
    elif risk_category:
        query_vec = embed_text(risk_category)

    if query_vec and pgvector_enabled(db):
        ids = search_memories_by_vector(db, query_vec, limit=limit * 2)
        if ids:
            by_id = {m.id: m for m in db.query(Memory).filter(Memory.id.in_(ids)).all()}
            ordered = [by_id[i] for i in ids if i in by_id]
            if ordered:
                return ordered[:limit]

    memories = db.query(Memory).order_by(Memory.updated_at.desc()).limit(200).all()
    if not memories:
        return []

    tag_set = set(tags or [])
    if risk_category:
        tag_set.add(risk_category)

    scored: List[tuple[float, Memory]] = []
    for m in memories:
        tag_score = 0.0
        if tag_set:
            m_tags = set(m.tags or [])
            overlap = len(tag_set & m_tags)
            if risk_category and risk_category in (m.content[:30] or ""):
                overlap += 1
            tag_score = overlap / max(len(tag_set), 1)

        vec_score = 0.0
        if query_vec and m.embedding_json:
            vec_score = max(0.0, cosine_similarity(query_vec, m.embedding_json))

        if query_vec or tag_set:
            combined = vec_score * 0.65 + tag_score * 0.35
            if combined > 0:
                scored.append((combined, m))
        else:
            scored.append((0.0, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    if scored:
        return [m for _, m in scored[:limit]]
    return memories[:limit]


def format_memories_for_prompt(memories: List[Memory]) -> str:
    if not memories:
        return "（无相关记忆）"
    return "\n".join(f"- [{m.memory_type}] {m.content}" for m in memories)
