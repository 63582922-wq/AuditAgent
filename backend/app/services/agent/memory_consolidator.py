from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import Memory
from app.services.embedding_service import embed_memory_content


@dataclass(frozen=True)
class MemoryConsolidationResult:
    written: int = 0
    skipped: int = 0
    source_count: int = 0
    memory_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "written": self.written,
            "skipped": self.skipped,
            "source_count": self.source_count,
            "memory_type": self.memory_type,
        }


def _clean_preference(content: str) -> str:
    text = " ".join((content or "").strip().split())
    if text.startswith("用户偏好："):
        text = text[len("用户偏好：") :]
    return text.strip(" 。；;")


def _common_prefix(items: list[str]) -> str:
    if not items:
        return ""
    prefix = items[0]
    for item in items[1:]:
        while prefix and not item.startswith(prefix):
            prefix = prefix[:-1]
    return prefix.strip()


def _normalize_tail(tail: str) -> str:
    text = tail.strip(" ，。；;")
    for verb in ("说明", "给"):
        if text.startswith(verb) and len(text) > len(verb):
            return text[len(verb) :]
    return text


def _tail_sort_key(text: str) -> tuple[int, str]:
    priorities = (
        ("缺资料", 0),
        ("证据", 1),
        ("下一步", 2),
    )
    for keyword, priority in priorities:
        if keyword in text:
            return priority, text
    return 20, text


def _summarize_preferences(preferences: list[str]) -> str:
    unique: list[str] = []
    seen: set[str] = set()
    for item in preferences:
        text = _clean_preference(item)
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]

    prefix = _common_prefix(unique)
    if len(prefix) >= 4:
        tails = [_normalize_tail(item[len(prefix) :]) for item in unique]
        tails = sorted([tail for tail in tails if tail], key=_tail_sort_key)
        if len(tails) == 1:
            return prefix + tails[0]
        if len(tails) >= 2:
            return prefix + "、".join(tails[:-1]) + "和" + tails[-1]
    return "；".join(unique)


def _chat_preference_memories(db: Session, project_id: str | None, limit: int) -> list[Memory]:
    rows = (
        db.query(Memory)
        .filter(Memory.memory_type == "user_preference")
        .order_by(Memory.created_at.desc(), Memory.id.desc())
        .limit(limit * 3)
        .all()
    )
    project_tag = f"project:{project_id}" if project_id else None
    out: list[Memory] = []
    for row in rows:
        tags = row.tags or []
        if "main_agent_chat" not in tags:
            continue
        if project_tag and project_tag not in tags:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return list(reversed(out))


def consolidate_chat_memories(
    db: Session,
    *,
    project_id: str | None,
    meeting_id: str | None = None,
    threshold: int = 3,
    limit: int = 5,
) -> MemoryConsolidationResult:
    rows = _chat_preference_memories(db, project_id, limit)
    if len(rows) < threshold:
        return MemoryConsolidationResult(skipped=1, source_count=len(rows))

    summary = _summarize_preferences([row.content for row in rows])
    if not summary:
        return MemoryConsolidationResult(skipped=1, source_count=len(rows))

    content = f"记忆整理：用户稳定偏好：{summary}。后续主 Agent 对话应优先遵循。"
    existing = db.query(Memory).filter_by(memory_type="memory_summary", content=content).first()
    if existing:
        return MemoryConsolidationResult(skipped=1, source_count=len(rows), memory_type="memory_summary")

    tags = ["main_agent_chat", "memory_summary", "user_preference_summary"]
    if project_id:
        tags.append(f"project:{project_id}")
    if meeting_id:
        tags.append(f"meeting:{meeting_id}")
    mem = Memory(
        memory_type="memory_summary",
        content=content,
        tags=tags,
        embedding_json=embed_memory_content(content, tags),
    )
    db.add(mem)
    db.commit()
    return MemoryConsolidationResult(written=1, source_count=len(rows), memory_type="memory_summary")
