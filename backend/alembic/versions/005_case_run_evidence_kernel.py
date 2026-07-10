"""Case runs, evidence claims, fact decisions, and governed learning proposals.

Revision ID: 005
Revises: 004
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "case_runs" not in tables:
        op.create_table(
        "case_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=True),
        sa.Column("run_kind", sa.String(50), nullable=False, server_default="full"),
        sa.Column("execution_mode", sa.String(100), nullable=False, server_default="compliance_harness"),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("input_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("runtime_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        inspector = sa.inspect(bind)
        tables.add("case_runs")
    case_indexes = {item["name"] for item in inspector.get_indexes("case_runs")}
    if "ix_case_runs_job_id" not in case_indexes:
        op.create_index("ix_case_runs_job_id", "case_runs", ["job_id"])
    if "ix_case_runs_project_meeting" not in case_indexes:
        op.create_index("ix_case_runs_project_meeting", "case_runs", ["project_id", "meeting_id"])

    if "evidence_claims" not in tables:
        op.create_table(
        "evidence_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("case_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("claim_key", sa.String(160), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("source_kind", sa.String(80), nullable=False),
        sa.Column("source_priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extraction_pass", sa.String(100), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("region_json", sa.JSON(), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="accepted"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        inspector = sa.inspect(bind)
        tables.add("evidence_claims")
    evidence_indexes = {item["name"] for item in inspector.get_indexes("evidence_claims")}
    if "ix_evidence_claims_run_key" not in evidence_indexes:
        op.create_index("ix_evidence_claims_run_key", "evidence_claims", ["run_id", "claim_key"])

    if "fact_decisions" not in tables:
        op.create_table(
        "fact_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("case_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fact_key", sa.String(160), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="missing"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("decision_method", sa.String(100), nullable=False, server_default="source_priority"),
        sa.Column("claim_ids_json", sa.JSON(), nullable=False),
        sa.Column("conflict_json", sa.JSON(), nullable=True),
        sa.Column("source_summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("run_id", "fact_key", name="uq_fact_decision_run_key"),
        )
        inspector = sa.inspect(bind)
        tables.add("fact_decisions")
    decision_indexes = {item["name"] for item in inspector.get_indexes("fact_decisions")}
    if "ix_fact_decisions_run_key" not in decision_indexes:
        op.create_index("ix_fact_decisions_run_key", "fact_decisions", ["run_id", "fact_key"])

    if "learning_proposals" not in tables:
        op.create_table(
        "learning_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=True),
        sa.Column("feedback_text", sa.Text(), nullable=False),
        sa.Column("original_conclusion", sa.Text(), nullable=True),
        sa.Column("proposed_patch_json", sa.JSON(), nullable=False),
        sa.Column("required_case_ids", sa.JSON(), nullable=False),
        sa.Column("regression_plan_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        inspector = sa.inspect(bind)
        tables.add("learning_proposals")
    learning_indexes = {item["name"] for item in inspector.get_indexes("learning_proposals")}
    if "ix_learning_proposals_project_meeting" not in learning_indexes:
        op.create_index("ix_learning_proposals_project_meeting", "learning_proposals", ["project_id", "meeting_id"])


def downgrade() -> None:
    op.drop_index("ix_learning_proposals_project_meeting", table_name="learning_proposals")
    op.drop_table("learning_proposals")
    op.drop_index("ix_fact_decisions_run_key", table_name="fact_decisions")
    op.drop_table("fact_decisions")
    op.drop_index("ix_evidence_claims_run_key", table_name="evidence_claims")
    op.drop_table("evidence_claims")
    op.drop_index("ix_case_runs_project_meeting", table_name="case_runs")
    op.drop_index("ix_case_runs_job_id", table_name="case_runs")
    op.drop_table("case_runs")
