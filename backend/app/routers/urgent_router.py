"""AlmaDiet — Urgent Help Router (/api/v1/urgent).

Information-only. No diagnosis, no treatment, no resolution state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import audit_service, urgent_service

router = APIRouter(prefix="/api/v1/urgent", tags=["Urgent Help"])


class UrgentNoteCreate(BaseModel):
    observed_symptoms: list[str] = Field(default_factory=list, max_length=20)
    note_text: Optional[str] = Field(None, max_length=2000)


class UrgentNoteResponse(BaseModel):
    id: str
    observed_symptoms: list[str]
    note_text: Optional[str]
    created_at: Optional[str]


@router.get("/info")
async def urgent_info(current_user: User = Depends(get_current_user)):
    """Static safety information for the Urgent Help screen."""
    return urgent_service.urgent_info()


@router.post("/notes", response_model=UrgentNoteResponse, status_code=201)
async def create_note(
    data: UrgentNoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    note = await urgent_service.create_note(
        db, current_user.id, data.note_text, data.observed_symptoms
    )
    await audit_service.record_event(
        db, audit_service.EventCodes.URGENT_NOTE_CREATED, current_user.id, {}
    )
    return UrgentNoteResponse(
        id=str(note.id),
        observed_symptoms=note.observed_symptoms or [],
        note_text=note.note_text,
        created_at=note.created_at.isoformat() if note.created_at else None,
    )


@router.get("/notes", response_model=list[UrgentNoteResponse])
async def list_notes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notes = await urgent_service.list_notes(db, current_user.id)
    return [
        UrgentNoteResponse(
            id=str(n.id),
            observed_symptoms=n.observed_symptoms or [],
            note_text=n.note_text,
            created_at=n.created_at.isoformat() if n.created_at else None,
        )
        for n in notes
    ]
