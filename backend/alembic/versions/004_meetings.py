"""Meetings table and meeting_id on child entities

Revision ID: 004
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MEETING_FK_TABLES = (
    "files",
    "parsed_documents",
    "extracted_entities",
    "risks",
    "outputs",
    "agent_run_logs",
    "analysis_jobs",
    "record_links",
)


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("meeting_code", sa.String(64), nullable=False),
        sa.Column("meeting_title", sa.String(512), nullable=True),
        sa.Column("observation_type", sa.String(100), nullable=True),
        sa.Column("meeting_type", sa.String(100), nullable=True),
        sa.Column("meeting_date", sa.String(32), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("state_json", sa.JSON(), nullable=True),
        sa.Column("deliverable_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("project_id", "meeting_code", name="uq_meetings_project_code"),
    )
    op.create_index("ix_meetings_project_id", "meetings", ["project_id"])

    for table in MEETING_FK_TABLES:
        op.add_column(table, sa.Column("meeting_id", sa.String(36), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_meeting_id",
            table,
            "meetings",
            ["meeting_id"],
            ["id"],
        )
        op.create_index(f"ix_{table}_meeting_id", table, ["meeting_id"])

    bind = op.get_bind()
    projects = bind.execute(sa.text("SELECT id, name, status, state_json, summary FROM projects")).fetchall()
    now_expr = sa.text("CURRENT_TIMESTAMP")
    for row in projects:
        pid, name, status, state_json, summary = row
        state = state_json or {}
        meeting_case = state.get("meeting_case") or {}
        meeting_code = str(meeting_case.get("meeting_code") or "DEFAULT").strip() or "DEFAULT"
        mid = str(uuid.uuid4())
        deliverable = state.get("deliverable")
        m_state = {
            k: state.get(k)
            for k in (
                "meeting_case",
                "missing_documents",
                "present_categories",
                "agent_plan",
                "execution_graph",
                "mission",
                "sub_agent_briefs",
                "synthesis_brief",
                "runtime",
                "runtime_live",
                "execution_mode",
                "agent_domain",
                "processed_file_ids",
            )
            if state.get(k) is not None
        }
        if meeting_case and "meeting_case" not in m_state:
            m_state["meeting_case"] = meeting_case

        existing = bind.execute(
            sa.text(
                "SELECT id FROM meetings WHERE project_id = :pid AND meeting_code = :code"
            ),
            {"pid": pid, "code": meeting_code[:64]},
        ).fetchone()
        if existing:
            mid = existing[0]
        else:
            mid = str(uuid.uuid4())
            bind.execute(
                sa.text(
                    """
                    INSERT INTO meetings (
                        id, project_id, meeting_code, meeting_title, observation_type,
                        meeting_type, status, summary, state_json, deliverable_json,
                        created_at, updated_at
                    ) VALUES (
                        :id, :project_id, :meeting_code, :meeting_title, :observation_type,
                        :meeting_type, :status, :summary, :state_json, :deliverable_json,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": mid,
                    "project_id": pid,
                    "meeting_code": meeting_code[:64],
                    "meeting_title": str(meeting_case.get("meeting_title") or name or "")[:512] or None,
                    "observation_type": meeting_case.get("observation_type"),
                    "meeting_type": meeting_case.get("meeting_type"),
                    "status": status if status not in ("created",) else "draft",
                    "summary": summary,
                    "state_json": m_state,
                    "deliverable_json": deliverable,
                },
            )
        for table in MEETING_FK_TABLES:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET meeting_id = :mid "
                    f"WHERE project_id = :pid AND meeting_id IS NULL"
                ),
                {"mid": mid, "pid": pid},
            )


def downgrade() -> None:
    for table in reversed(MEETING_FK_TABLES):
        op.drop_index(f"ix_{table}_meeting_id", table_name=table)
        op.drop_constraint(f"fk_{table}_meeting_id", table, type_="foreignkey")
        op.drop_column(table, "meeting_id")
    op.drop_index("ix_meetings_project_id", table_name="meetings")
    op.drop_table("meetings")
