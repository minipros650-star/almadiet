"""AuditLog ORM model — security/safety event trail.

context must NEVER contain health values, allergy lists, or plan contents —
only ids, event codes, and coarse metadata (enforced by service layer).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from app.database import Base, GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column



class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_user_time", "user_id", "created_at"),
        Index("ix_audit_event", "event_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_code: Mapped[str] = mapped_column(String(64), nullable=False)
    context: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
