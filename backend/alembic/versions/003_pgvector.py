"""Add pgvector column for memory semantic search

Revision ID: 003
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding_vector vector(384)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memories_embedding_hnsw
        ON memories USING hnsw (embedding_vector vector_cosine_ops)
        """
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_memories_embedding_hnsw")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS embedding_vector")
