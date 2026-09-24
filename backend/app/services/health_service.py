"""AlmaDiet — Health service.

Records user-entered health data. The app does NOT interpret values as
diagnoses: out-of-range values produce neutral clinician-discussion
suggestions only (docs/CLINICAL_SAFETY.md §4). Missing values stay missing
(no fabricated defaults — SR-7).
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.gestational import validate_gestational_age
from app.domain.health_signals import discussion_messages
from app.models.consent import Consent, CURRENT_CONSENT_VERSION
from app.models.health_record import HealthRecord
from app.models.user import User
from app.schemas.errors import ErrorCode
from app.schemas.health import HealthRecordCreate


class ConsentRequiredError(Exception):
    """Raised when a current-version consent is missing."""

    def __init__(self) -> None:
        self.code = ErrorCode.CONSENT_REQUIRED
        super().__init__("Consent is required before saving health information")


class AllergenValidationError(ValueError):
    pass


async def has_current_consent(db: AsyncSession, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(Consent)
        .where(Consent.user_id == user_id, Consent.consent_version == CURRENT_CONSENT_VERSION)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def normalize_allergies(raw: Optional[list[str]]) -> list[str]:
    """Normalize free-text allergies to known category codes.

    Uses the domain taxonomy: 'peanut'/'groundnut'/'peanut butter' all map to
    the single `peanut` category so filtering cannot miss synonyms.
    """
    from app.domain.allergens import AllergenCategory, match_ingredient

    valid = {c.value for c in AllergenCategory}
    normalized: list[str] = []
    for item in raw or []:
        token = str(item).strip().lower()
        if not token:
            continue
        if token in valid:
            if token not in normalized:
                normalized.append(token)
            continue
        matched = match_ingredient(token)
        for code in matched:
            if code not in normalized:
                normalized.append(code)
        if not matched:
            # Unknown term → keep under `other` rather than silently dropping.
            if AllergenCategory.OTHER.value not in normalized:
                normalized.append(AllergenCategory.OTHER.value)
    return normalized


def validate_condition_codes(raw: Optional[list[str]]) -> list[str]:
    from app.domain.conditions import VALID_CONDITION_CODES

    codes: list[str] = []
    for item in raw or []:
        token = str(item).strip().lower()
        if not token:
            continue
        if token in VALID_CONDITION_CODES and token not in codes:
            codes.append(token)
    return codes


async def create_health_record(
    db: AsyncSession, user_id: uuid.UUID, data: HealthRecordCreate
) -> HealthRecord:
    # Consent gate (server-side; TESTED).
    if not await has_current_consent(db, user_id):
        raise ConsentRequiredError()

    # Centralized trimester/week consistency (backend gate; TESTED).
    validate_gestational_age(data.trimester, data.week_number)

    user = await db.get(User, user_id)

    bmi = data.bmi
    if bmi is None and user and user.height_cm:
        height_m = user.height_cm / 100.0
        bmi = round(data.current_weight_kg / (height_m ** 2), 1)

    record = HealthRecord(
        user_id=user_id,
        trimester=data.trimester,
        week_number=data.week_number,
        current_weight_kg=data.current_weight_kg,
        bmi=bmi,
        # Never invent values the user did not provide.
        blood_pressure_sys=data.blood_pressure_sys,
        blood_pressure_dia=data.blood_pressure_dia,
        hemoglobin=data.hemoglobin,
        blood_sugar_fasting=data.blood_sugar_fasting,
        allergies=normalize_allergies(data.allergies),
        medical_conditions=validate_condition_codes(data.medical_conditions),
        is_vegetarian=data.dietary_preference == "veg",
        dietary_preference=data.dietary_preference,
        notes=data.notes,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def get_health_records(db: AsyncSession, user_id: uuid.UUID) -> list[HealthRecord]:
    result = await db.execute(
        select(HealthRecord)
        .where(HealthRecord.user_id == user_id)
        .order_by(HealthRecord.recorded_at.desc())
    )
    return list(result.scalars().all())


async def get_health_record_by_id(
    db: AsyncSession, record_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[HealthRecord]:
    result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id == record_id, HealthRecord.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


def discussion_suggestions(record: HealthRecord) -> list[str]:
    """Neutral, non-diagnostic clinician-discussion suggestions."""
    return discussion_messages(record)
