"""NutritionPolicyApproval ORM model — clinician sign-off gate for policies.

A policy version may only influence reference values when an approval
record exists (approved_by + approved_at). No auto-approval ever happens:
seeding never creates these rows.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from app.database import Base, GUID
from sqlalchemy.orm import Mapped, mapped_column


class NutritionPolicyApproval(Base):
    __tablename__ = "nutrition_policy_approvals"
    __table_args__ = (
        UniqueConstraint("policy_id", "policy_version", name="uq_policy_version_approval"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NutritionPolicyApproval {self.policy_id}@{self.policy_version}>"
