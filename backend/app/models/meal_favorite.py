"""MealFavorite ORM model — user-saved meals (ranking signal, non-clinical)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from app.database import Base, GUID
from sqlalchemy.orm import Mapped, mapped_column


class MealFavorite(Base):
    __tablename__ = "meal_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "meal_id", name="uq_user_meal_favorite"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    meal_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meals.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
