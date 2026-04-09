"""
AlmaDiet — Health Router
Handles health record creation, listing, and analysis.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.health import HealthRecordCreate, HealthRecordResponse, HealthAnalysis
from app.services.health_service import (
    create_health_record,
    get_health_records,
    get_health_record_by_id,
    analyze_health,
)
from app.auth.jwt_handler import get_current_user

router = APIRouter(prefix="/api/health", tags=["Health Records"])


@router.post("/record", response_model=HealthRecordResponse, status_code=status.HTTP_201_CREATED)
async def submit_health_record(
    data: HealthRecordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a new monthly health record."""
    record = await create_health_record(db, current_user.id, data)
    return HealthRecordResponse.model_validate(record)


@router.get("/records", response_model=list[HealthRecordResponse])
async def list_health_records(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all health records for the current user."""
    records = await get_health_records(db, current_user.id)
    return [HealthRecordResponse.model_validate(r) for r in records]


@router.get("/analyze/{record_id}", response_model=HealthAnalysis)
async def analyze_health_record(
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze a health record and return clinical insights with corrections."""
    record = await get_health_record_by_id(db, record_id, current_user.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health record not found",
        )
    analysis = analyze_health(record, current_user)
    return analysis
