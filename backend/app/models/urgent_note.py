"""UrgentHelpNote ORM model — clinician-share observations.

Deliberately NO is_active / resolved_at columns: the app never records that
an urgent situation is resolved (CLINICAL_SAFETY SR-5).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from app.database import Base, GUID, JSONType
from sqlalchemy.orm import Mapped, mapped_column, relationship



class UrgentHelpNote(Base):
    __tablename__ = "urgent_help_notes"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_symptoms: Mapped[list | None] = mapped_column(JSONType, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="urgent_notes")
