from __future__ import annotations

from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.services.embedding_service import embedding_dim


def is_postgres() -> bool:
    return settings.database_url.startswith("postgresql")


def pgvector_enabled(db: Session) -> bool:
    if not is_postgres():
        return False
    try:
        row = db.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector' LIMIT 1")
        ).first()
        return row is not None
    except Exception:
        return False


def ensure_pgvector_extension(db: Session) -> bool:
    if not is_postgres():
        return False
    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def vector_column_exists(db: Session) -> bool:
    if not is_postgres():
        return False
    try:
        row = db.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'memories' AND column_name = 'embedding_vector'
                LIMIT 1
                """
            )
        ).first()
        return row is not None
    except Exception:
        return False


def sync_memory_vector(db: Session, memory_id: str, vec: List[float]) -> None:
    if not pgvector_enabled(db) or not vector_column_exists(db):
        return
    dim = embedding_dim()
    if len(vec) != dim:
        return
    literal = "[" + ",".join(f"{x:.8f}" for x in vec) + "]"
    db.execute(
        text("UPDATE memories SET embedding_vector = CAST(:vec AS vector) WHERE id = :id"),
        {"vec": literal, "id": memory_id},
    )


def search_memories_by_vector(db: Session, query_vec: List[float], limit: int = 5) -> List[str]:
    if not pgvector_enabled(db) or not vector_column_exists(db):
        return []
    if len(query_vec) != embedding_dim():
        return []
    literal = "[" + ",".join(f"{x:.8f}" for x in query_vec) + "]"
    rows = db.execute(
        text(
            """
            SELECT id FROM memories
            WHERE embedding_vector IS NOT NULL
            ORDER BY embedding_vector <=> CAST(:q AS vector)
            LIMIT :limit
            """
        ),
        {"q": literal, "limit": limit},
    ).fetchall()
    return [r[0] for r in rows]
