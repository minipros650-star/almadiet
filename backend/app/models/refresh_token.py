"""RefreshToken ORM model — hashed, rotating, revocable sessions."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from app.database import Base, GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column, relationship



class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_family", "family_id"),
        Index("ix_refresh_tokens_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256 hash of the opaque token — the raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="refresh_tokens")

    @property
    def is_active(self) -> bool:
        from datetime import datetime, timezone
        expires = self.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return self.revoked_at is None and (expires is None or expires > datetime.now(timezone.utc))
