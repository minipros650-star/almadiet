"""Migration 0004 — personalized suggestions foundation.

Adds:
  * users: server-derived profile fields (pre_pregnancy_bmi,
    gestational_week, trimester, profile_complete) + optional ranking
    preferences (declared_allergies, dietary_preference,
    disliked_ingredients, cooking_time_preference, budget_preference)
  * meals: reviewer metadata (approved_at, approved_by, retired_at) and
    clinician_review_required flag; catalog_version
  * nutrition_policy_approvals: explicit clinician sign-off per policy
    version (never seeded automatically)
  * meal_favorites: user-saved meals (ranking signal)
  * diet_plans: policy_version, catalog_version, ranking_version

Seeded/existing meals stay pending review — this migration does NOT
promote any content. Uses batch_alter_table so the migration runs on
both PostgreSQL and SQLite (tests).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb():
    return pg.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    # ── users ────────────────────────────────────────────────
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("pre_pregnancy_bmi", sa.Float(), nullable=True))
        batch.add_column(sa.Column("gestational_week", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("trimester", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("profile_complete", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("declared_allergies", _jsonb(), nullable=True))
        batch.add_column(sa.Column("dietary_preference", sa.String(20), nullable=True))
        batch.add_column(sa.Column("disliked_ingredients", _jsonb(), nullable=True))
        batch.add_column(sa.Column("cooking_time_preference", sa.String(20), nullable=True))
        batch.add_column(sa.Column("budget_preference", sa.String(20), nullable=True))
        batch.create_check_constraint(
            "ck_users_prepreg_bmi",
            "pre_pregnancy_bmi IS NULL OR (pre_pregnancy_bmi BETWEEN 10 AND 60)",
        )
        batch.create_check_constraint(
            "ck_users_gest_week",
            "gestational_week IS NULL OR (gestational_week BETWEEN 1 AND 42)",
        )
        batch.create_check_constraint(
            "ck_users_trimester", "trimester IS NULL OR (trimester BETWEEN 1 AND 3)"
        )
        batch.create_check_constraint(
            "ck_users_diet_pref",
            "dietary_preference IS NULL OR dietary_preference IN ('veg','nonveg','eggetarian')",
        )
        batch.create_check_constraint(
            "ck_users_cook_pref",
            "cooking_time_preference IS NULL OR cooking_time_preference IN ('quick','moderate','relaxed')",
        )
        batch.create_check_constraint(
            "ck_users_budget_pref",
            "budget_preference IS NULL OR budget_preference IN ('low','medium','high')",
        )

    # ── meals: reviewer metadata ─────────────────────────────
    with op.batch_alter_table("meals") as batch:
        batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("approved_by", sa.String(255), nullable=True))
        batch.add_column(sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column(
                "clinician_review_required", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.add_column(
            sa.Column("catalog_version", sa.String(32), nullable=False, server_default="1")
        )
    op.create_index(
        "ix_meals_content_status_version", "meals", ["content_status", "catalog_version"]
    )

    # ── nutrition_policy_approvals ───────────────────────────
    op.create_table(
        "nutrition_policy_approvals",
        sa.Column("id", pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"), primary_key=True),
        sa.Column("policy_id", sa.String(100), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("approved_by", sa.String(255), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("policy_id", "policy_version", name="uq_policy_version_approval"),
    )
    op.create_index("ix_npa_policy", "nutrition_policy_approvals", ["policy_id", "policy_version"])

    # ── meal_favorites ───────────────────────────────────────
    op.create_table(
        "meal_favorites",
        sa.Column("user_id", pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"), primary_key=True),
        sa.Column("meal_id", pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meal_id"], ["meals.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "meal_id", name="uq_user_meal_favorite"),
    )

    # ── diet_plans: pipeline provenance ──────────────────────
    with op.batch_alter_table("diet_plans") as batch:
        batch.add_column(sa.Column("policy_version", sa.String(32), nullable=True))
        batch.add_column(sa.Column("catalog_version", sa.String(32), nullable=True))
        batch.add_column(sa.Column("ranking_version", sa.String(32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("diet_plans") as batch:
        batch.drop_column("ranking_version")
        batch.drop_column("catalog_version")
        batch.drop_column("policy_version")
    op.drop_table("meal_favorites")
    op.drop_index("ix_npa_policy", table_name="nutrition_policy_approvals")
    op.drop_table("nutrition_policy_approvals")
    op.drop_index("ix_meals_content_status_version", table_name="meals")
    with op.batch_alter_table("meals") as batch:
        batch.drop_column("catalog_version")
        batch.drop_column("clinician_review_required")
        batch.drop_column("retired_at")
        batch.drop_column("approved_by")
        batch.drop_column("approved_at")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_users_budget_pref")
        batch.drop_constraint("ck_users_cook_pref")
        batch.drop_constraint("ck_users_diet_pref")
        batch.drop_constraint("ck_users_trimester")
        batch.drop_constraint("ck_users_gest_week")
        batch.drop_constraint("ck_users_prepreg_bmi")
        batch.drop_column("budget_preference")
        batch.drop_column("cooking_time_preference")
        batch.drop_column("disliked_ingredients")
        batch.drop_column("dietary_preference")
        batch.drop_column("declared_allergies")
        batch.drop_column("profile_complete")
        batch.drop_column("trimester")
        batch.drop_column("gestational_week")
        batch.drop_column("pre_pregnancy_bmi")
