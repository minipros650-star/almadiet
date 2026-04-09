"""
AlmaDiet — Diet Router
Handles diet plan generation, listing, and feedback.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.diet import DietPlanResponse, DietPlanGenerate, FeedbackSubmit
from app.services.diet_service import (
    generate_diet_plan,
    get_diet_plans,
    get_diet_plan_by_id,
    submit_feedback,
)
from app.auth.jwt_handler import get_current_user

router = APIRouter(prefix="/api/diet", tags=["Diet Plans"])


@router.post("/generate", response_model=DietPlanResponse, status_code=status.HTTP_201_CREATED)
async def generate_plan(
    data: DietPlanGenerate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a personalized weekly diet plan based on a health record."""
    try:
        plan = await generate_diet_plan(db, current_user.id, data.health_record_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    return DietPlanResponse.model_validate(plan)


@router.get("/plans", response_model=list[DietPlanResponse])
async def list_plans(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all diet plans for the current user."""
    plans = await get_diet_plans(db, current_user.id)
    return [DietPlanResponse.model_validate(p) for p in plans]


@router.get("/plan/{plan_id}", response_model=DietPlanResponse)
async def get_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific diet plan."""
    plan = await get_diet_plan_by_id(db, plan_id, current_user.id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet plan not found",
        )
    return DietPlanResponse.model_validate(plan)


@router.post("/feedback", response_model=DietPlanResponse)
async def add_feedback(
    data: FeedbackSubmit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback/corrections on a diet plan."""
    try:
        plan = await submit_feedback(
            db, current_user.id, data.diet_plan_id, data.feedback, data.rating
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return DietPlanResponse.model_validate(plan)
