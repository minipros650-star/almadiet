"""Allergen + MealAllergen ORM models — ingredient-level allergen metadata."""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from app.database import Base, GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.allergens import AllergenCategory


class Allergen(Base):
    __tablename__ = "allergens"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # Stable category code (AllergenCategory value)
    category: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)

    meal_links = relationship("MealAllergen", back_populates="allergen")


class MealAllergen(Base):
    """A detected allergen occurrence in a meal's ingredient list.

    `matched_term` records the ingredient that triggered the match, giving
    full traceability for safety reviews.
    """

    __tablename__ = "meal_allergens"
    __table_args__ = (
        UniqueConstraint("meal_id", "allergen_id", "matched_term", name="uq_meal_allergen_term"),
    )

    meal_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meals.id", ondelete="CASCADE"), primary_key=True
    )
    allergen_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("allergens.id", ondelete="RESTRICT"), primary_key=True
    )
    match_type: Mapped[str] = mapped_column(String(20), nullable=False, default="synonym")
    matched_term: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True)

    meal = relationship("Meal", back_populates="allergen_links")
    allergen = relationship("Allergen", back_populates="meal_links")

    @property
    def category(self) -> str:
        return self.allergen.category if self.allergen else AllergenCategory.OTHER.value
