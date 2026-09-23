"""AlmaDiet — Consent Router (/api/v1/consent)."""

from __future__ import annotations

import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import get_current_user
from app.database import get_db
from app.models.consent import Consent, CURRENT_CONSENT_VERSION
from app.models.user import User
from app.services import audit_service

router = APIRouter(prefix="/api/v1/consent", tags=["Consent"])


class ConsentAccept(BaseModel):
    consent_version: str = Field(..., min_length=4, max_length=32)


class ConsentStatus(BaseModel):
    accepted: bool
    consent_version: Optional[str] = None
    accepted_at: Optional[str] = None
    current_version: str = CURRENT_CONSENT_VERSION


@router.post("", status_code=201)
@router.post("/", include_in_schema=False)
async def accept_consent(
    data: ConsentAccept,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    consent = Consent(
        user_id=current_user.id,
        consent_version=data.consent_version,
        ip_hash=hashlib.sha256(ip.encode()).hexdigest()[:32],
    )
    db.add(consent)
    await db.flush()
    await audit_service.record_event(
        db, audit_service.EventCodes.CONSENT_ACCEPTED, current_user.id,
        {"version": data.consent_version},
    )
    return {
        "accepted": True,
        "consent_version": data.consent_version,
        "accepted_at": consent.accepted_at.isoformat() if consent.accepted_at else None,
    }


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
