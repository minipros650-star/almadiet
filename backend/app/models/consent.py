"""Consent ORM model — versioned acceptance records."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from app.database import Base, GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column, relationship


CURRENT_CONSENT_VERSION = "2026-09-v1"


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (
        Index("ix_consents_user_time", "user_id", "accepted_at"),
        # Acceptance is a fact, not an event stream: one row per (user,
        # version). This makes POST /consent idempotent instead of appending
        # a duplicate record on every tap.
        UniqueConstraint("user_id", "consent_version", name="uq_consents_user_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user = relationship("User", back_populates="consents")
