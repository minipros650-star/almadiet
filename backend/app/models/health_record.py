"""HealthRecord ORM model — hardened with gestational CHECK constraint."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from app.database import Base, GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column, relationship



class HealthRecord(Base):
    __tablename__ = "health_records"
    __table_args__ = (
        CheckConstraint("trimester BETWEEN 1 AND 3", name="ck_hr_trimester"),
        CheckConstraint("week_number BETWEEN 1 AND 42", name="ck_hr_week"),
        # Trimester/week consistency — mirrors app.domain.gestational.
        CheckConstraint(
            "(trimester = 1 AND week_number BETWEEN 1 AND 13) OR "
            "(trimester = 2 AND week_number BETWEEN 14 AND 26) OR "
            "(trimester = 3 AND week_number BETWEEN 27 AND 42)",
            name="ck_hr_trimester_week_consistent",
        ),
        CheckConstraint("current_weight_kg BETWEEN 30 AND 200", name="ck_hr_weight"),
        CheckConstraint("bmi IS NULL OR (bmi BETWEEN 10 AND 60)", name="ck_hr_bmi"),
        CheckConstraint("blood_pressure_sys IS NULL OR (blood_pressure_sys BETWEEN 60 AND 250)", name="ck_hr_bpsys"),
        CheckConstraint("blood_pressure_dia IS NULL OR (blood_pressure_dia BETWEEN 40 AND 150)", name="ck_hr_bpdia"),
        CheckConstraint("hemoglobin IS NULL OR (hemoglobin BETWEEN 3 AND 20)", name="ck_hr_hb"),
        CheckConstraint("blood_sugar_fasting IS NULL OR (blood_sugar_fasting BETWEEN 20 AND 600)", name="ck_hr_bs"),
        CheckConstraint(
            "dietary_preference IN ('veg','nonveg','eggetarian')",
            name="ck_hr_dietpref",
        ),
        Index("ix_hr_user_time", "user_id", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    trimester: Mapped[int] = mapped_column(Integer, nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    current_weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    bmi: Mapped[float | None] = mapped_column(Float, nullable=True)
    blood_pressure_sys: Mapped[float | None] = mapped_column(Float, nullable=True)
    blood_pressure_dia: Mapped[float | None] = mapped_column(Float, nullable=True)
    hemoglobin: Mapped[float | None] = mapped_column(Float, nullable=True)
    blood_sugar_fasting: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Lists of AllergenCategory codes (validated at schema level)
    allergies: Mapped[list | None] = mapped_column(JSONType, nullable=True, default=list)
    # Lists of MedicalCondition codes
    medical_conditions: Mapped[list | None] = mapped_column(JSONType, nullable=True, default=list)
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dietary_preference: Mapped[str] = mapped_column(String(20), nullable=False, default="nonveg")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="health_records")
    diet_plans = relationship("DietPlan", back_populates="health_record")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HealthRecord T{self.trimester} W{self.week_number} user={self.user_id}>"
