"""Meal ORM model — structured metadata + content governance provenance.

Removed from the legacy schema: `clinically_approved` (was hardcoded true
with no review) and `who_alignment` (unsourced claims). Added: source,
source_url, evidence_version, reviewed_at, reviewer, content_status,
sodium/sugar, serving_basis, food_safety_notes, cuisine.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Integer, String, Text, func
from app.database import Base, GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.content_state import ContentStatus


class Meal(Base):
    __tablename__ = "meals"
    __table_args__ = (
        CheckConstraint("calories >= 0", name="ck_meal_cal"),
        CheckConstraint("protein_g >= 0 AND carbs_g >= 0 AND fat_g >= 0", name="ck_meal_macros"),
        CheckConstraint("fiber_g >= 0 AND iron_mg >= 0 AND calcium_mg >= 0", name="ck_meal_micro"),
        CheckConstraint("folate_mcg >= 0 AND vitamin_c_mg >= 0", name="ck_meal_micro2"),
        CheckConstraint("sodium_mg >= 0 AND sugar_g >= 0", name="ck_meal_micro3"),
        CheckConstraint(
            "preparation_time_minutes IS NULL OR preparation_time_minutes >= 0",
            name="ck_meal_prep",
        ),
        CheckConstraint(
            "content_status IN ('DRAFT','REVIEW_REQUIRED','REVIEWED','PUBLISHED','RETIRED')",
            name="ck_meal_content_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)

    # ── Names (multilingual) ─────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name_tamil: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_malayalam: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_kannada: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_telugu: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Classification ───────────────────────────────────────
    region: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    meal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trimester_suitability: Mapped[list | None] = mapped_column(JSONType, nullable=True, default=list)
    cuisine: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Nutrition per serving ────────────────────────────────
    calories: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    fiber_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    iron_mg: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    calcium_mg: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    folate_mcg: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    vitamin_c_mg: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    sodium_mg: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    sugar_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    # ── Ingredients & preparation ────────────────────────────
    ingredients: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    serving_size: Mapped[str | None] = mapped_column(String(100), nullable=True)
    serving_basis: Mapped[str | None] = mapped_column(String(200), nullable=True)
    preparation_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preparation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Safety & notes ───────────────────────────────────────
    benefits: Mapped[list | None] = mapped_column(JSONType, nullable=True, default=list)
    cautions: Mapped[str | None] = mapped_column(Text, nullable=True)
    food_safety_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    best_time_to_eat: Mapped[str | None] = mapped_column(String(50), nullable=True)
    substitutions: Mapped[list | None] = mapped_column(JSONType, nullable=True, default=list)

    # ── Metadata ─────────────────────────────────────────────
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Content governance (replaces clinically_approved) ────
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clinician_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    catalog_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    content_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ContentStatus.REVIEW_REQUIRED.value, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    images = relationship("MealImage", back_populates="meal", cascade="all, delete-orphan")
    allergen_links = relationship("MealAllergen", back_populates="meal", cascade="all, delete-orphan")

    @property
    def allergens(self) -> list[str]:
        """Detected allergen category codes (derived from ingredient links)."""
        codes: list[str] = []
        for link in (self.allergen_links or []):
            code = link.category
            if code and code not in codes:
                codes.append(code)
        return codes

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Meal {self.name} [{self.content_status}]>"
