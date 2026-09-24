"""ContentRoleGrant ORM model — backend-controlled review/publish authority.

One row per (user, role). Revocation stamps ``revoked_at`` and clears the
grant; the row is kept so the grant history is auditable. Rows are written
ONLY by the backend service connection (via scripts/bootstrap_content_role.py)
— the table carries RLS with no client policies, so an authenticated client
can neither read nor write it through PostgREST.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, GUID


class ContentRoleGrant(Base):
    __tablename__ = "content_role_grants"
    __table_args__ = (
        CheckConstraint(
            "role IN ('REVIEWER','PUBLISHER')", name="ck_content_role_grants_role"
        ),
        UniqueConstraint("user_id", "role", name="uq_content_role_grants_user_role"),
        Index("ix_content_role_grants_role", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    # Who granted it. Nullable because the first grant is a documented manual
    # bootstrap performed directly against the database.
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_by_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:  # pragma: no cover
        state = "revoked" if self.revoked_at else "active"
        return f"<ContentRoleGrant {self.role} user={self.user_id} {state}>"
