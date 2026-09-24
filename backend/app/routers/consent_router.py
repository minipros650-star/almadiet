"""AlmaDiet — Consent Router (/api/v1/consent).

Acceptance is a fact per (user, version), not an event stream: posting the same
version again returns the existing record instead of appending a duplicate.
Ownership is always derived from the validated token — the request model
forbids extra fields, so a client cannot name a different user.

A database unique constraint backs the guarantee, so two concurrent requests
cannot both create a row.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import get_current_user
from app.database import get_db
from app.models.consent import Consent, CURRENT_CONSENT_VERSION
from app.models.user import User
from app.services import audit_service

router = APIRouter(prefix="/api/v1/consent", tags=["Consent"])


class ConsentAccept(BaseModel):
    """Only the version is client-supplied; the user comes from the token."""

    model_config = ConfigDict(extra="forbid")

    consent_version: str = Field(..., min_length=4, max_length=32)


class ConsentStatus(BaseModel):
    accepted: bool
    consent_version: Optional[str] = None
    accepted_at: Optional[str] = None
    current_version: str = CURRENT_CONSENT_VERSION


def _body(consent: Consent, created: bool) -> dict:
    return {
        "accepted": True,
        "consent_version": consent.consent_version,
        "accepted_at": consent.accepted_at.isoformat() if consent.accepted_at else None,
        "created": created,
    }


async def _existing(
    db: AsyncSession, user_id, consent_version: str
) -> Consent | None:
    return (
        await db.execute(
            select(Consent).where(
                Consent.user_id == user_id, Consent.consent_version == consent_version
            )
        )
    ).scalar_one_or_none()


@router.post("", status_code=201)
@router.post("/", include_in_schema=False)
async def accept_consent(
    data: ConsentAccept,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Idempotent: if this user already accepted this version, return that fact
    # unchanged (no new row, and no duplicate audit entry for the same act).
    existing = await _existing(db, current_user.id, data.consent_version)
    if existing is not None:
        return _body(existing, created=False)

    ip = request.client.host if request.client else "unknown"
    consent = Consent(
        user_id=current_user.id,
        consent_version=data.consent_version,
        ip_hash=hashlib.sha256(ip.encode()).hexdigest()[:32],
    )
    try:
        # SAVEPOINT so a lost race rolls back only this insert, never the
        # surrounding request transaction.
        async with db.begin_nested():
            db.add(consent)
            await db.flush()
    except IntegrityError:
        raced = await _existing(db, current_user.id, data.consent_version)
        if raced is None:  # pragma: no cover - constraint fired without a row
            raise
        return _body(raced, created=False)

    await audit_service.record_event(
        db, audit_service.EventCodes.CONSENT_ACCEPTED, current_user.id,
        {"version": data.consent_version},
    )
    return _body(consent, created=True)


@router.get("/current", response_model=ConsentStatus)
async def consent_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Consent)
        .where(Consent.user_id == current_user.id, Consent.consent_version == CURRENT_CONSENT_VERSION)
        .order_by(Consent.accepted_at.desc())
        .limit(1)
    )
    consent = result.scalar_one_or_none()
    return ConsentStatus(
        accepted=consent is not None,
        consent_version=consent.consent_version if consent else None,
        accepted_at=consent.accepted_at.isoformat() if consent else None,
    )
