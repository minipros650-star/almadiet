"""
DietPlan ORM Model — Generated meal plans per user per health record.
"""

import uuid
from datetime import datetime, date
from sqlalchemy import String, Integer, Float, Boolean, Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DietPlan(Base):
    __tablename__ = "diet_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    health_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("health_records.id", ondelete="SET NULL"), nullable=True
    )
    trimester: Mapped[int] = mapped_column(Integer, nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    breakfast_meals: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    lunch_meals: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    dinner_meals: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    snack_meals: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    target_calories: Mapped[float] = mapped_column(Float, nullable=False, default=2200)
    target_protein: Mapped[float] = mapped_column(Float, nullable=False, default=75)
    target_iron: Mapped[float] = mapped_column(Float, nullable=False, default=35)
    target_calcium: Mapped[float] = mapped_column(Float, nullable=False, default=1200)
    dietary_alerts: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    user_corrections: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    is_emergency_plan: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_start: Mapped[date] = mapped_column(Date, nullable=False)
    plan_end: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="diet_plans")
    health_record = relationship("HealthRecord", back_populates="diet_plan")

    def __repr__(self) -> str:
        return f"<DietPlan T{self.trimester} W{self.week_number} for {self.user_id}>"
