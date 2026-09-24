"""
AlmaDiet — Privacy Service (data export, deletion).

Deletion behaviour is documented in docs/PRIVACY_AND_DATA.md and tested in
backend/tests/test_api_privacy.py.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Consent,
    DietPlan,
    HealthRecord,
    RefreshToken,
    UrgentHelpNote,
    User,
)
from app.services import audit_service


async def export_user_data(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Build the JSON export bundle for a user (no secrets included)."""
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found")

    records = (
        await db.execute(
            select(HealthRecord)
            .where(HealthRecord.user_id == user_id)
            .order_by(HealthRecord.recorded_at.desc())
        )
    ).scalars().all()
    plans = (
        await db.execute(
            select(DietPlan)
            .where(DietPlan.user_id == user_id)
            .order_by(DietPlan.created_at.desc())
        )
    ).scalars().all()
    consents = (
        await db.execute(
            select(Consent).where(Consent.user_id == user_id).order_by(Consent.accepted_at)
        )
    ).scalars().all()
    notes = (
        await db.execute(
            select(UrgentHelpNote).where(UrgentHelpNote.user_id == user_id)
        )
    ).scalars().all()

    return {
        "exported_at": None,  # filled by router (aware-UTC isoformat)
        "profile": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "phone": user.phone,
            "region": user.region,
            "language": user.language,
            "lmp_date": user.lmp_date.isoformat() if user.lmp_date else None,
            "due_date": user.due_date.isoformat() if user.due_date else None,
            "age": user.age,
            "height_cm": user.height_cm,
            "pre_pregnancy_weight_kg": user.pre_pregnancy_weight_kg,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "health_records": [
            {
                "id": str(r.id),
                "trimester": r.trimester,
                "week_number": r.week_number,
                "current_weight_kg": r.current_weight_kg,
                "bmi": r.bmi,
                "blood_pressure_sys": r.blood_pressure_sys,
                "blood_pressure_dia": r.blood_pressure_dia,
                "hemoglobin": r.hemoglobin,
                "blood_sugar_fasting": r.blood_sugar_fasting,
                "allergies": r.allergies,
                "medical_conditions": r.medical_conditions,
                "is_vegetarian": r.is_vegetarian,
                "dietary_preference": r.dietary_preference,
                "notes": r.notes,
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            }
            for r in records
        ],
        "diet_plans": [
            {
                "id": str(p.id),
                "trimester": p.trimester,
                "week_number": p.week_number,
                "plan_start": p.plan_start.isoformat() if p.plan_start else None,
                "plan_end": p.plan_end.isoformat() if p.plan_end else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in plans
        ],
        "consents": [
            {
                "consent_version": c.consent_version,
                "accepted_at": c.accepted_at.isoformat() if c.accepted_at else None,
            }
            for c in consents
        ],
        "urgent_notes": [
            {
                "id": str(n.id),
                "note_text": n.note_text,
                "observed_symptoms": n.observed_symptoms,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ],
    }


async def delete_health_record(
    db: AsyncSession, user_id: uuid.UUID, record_id: uuid.UUID
) -> bool:
    """Delete a health record owned by the user. Returns True when deleted."""
    result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id == record_id, HealthRecord.user_id == user_id
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        return False
    await db.delete(record)
    await db.flush()
    await audit_service.record_event(
        db, audit_service.EventCodes.HEALTH_RECORD_DELETED, user_id, {}
    )
    return True


async def delete_account(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """
    Hard-delete the account and all cascaded data.
    The audit trail keeps only a non-sensitive ACCOUNT_DELETED event row
    (user_id is SET NULL by FK; the event has no health content).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return False

    await db.delete(user)
    await db.flush()
    db.add(
        AuditLog(
            user_id=None,
            event_code=audit_service.EventCodes.ACCOUNT_DELETED,
            context={"deleted_user_id": str(user_id)},
        )
    )
    await db.flush()
    return True
