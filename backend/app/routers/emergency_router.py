"""
AlmaDiet — Emergency Router
Handles emergency reporting, listing, and resolution.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.emergency import EmergencyCreate, EmergencyResponse, EmergencyResolve
from app.services.emergency_service import (
    report_emergency,
    get_emergencies,
    resolve_emergency,
)
from app.auth.jwt_handler import get_current_user

router = APIRouter(prefix="/api/emergency", tags=["Emergency"])


@router.post("/report", response_model=EmergencyResponse, status_code=status.HTTP_201_CREATED)
async def report(
    data: EmergencyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Report an emergency and get modified diet restrictions."""
    record = await report_emergency(db, current_user.id, data)
    return EmergencyResponse.model_validate(record)


@router.get("/list", response_model=list[EmergencyResponse])
async def list_emergencies(
    active_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all emergencies for the current user."""
    records = await get_emergencies(db, current_user.id, active_only=active_only)
    return [EmergencyResponse.model_validate(r) for r in records]


@router.post("/resolve", response_model=EmergencyResponse)
async def resolve(
    data: EmergencyResolve,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark an emergency as resolved."""
    record = await resolve_emergency(db, current_user.id, data.emergency_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emergency record not found",
        )
    return EmergencyResponse.model_validate(record)
