"""initial schema — users, consents, refresh_tokens, health_records, audit_logs

Revision ID: 0001
Revises:
Create Date: 2026-09-22
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb():
    """JSONB on Postgres, JSON elsewhere (SQLite tests)."""
    try:
        op.get_bind().execute(sa.text("SELECT 1"))
    except Exception:  # pragma: no cover
        pass
    return pg.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    users = op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("region", sa.String(20), nullable=False, server_default="kerala"),
        sa.Column("language", sa.String(5), nullable=False, server_default="en"),
        sa.Column("lmp_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("pre_pregnancy_weight_kg", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("age IS NULL OR (age BETWEEN 14 AND 55)", name="ck_users_age"),
        sa.CheckConstraint("height_cm IS NULL OR (height_cm BETWEEN 100 AND 250)", name="ck_users_height"),
        sa.CheckConstraint(
            "pre_pregnancy_weight_kg IS NULL OR (pre_pregnancy_weight_kg BETWEEN 30 AND 200)",
            name="ck_users_prepreg_weight",
        ),
        sa.CheckConstraint(
            "region IN ('kerala','tamilnadu','karnataka','andhra')", name="ck_users_region"
        ),
        sa.CheckConstraint("language IN ('en','ml','ta','kn','te')", name="ck_users_language"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("family_id", pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_family", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_user", "refresh_tokens", ["user_id"])

    op.create_table(
        "consents",
        sa.Column("id", pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consent_version", sa.String(32), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ip_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_consents_user_time", "consents", ["user_id", "accepted_at"])

    op.create_table(
        "health_records",
        sa.Column("id", pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trimester", sa.Integer(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("current_weight_kg", sa.Float(), nullable=False),
        sa.Column("bmi", sa.Float(), nullable=True),
        sa.Column("blood_pressure_sys", sa.Float(), nullable=True),
        sa.Column("blood_pressure_dia", sa.Float(), nullable=True),
        sa.Column("hemoglobin", sa.Float(), nullable=True),
        sa.Column("blood_sugar_fasting", sa.Float(), nullable=True),
        sa.Column("allergies", _jsonb(), nullable=True),
        sa.Column("medical_conditions", _jsonb(), nullable=True),
        sa.Column("is_vegetarian", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dietary_preference", sa.String(20), nullable=False, server_default="nonveg"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("trimester BETWEEN 1 AND 3", name="ck_hr_trimester"),
        sa.CheckConstraint("week_number BETWEEN 1 AND 42", name="ck_hr_week"),
        sa.CheckConstraint(
            "(trimester = 1 AND week_number BETWEEN 1 AND 13) OR "
            "(trimester = 2 AND week_number BETWEEN 14 AND 26) OR "
            "(trimester = 3 AND week_number BETWEEN 27 AND 42)",
            name="ck_hr_trimester_week_consistent",
        ),
        sa.CheckConstraint("current_weight_kg BETWEEN 30 AND 200", name="ck_hr_weight"),
        sa.CheckConstraint("bmi IS NULL OR (bmi BETWEEN 10 AND 60)", name="ck_hr_bmi"),
        sa.CheckConstraint(
            "blood_pressure_sys IS NULL OR (blood_pressure_sys BETWEEN 60 AND 250)", name="ck_hr_bpsys"
        ),
        sa.CheckConstraint(
            "blood_pressure_dia IS NULL OR (blood_pressure_dia BETWEEN 40 AND 150)", name="ck_hr_bpdia"
        ),
        sa.CheckConstraint("hemoglobin IS NULL OR (hemoglobin BETWEEN 3 AND 20)", name="ck_hr_hb"),
        sa.CheckConstraint(
            "blood_sugar_fasting IS NULL OR (blood_sugar_fasting BETWEEN 20 AND 600)", name="ck_hr_bs"
        ),
        sa.CheckConstraint("dietary_preference IN ('veg','nonveg','eggetarian')", name="ck_hr_dietpref"),
    )
    op.create_index("ix_hr_user_time", "health_records", ["user_id", "recorded_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"), primary_key=True),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_code", sa.String(64), nullable=False),
        sa.Column("context", _jsonb(), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_user_time", "audit_logs", ["user_id", "created_at"])
    op.create_index("ix_audit_event", "audit_logs", ["event_code"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("health_records")
    op.drop_table("consents")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
