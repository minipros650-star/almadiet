"""diet plans (7-day structure) + urgent help notes

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb():
    return pg.JSONB().with_variant(sa.JSON(), "sqlite")


def _uuid():
    return pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite")


def upgrade() -> None:
    op.create_table(
        "diet_plans",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "health_record_id",
            _uuid(),
            sa.ForeignKey("health_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trimester", sa.Integer(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("days", _jsonb(), nullable=False),
        sa.Column("target_calories", sa.Float(), nullable=False, server_default="2200"),
        sa.Column("target_protein", sa.Float(), nullable=False, server_default="75"),
        sa.Column("target_iron", sa.Float(), nullable=False, server_default="30"),
        sa.Column("target_calcium", sa.Float(), nullable=False, server_default="1000"),
        sa.Column("dietary_alerts", _jsonb(), nullable=True),
        sa.Column("exclusions_applied", _jsonb(), nullable=True),
        sa.Column("user_corrections", _jsonb(), nullable=True),
        sa.Column("plan_start", sa.Date(), nullable=False),
        sa.Column("plan_end", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("trimester BETWEEN 1 AND 3", name="ck_plan_trimester"),
        sa.CheckConstraint("week_number BETWEEN 1 AND 42", name="ck_plan_week"),
        sa.CheckConstraint("plan_end >= plan_start", name="ck_plan_dates"),
    )
    op.create_index("ix_diet_plans_user", "diet_plans", ["user_id"])

    op.create_table(
        "urgent_help_notes",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("user_id", _uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note_text", sa.Text(), nullable=True),
        sa.Column("observed_symptoms", _jsonb(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_urgent_help_notes_user", "urgent_help_notes", ["user_id"])


def downgrade() -> None:
    op.drop_table("urgent_help_notes")
    op.drop_table("diet_plans")
