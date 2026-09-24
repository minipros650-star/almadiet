"""AlmaDiet — Meal Router (/api/v1/meals).

Route ordering matters (TEST 8/9): the static `/images/all` route is
declared BEFORE the parameterized `/{meal_id}` route, and `/{meal_id}`
accepts UUIDs only.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.content_authz import ContentActor, optional_content_actor
from app.auth.jwt_handler import get_current_user
from app.config import settings
from app.database import get_db
from app.domain.content_visibility import PUBLISHED, is_readable, readable_statuses
from app.models.meal import Meal
from app.models.meal_image import MealImage
from app.schemas.diet import MealResponse
from app.schemas.errors import ErrorCode, envelope
from app.services.meal_service import get_meal_by_id, get_meals

router = APIRouter(prefix="/api/v1/meals", tags=["Meals"])


@router.get("", response_model=list[MealResponse])
async def list_meals(
    region: Optional[str] = Query(None, max_length=100),
    trimester: Optional[int] = Query(None, ge=1, le=3),
    meal_type: Optional[str] = Query(None, max_length=50),
    is_vegetarian: Optional[bool] = Query(None),
    exclude_allergen: Optional[list[str]] = Query(None, description="Allergen category codes to exclude"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    actor: ContentActor | None = Depends(optional_content_actor),
    db: AsyncSession = Depends(get_db),
):
    trimester_str = None
    if trimester is not None:
        trimester_str = {1: "First", 2: "Second", 3: "Third"}.get(trimester)

    meals = await get_meals(
        db,
        region=region,
        trimester=trimester_str,
        meal_type=meal_type,
        is_vegetarian=is_vegetarian,
        # Ordinary callers are pinned to PUBLISHED; only content staff may
        # list their working set. Never trust configuration alone here.
        include_statuses=readable_statuses(
            settings.CONTENT_INCLUDE_STATUSES, actor is not None
        ),
        limit=limit,
        offset=offset,
    )

    if exclude_allergen:
        excluded = {a.strip().lower() for a in exclude_allergen}
        meals = [m for m in meals if not (set(m.allergens or []) & excluded)]

    return [MealResponse.model_validate(m) for m in meals]


# ── Static route declared BEFORE /{meal_id} (TEST 8) ─────────────────────
@router.get("/images/all")
async def list_images(
    current_user=Depends(get_current_user),
    actor: ContentActor | None = Depends(optional_content_actor),
    db: AsyncSession = Depends(get_db),
):
    """List cached meal image metadata (requires authentication).

    Image rows are joined to their meal so unreviewed content cannot be
    enumerated through this endpoint by meal id.
    """
    result = await db.execute(
        select(MealImage, Meal.content_status)
        .join(Meal, Meal.id == MealImage.meal_id)
        .order_by(MealImage.generated_at.desc())
        .limit(200)
    )
    rows = result.all()
    if actor is None:
        rows = [r for r in rows if str(r[1] or "").upper() == PUBLISHED]
    return [
        {
            "id": str(img.id),
            "meal_id": str(img.meal_id),
            "image_url": img.image_url,
            "illustrative": True,
            "generated_at": img.generated_at.isoformat() if img.generated_at else None,
        }
        for img, _status in rows
    ]


@router.get("/{meal_id}", response_model=MealResponse)
async def get_meal(
    meal_id: uuid.UUID,
    actor: ContentActor | None = Depends(optional_content_actor),
    db: AsyncSession = Depends(get_db),
):
    meal = await get_meal_by_id(db, meal_id)
    # Unreviewed content is indistinguishable from missing content to anyone
    # who is not content staff: a 403 here would confirm the id exists.
    if meal is None or not is_readable(meal.content_status, actor is not None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=envelope(ErrorCode.NOT_FOUND, "Meal not found"),
        )
    return MealResponse.model_validate(meal)


@router.get("/{meal_id}/image")
async def get_meal_image(
    meal_id: uuid.UUID,
    actor: ContentActor | None = Depends(optional_content_actor),
    db: AsyncSession = Depends(get_db),
):
    """Illustrative image URL — clearly labelled, never a clinical trust
    signal; recommendations work fully without it.

    The URL is derived from the meal name, so this route would otherwise
    disclose unreviewed content by name.
    """
    meal = await get_meal_by_id(db, meal_id)
    if meal is None or not is_readable(meal.content_status, actor is not None):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=envelope(ErrorCode.NOT_FOUND, "Meal not found"),
        )
    from app.services.image_service import build_image_url

    return {
        "meal_id": str(meal_id),
        "image_url": meal.image_url or build_image_url(meal.name, meal.region),
        "illustrative": True,
        "note": "Image is illustrative and may not depict the exact meal.",
    }
