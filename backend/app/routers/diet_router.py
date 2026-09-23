"""AlmaDiet — Diet Plan Router (/api/v1/diet)."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.diet import DietPlanResponse
from app.schemas.errors import ErrorCode, envelope
from app.services import audit_service, diet_service
from app.services.health_service import ConsentRequiredError
from app.services.safety_validator import build_validator
from app.services.suggestion_service import SuggestionBlocked, generate_personalized_plan

router = APIRouter(prefix="/api/v1/diet", tags=["Diet Plans"])


class DietPlanGenerate(BaseModel):
    health_record_id: Optional[uuid.UUID] = None  # legacy path; personalized ignores it


class SwapRequest(BaseModel):
    day_index: int = Field(..., ge=1, le=7)
    slot: str = Field(..., pattern="^(breakfast|lunch|snack|dinner)$")
    current_meal_id: str = Field(..., min_length=8, max_length=64)


class FeedbackSubmit(BaseModel):
    plan_id: uuid.UUID
    feedback: str = Field(..., min_length=5, max_length=1000)
    rating: int = Field(..., ge=1, le=5)


def _validator() -> diet_service.SafetyValidator:
    return build_validator(
        production=settings.ENVIRONMENT == "production",
        config_statuses=",".join(settings.CONTENT_INCLUDE_STATUSES or []),
    )


_BLOCKED_STATUS = {
    "PROFILE_INCOMPLETE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "CLINICIAN_REVIEW_REQUIRED": status.HTTP_403_FORBIDDEN,
    "NEEDS_CLINICIAN_REVIEW": status.HTTP_403_FORBIDDEN,
    "NO_SAFE_SUGGESTION": status.HTTP_404_NOT_FOUND,
    "CONSENT_REQUIRED": status.HTTP_409_CONFLICT,
    "RANKER_CONTRACT_VIOLATION": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "MISSING_GESTATION_DATE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "CONTRADICTORY_DATES": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "INVALID_LMP": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "INVALID_DUE_DATE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "GESTATION_OUT_OF_RANGE": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _blocked_response(exc: SuggestionBlocked) -> HTTPException:
    code = exc.details.get("blocking_code", exc.code)
    return HTTPException(
        status_code=_BLOCKED_STATUS.get(code, status.HTTP_422_UNPROCESSABLE_ENTITY),
        detail=envelope(ErrorCode.INVALID_INPUT, str(exc), details={
            "blocking_code": code,
            **{k: v for k, v in exc.details.items() if k != "blocking_code"},
        }),
    )


@router.post("/generate", response_model=DietPlanResponse, status_code=status.HTTP_201_CREATED)
async def generate_plan(
    data: DietPlanGenerate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Personalized suggestions from the server-side profile.

    Pipeline: profile completion → gestational derivation (LMP/due date)
    → consent → hard safety filter (approved meals only) → versioned BMI
    policy → deterministic ranking → 7-day plan. Client-sent BMI is never
    accepted; a health_record_id is accepted for backwards compatibility
    but is not used by the personalized path.
    """
    try:
        plan, _pipeline = await generate_personalized_plan(db, current_user, _validator())
    except SuggestionBlocked as e:
        raise _blocked_response(e)
    await audit_service.record_event(
        db, audit_service.EventCodes.PLAN_GENERATED, current_user.id,
        {"pipeline": "personalized"},
    )
    return DietPlanResponse.model_validate(plan)


@router.get("/plans", response_model=list[DietPlanResponse])
async def list_plans(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plans = await diet_service.get_diet_plans(db, current_user.id)
    return [DietPlanResponse.model_validate(p) for p in plans[offset: offset + limit]]


@router.get("/plans/{plan_id}", response_model=DietPlanResponse)
async def get_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await diet_service.get_diet_plan_by_id(db, plan_id, current_user.id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=envelope(ErrorCode.NOT_FOUND, "Diet plan not found"),
        )
    return DietPlanResponse.model_validate(plan)


@router.post("/plans/{plan_id}/swap", response_model=DietPlanResponse)
async def swap_meal(
    plan_id: uuid.UUID,
    data: SwapRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        plan = await diet_service.swap_meal(
            db, current_user.id, plan_id, data.day_index, data.slot,
            data.current_meal_id, _validator(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=envelope(ErrorCode.INVALID_INPUT, str(e)),
        )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=envelope(ErrorCode.NOT_FOUND, "Diet plan not found"),
        )
    await audit_service.record_event(
        db, audit_service.EventCodes.MEAL_SWAPPED, current_user.id,
        {"day": data.day_index, "slot": data.slot},
    )
    return DietPlanResponse.model_validate(plan)


@router.post("/feedback", response_model=DietPlanResponse)
async def add_feedback(
    data: FeedbackSubmit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        plan = await diet_service.submit_feedback(
            db, current_user.id, data.plan_id, data.feedback, data.rating
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=envelope(ErrorCode.NOT_FOUND, str(e)),
        )
    return DietPlanResponse.model_validate(plan)
