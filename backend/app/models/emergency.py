"""
EmergencyRecord ORM Model — Tracks emergency cases and modified diet plans.
"""

import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EmergencyRecord(Base):
    __tablename__ = "emergency_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    emergency_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # GDM | preeclampsia | anemia | bleeding | hyperemesis | etc.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    modified_diet_restrictions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    emergency_meals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user = relationship("User", back_populates="emergencies")

    def __repr__(self) -> str:
        return f"<Emergency {self.emergency_type} for {self.user_id} active={self.is_active}>"
