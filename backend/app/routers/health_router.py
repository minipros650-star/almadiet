"""AlmaDiet — Health Router (/api/v1/health)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.errors import ErrorCode, envelope
from app.schemas.health import DiscussionPointsResponse, HealthRecordCreate, HealthRecordResponse
from app.services import audit_service, health_service
from app.services.health_service import ConsentRequiredError

router = APIRouter(prefix="/api/v1/health", tags=["Health Records"])


@router.post("/record", response_model=HealthRecordResponse, status_code=status.HTTP_201_CREATED)
async def submit_health_record(
    data: HealthRecordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        record = await health_service.create_health_record(db, current_user.id, data)
    except ConsentRequiredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=envelope(
                ErrorCode.CONSENT_REQUIRED,
                "Please review and accept the consent screen before saving health information.",
            ),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=envelope(ErrorCode.INVALID_INPUT, str(e)),
        )
    await audit_service.record_event(
        db, audit_service.EventCodes.HEALTH_RECORD_CREATED, current_user.id, {}
    )
    return HealthRecordResponse.model_validate(record)


@router.get("/records", response_model=list[HealthRecordResponse])
async def list_health_records(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    records = await health_service.get_health_records(db, current_user.id)
    return [HealthRecordResponse.model_validate(r) for r in records]


@router.get("/records/{record_id}", response_model=HealthRecordResponse)
async def get_health_record(
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await health_service.get_health_record_by_id(db, record_id, current_user.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=envelope(ErrorCode.NOT_FOUND, "Health record not found"),
        )
    return HealthRecordResponse.model_validate(record)


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_health_record(
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import privacy_service

    deleted = await privacy_service.delete_health_record(db, current_user.id, record_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=envelope(ErrorCode.NOT_FOUND, "Health record not found"),
        )
    return None


@router.get("/records/{record_id}/discussion-points", response_model=DiscussionPointsResponse)
async def get_discussion_points(
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Informational clinician-discussion suggestions (NOT a diagnosis)."""
    record = await health_service.get_health_record_by_id(db, record_id, current_user.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=envelope(ErrorCode.NOT_FOUND, "Health record not found"),
        )
    return DiscussionPointsResponse(
        record_id=record.id,
        suggestions=health_service.discussion_suggestions(record),
    )
