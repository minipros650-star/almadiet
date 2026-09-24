"""meal catalog + content governance

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb():
    return pg.JSONB().with_variant(sa.JSON(), "sqlite")


def _uuid():
    return pg.UUID(as_uuid=True).with_variant(sa.CHAR(32), "sqlite")


def upgrade() -> None:
    op.create_table(
        "allergens",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.UniqueConstraint("category", name="uq_allergens_category"),
    )
    op.create_index("ix_allergens_category", "allergens", ["category"])

    op.create_table(
        "meals",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("dataset_id", sa.String(20), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_tamil", sa.String(255), nullable=True),
        sa.Column("name_malayalam", sa.String(255), nullable=True),
        sa.Column("name_kannada", sa.String(255), nullable=True),
        sa.Column("name_telugu", sa.String(255), nullable=True),
        sa.Column("region", sa.String(100), nullable=False),
        sa.Column("meal_type", sa.String(50), nullable=False),
        sa.Column("trimester_suitability", _jsonb(), nullable=True),
        sa.Column("cuisine", sa.String(100), nullable=True),
        sa.Column("calories", sa.Float(), nullable=False, server_default="0"),
        sa.Column("protein_g", sa.Float(), nullable=False, server_default="0"),
        sa.Column("carbs_g", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fat_g", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fiber_g", sa.Float(), nullable=False, server_default="0"),
        sa.Column("iron_mg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("calcium_mg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("folate_mcg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("vitamin_c_mg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sodium_mg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sugar_g", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ingredients", _jsonb(), nullable=True),
        sa.Column("serving_size", sa.String(100), nullable=True),
        sa.Column("serving_basis", sa.String(200), nullable=True),
        sa.Column("preparation_time_minutes", sa.Integer(), nullable=True),
        sa.Column("preparation_notes", sa.Text(), nullable=True),
        sa.Column("benefits", _jsonb(), nullable=True),
        sa.Column("cautions", sa.Text(), nullable=True),
        sa.Column("food_safety_notes", sa.Text(), nullable=True),
        sa.Column("best_time_to_eat", sa.String(50), nullable=True),
        sa.Column("substitutions", _jsonb(), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("is_vegetarian", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(500), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("evidence_version", sa.String(32), nullable=False, server_default="1"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer", sa.String(255), nullable=True),
        sa.Column("content_status", sa.String(20), nullable=False, server_default="REVIEW_REQUIRED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("dataset_id", name="uq_meals_dataset_id"),
        sa.CheckConstraint("calories >= 0", name="ck_meal_cal"),
        sa.CheckConstraint("protein_g >= 0 AND carbs_g >= 0 AND fat_g >= 0", name="ck_meal_macros"),
        sa.CheckConstraint("fiber_g >= 0 AND iron_mg >= 0 AND calcium_mg >= 0", name="ck_meal_micro"),
        sa.CheckConstraint("folate_mcg >= 0 AND vitamin_c_mg >= 0", name="ck_meal_micro2"),
        sa.CheckConstraint("sodium_mg >= 0 AND sugar_g >= 0", name="ck_meal_micro3"),
        sa.CheckConstraint(
            "preparation_time_minutes IS NULL OR preparation_time_minutes >= 0", name="ck_meal_prep"
        ),
        sa.CheckConstraint(
            "content_status IN ('DRAFT','REVIEW_REQUIRED','REVIEWED','PUBLISHED','RETIRED')",
            name="ck_meal_content_status",
        ),
    )
    op.create_index("ix_meals_name", "meals", ["name"])
    op.create_index("ix_meals_region", "meals", ["region"])
    op.create_index("ix_meals_content_status", "meals", ["content_status"])

    op.create_table(
        "meal_allergens",
        sa.Column("meal_id", _uuid(), sa.ForeignKey("meals.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "allergen_id",
            _uuid(),
            sa.ForeignKey("allergens.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("matched_term", sa.String(255), primary_key=True),
        sa.Column("match_type", sa.String(20), nullable=False, server_default="synonym"),
        sa.UniqueConstraint("meal_id", "allergen_id", "matched_term", name="uq_meal_allergen_term"),
    )

    op.create_table(
        "content_versions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("meal_id", _uuid(), sa.ForeignKey("meals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", _jsonb(), nullable=True),
        sa.Column("change_note", sa.String(500), nullable=True),
        sa.Column("reviewer", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_content_versions_meal", "content_versions", ["meal_id", "version"])

    op.create_table(
        "meal_images",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("meal_id", _uuid(), sa.ForeignKey("meals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_url", sa.String(500), nullable=False),
        sa.Column("prompt_used", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_meal_images_meal", "meal_images", ["meal_id"])


def downgrade() -> None:
    op.drop_table("meal_images")
    op.drop_table("content_versions")
    op.drop_table("meal_allergens")
    op.drop_table("meals")
    op.drop_table("allergens")
