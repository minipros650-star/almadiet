"""ContentVersion ORM model — governance audit trail for meal content."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from app.database import Base, GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column, relationship



class ContentVersion(Base):
    __tablename__ = "content_versions"
    __table_args__ = (Index("ix_content_versions_meal", "meal_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    meal_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meals.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    change_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meal = relationship("Meal")
