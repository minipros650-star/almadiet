"""
Meal ORM Model — Regional South Indian meals with full nutritional data.
Aligned with meals_dataset.json structure.
"""

import uuid
from sqlalchemy import String, Integer, Float, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Dataset ID like "SI001"
    dataset_id: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True, index=True)

    # ── Names (multilingual) ──────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # English
    name_tamil: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_malayalam: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_kannada: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_telugu: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Classification ────────────────────────────────────────
    region: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    meal_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # Breakfast, Lunch, Lunch Side, Snack, Beverage, Dessert, Condiment, etc.
    trimester_suitability: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=list
    )  # ["First", "Second", "Third"]

    # ── Nutrition per serving ─────────────────────────────────
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    fiber_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    iron_mg: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    calcium_mg: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    folate_mcg: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    vitamin_c_mg: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    # ── Ingredients & Preparation ─────────────────────────────
    ingredients: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # [{name, quantity}]
    serving_size: Mapped[str | None] = mapped_column(String(100), nullable=True)
    preparation_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Clinical & WHO ────────────────────────────────────────
    benefits: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)  # ["..."]
    who_alignment: Mapped[str | None] = mapped_column(Text, nullable=True)
    cautions: Mapped[str | None] = mapped_column(Text, nullable=True)
    best_time_to_eat: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── Metadata ──────────────────────────────────────────────
    allergens: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    clinically_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    images = relationship("MealImage", back_populates="meal", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Meal {self.name} ({self.region})>"
