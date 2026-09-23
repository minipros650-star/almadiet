"""
AlmaDiet — Urgent Help Service (information-only).

Replaces the removed "emergency treatment diet" feature. This service:
  * never assesses or diagnoses,
  * never produces treatment instructions,
  * never records a "resolution",
  * only returns safety information and stores clinician-share notes.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.urgent_note import UrgentHelpNote

# Static, reviewed safety information. Wording constraints are tested:
# no "treatment"/"diagnos"/"resolved"/"cured" in user-facing strings.
DISCLAIMER = (
    "AlmaDiet cannot assess emergencies or urgent symptoms. "
    "This screen provides safety information only and is not medical advice."
)

WARNING_SIGNS = [
    "Bleeding from the vagina",
    "Severe abdominal pain or strong cramping",
    "Severe headache with vision changes",
    "Fever above 38°C (100.4°F)",
    "Reduced or no fetal movements",
    "Fluid leaking from the vagina",
    "Persistent vomiting and unable to keep fluids down",
    "Swelling of face or hands with headache",
]

CONTACT_GUIDANCE = [
    "If you think this is an emergency, call your local emergency number now.",
    "India: Emergency 112 · Ambulance 108 · Health advice 104",
    "Contact your doctor, midwife, or the nearest hospital for any urgent symptom.",
    "Take your notes and any medicines with you when you seek care.",
]

CLINICIAN_CHECKLIST = [
    "Describe your symptom and when it started",
    "Share your latest health record values (weight, BP, hemoglobin, glucose)",
    "List allergies and current medicines",
    "Ask what to watch for and when to come back",
]


async def create_note(
    db: AsyncSession, user_id: uuid.UUID, note_text: str | None, observed: list[str] | None
) -> UrgentHelpNote:
    """Store the user's observations to share with a clinician (no resolution)."""
    note = UrgentHelpNote(
        user_id=user_id,
        note_text=(note_text or "").strip() or None,
        observed_symptoms=observed or [],
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return note


async def list_notes(db: AsyncSession, user_id: uuid.UUID) -> list[UrgentHelpNote]:
    result = await db.execute(
        select(UrgentHelpNote)
        .where(UrgentHelpNote.user_id == user_id)
        .order_by(UrgentHelpNote.created_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


def urgent_info() -> dict:
    """Static information payload for the Urgent Help screen."""
    return {
        "disclaimer": DISCLAIMER,
        "warning_signs": WARNING_SIGNS,
        "contact_guidance": CONTACT_GUIDANCE,
        "clinician_checklist": CLINICIAN_CHECKLIST,
    }
