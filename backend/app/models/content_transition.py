"""ContentTransition ORM model — immutable ledger of content state changes.

Every move of a meal between content states is recorded here with the actor
identity derived from the validated session token, the previous and new state,
the source/version the decision was made against, and the reviewer's rationale.

The table is append-only in practice and carries RLS with no client policies:
it is a governance record, not client data.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, GUID


class ContentTransition(Base):
    __tablename__ = "content_transitions"
    __table_args__ = (
        CheckConstraint(
            "to_status IN ('DRAFT','REVIEW_REQUIRED','REVIEWED','PUBLISHED','RETIRED')",
            name="ck_content_transitions_to_status",
        ),
        Index("ix_content_transitions_meal_created", "meal_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    meal_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meals.id", ondelete="CASCADE"), nullable=False
    )

    # ── Actor (always derived server-side from the validated token) ──
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── State change ────────────────────────────────────────────────
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)

    # ── Provenance snapshot taken at decision time ──────────────────
    source_snapshot: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    meal = relationship("Meal")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ContentTransition {self.from_status}->{self.to_status} meal={self.meal_id}>"
