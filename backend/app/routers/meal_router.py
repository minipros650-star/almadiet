"""
AlmaDiet — Meal Router
Browse and search meal data.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.diet import MealResponse
from app.services.meal_service import get_meals, get_meal_by_id
from app.services.image_service import build_image_url

router = APIRouter(prefix="/api/meals", tags=["Meals"])


def _ensure_image_url(meal) -> None:
    """Auto-populate image_url for meals that were seeded before the image fix."""
    if not meal.image_url:
        meal.image_url = build_image_url(meal.name, meal.region)


@router.get("", response_model=list[MealResponse])
async def list_meals(
    region: Optional[str] = Query(None, description="Filter by region: kerala, tamilnadu, karnataka, andhra"),
    trimester: Optional[int] = Query(None, ge=1, le=3, description="Filter by trimester suitability"),
    meal_type: Optional[str] = Query(None, description="Filter: breakfast, lunch, dinner, snack"),
    is_vegetarian: Optional[bool] = Query(None, description="Filter vegetarian meals"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Browse meals with optional filters."""
    # Convert trimester int → string for JSONB query
    trimester_str = None
    if trimester is not None:
        trimester_str = {1: "First", 2: "Second", 3: "Third"}.get(trimester)

    meals = await get_meals(
        db,
        region=region,
        trimester=trimester_str,
        meal_type=meal_type,
        is_vegetarian=is_vegetarian,
        limit=limit,
        offset=offset,
    )
    for m in meals:
        _ensure_image_url(m)
    return [MealResponse.model_validate(m) for m in meals]


@router.get("/{meal_id}", response_model=MealResponse)
async def get_meal(
    meal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information about a specific meal."""
    meal = await get_meal_by_id(db, meal_id)
    if meal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meal not found",
        )
    _ensure_image_url(meal)
    return MealResponse.model_validate(meal)
