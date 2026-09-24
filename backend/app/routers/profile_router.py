"""AlmaDiet — Profile Router (/api/v1/profile).

Server-authoritative pregnancy profile:

* ``GET  /profile/completion`` — server-calculated pre-pregnancy BMI,
  gestational week/trimester derived from LMP/due date, and the exact
  list of missing fields.
* ``PATCH /profile/preferences`` — allergies (taxonomy-normalized),
  dislikes, cooking-time and budget preferences. BMI is NOT accepted
  anywhere in this API.
* ``GET/POST /profile/favorites`` — saved meals (ranking signal only).
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import get_current_user
from app.database import get_db
from app.domain.profile import (
    ProfileDataError,
    calculate_pre_pregnancy_bmi,
    derive_gestational_age,
    profile_completion_status,
)
from app.models.meal_favorite import MealFavorite
from app.models.user import User
from app.schemas.errors import ErrorCode, envelope
from app.services import audit_service, preference_service

router = APIRouter(prefix="/api/v1/profile", tags=["Profile"])


# ── Schemas ──────────────────────────────────────────────────────


class ProfileCompletionResponse(BaseModel):
    complete: bool
    missing_fields: list[str] = []
    height_cm: Optional[float] = None
    pre_pregnancy_weight_kg: Optional[float] = None
    pre_pregnancy_bmi: Optional[float] = None
    bmi_note: str = (
        "Calculated by AlmaDiet from your height and pre-pregnancy weight. "
        "It is general context only — not a diagnosis or a target."
    )
    gestational_week: Optional[int] = None
    trimester: Optional[int] = None
    gestation_basis: Optional[str] = None  # lmp | due_date
    region: Optional[str] = None
    dietary_preference: Optional[str] = None
    declared_allergies: list[str] = []


class PreferencesUpdate(BaseModel):
    """PATCH semantics. BMI fields are rejected by extra=forbid."""

    model_config = {"extra": "forbid"}

    allergies: Optional[list[str]] = Field(None, max_length=30)
    dietary_preference: Optional[str] = Field(
        None, pattern="^(veg|nonveg|eggetarian)$"
    )
    disliked_ingredients: Optional[list[str]] = Field(None, max_length=50)
    cooking_time_preference: Optional[str] = Field(
        None, pattern="^(quick|moderate|relaxed)$"
    )
    budget_preference: Optional[str] = Field(None, pattern="^(low|medium|high)$")


class PreferencesResponse(BaseModel):
    allergies: list[str] = []
    dietary_preference: Optional[str] = None
    disliked_ingredients: list[str] = []
    cooking_time_preference: Optional[str] = None
    budget_preference: Optional[str] = None


class FavoriteToggle(BaseModel):
    model_config = {"extra": "forbid"}

    meal_id: uuid.UUID


class FavoriteStatus(BaseModel):
    meal_id: uuid.UUID
    is_favorite: bool


# ── Endpoints ────────────────────────────────────────────────────


def _completion_payload(user: User) -> dict:
    base = profile_completion_status(
        height_cm=user.height_cm,
        pre_pregnancy_weight_kg=user.pre_pregnancy_weight_kg,
        lmp_date=user.lmp_date,
        due_date=user.due_date,
        region=user.region,
        dietary_preference=user.dietary_preference,
        allergies=user.declared_allergies,
    )
    gestation_basis = None
    try:
        gestation = derive_gestational_age(
            lmp_date=user.lmp_date, due_date=user.due_date
        )
        base["gestational_week"] = gestation["week"]
        base["trimester"] = gestation["trimester"]
        gestation_basis = gestation["basis"]
    except ProfileDataError:
        pass  # reported via missing_fields / incomplete
    return {**base, "gestation_basis": gestation_basis}


@router.get("/completion", response_model=ProfileCompletionResponse)
async def get_completion(
    current_user: User = Depends(get_current_user),
):
    return ProfileCompletionResponse(
        complete=_completion_payload(current_user)["complete"],
        missing_fields=_completion_payload(current_user)["missing_fields"],
        height_cm=current_user.height_cm,
        pre_pregnancy_weight_kg=current_user.pre_pregnancy_weight_kg,
        pre_pregnancy_bmi=_completion_payload(current_user)["pre_pregnancy_bmi"],
        gestational_week=_completion_payload(current_user)["gestational_week"],
        trimester=_completion_payload(current_user)["trimester"],
        gestation_basis=_completion_payload(current_user)["gestation_basis"],
        region=current_user.region,
        dietary_preference=current_user.dietary_preference,
        declared_allergies=list(current_user.declared_allergies or []),
    )


@router.patch("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    data: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await preference_service.update_preferences(
            db,
            current_user,
            allergies=data.allergies,
            dietary_preference=data.dietary_preference,
            disliked_ingredients=data.disliked_ingredients,
            cooking_time_preference=data.cooking_time_preference,
            budget_preference=data.budget_preference,
        )
    except preference_service.PreferenceValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=envelope(ErrorCode.INVALID_INPUT, str(e)),
        )
    await audit_service.record_event(
        db, audit_service.EventCodes.PROFILE_UPDATED, current_user.id, {"fields": "preferences"}
    )
    return PreferencesResponse(
        allergies=list(user.declared_allergies or []),
        dietary_preference=user.dietary_preference,
        disliked_ingredients=list(user.disliked_ingredients or []),
        cooking_time_preference=user.cooking_time_preference,
        budget_preference=user.budget_preference,
    )


@router.get("/favorites")
async def list_favorites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ids = await preference_service.list_favorites(db, current_user.id)
    return {"favorites": [str(i) for i in ids]}


@router.post("/favorites", response_model=FavoriteStatus)
async def toggle_favorite(
    data: FavoriteToggle,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_fav = await preference_service.toggle_favorite(db, current_user.id, data.meal_id)
    return FavoriteStatus(meal_id=data.meal_id, is_favorite=is_fav)
