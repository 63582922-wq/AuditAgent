"""Add memory embedding_json column

Revision ID: 002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if insp.has_table("memories"):
        cols = {c["name"] for c in insp.get_columns("memories")}
        if "embedding_json" not in cols:
            op.add_column("memories", sa.Column("embedding_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if insp.has_table("memories"):
        cols = {c["name"] for c in insp.get_columns("memories")}
        if "embedding_json" in cols:
            op.drop_column("memories", "embedding_json")
