"""
HealthRecord ORM Model — Monthly health data submitted by users.
"""

import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HealthRecord(Base):
    __tablename__ = "health_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trimester: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–40
    current_weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    bmi: Mapped[float | None] = mapped_column(Float, nullable=True)
    blood_pressure_sys: Mapped[float | None] = mapped_column(Float, nullable=True)
    blood_pressure_dia: Mapped[float | None] = mapped_column(Float, nullable=True)
    hemoglobin: Mapped[float | None] = mapped_column(Float, nullable=True)
    blood_sugar_fasting: Mapped[float | None] = mapped_column(Float, nullable=True)
    allergies: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    medical_conditions: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=list)
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, default=False)
    dietary_preference: Mapped[str] = mapped_column(
        String(20), nullable=False, default="nonveg"
    )  # veg | nonveg | eggetarian
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="health_records")
    diet_plan = relationship("DietPlan", back_populates="health_record", uselist=False)

    def __repr__(self) -> str:
        return f"<HealthRecord T{self.trimester} W{self.week_number} for {self.user_id}>"
