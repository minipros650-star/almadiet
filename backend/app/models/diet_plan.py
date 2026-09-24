"""DietPlan ORM model — genuine 7-day plan structure.

`days` JSONB = list of exactly 7 objects:
    {"day_index": 1..7, "meals": {"breakfast": [MealCard], "lunch": [...],
                                  "snack": [...], "dinner": [...]}}
MealCard carries nutrition, allergens, why_suggested explanations, source,
evidence_version and content_status at snapshot time.

Removed from the legacy schema: `is_emergency_plan` and emergency meal
snapshots (feature replaced by information-only urgent help).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, Integer, ForeignKey, String, func
from app.database import Base, GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column, relationship



class DietPlan(Base):
    __tablename__ = "diet_plans"
    __table_args__ = (
        CheckConstraint("trimester BETWEEN 1 AND 3", name="ck_plan_trimester"),
        CheckConstraint("week_number BETWEEN 1 AND 42", name="ck_plan_week"),
        CheckConstraint("plan_end >= plan_start", name="ck_plan_dates"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    health_record_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("health_records.id", ondelete="SET NULL"), nullable=True
    )
    trimester: Mapped[int] = mapped_column(Integer, nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)

    days: Mapped[list | None] = mapped_column(JSONType, nullable=False, default=list)

    # Reference targets shown as context — explicitly NOT prescriptions.
    target_calories: Mapped[float] = mapped_column(Float, nullable=False, default=2200)
    target_protein: Mapped[float] = mapped_column(Float, nullable=False, default=75)
    target_iron: Mapped[float] = mapped_column(Float, nullable=False, default=30)
    target_calcium: Mapped[float] = mapped_column(Float, nullable=False, default=1000)

    # Deterministic explanations + safety notes attached to the plan.
    dietary_alerts: Mapped[list | None] = mapped_column(JSONType, nullable=True, default=list)
    exclusions_applied: Mapped[dict | None] = mapped_column(JSONType, nullable=True, default=dict)
    user_corrections: Mapped[list | None] = mapped_column(JSONType, nullable=True, default=list)

    plan_start: Mapped[date] = mapped_column(Date, nullable=False)
    plan_end: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # ── Provenance of the suggestion pipeline (determinism keys) ──
    policy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    catalog_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ranking_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    user = relationship("User", back_populates="diet_plans")
    health_record = relationship("HealthRecord", back_populates="diet_plans")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DietPlan T{self.trimester} W{self.week_number} user={self.user_id}>"
