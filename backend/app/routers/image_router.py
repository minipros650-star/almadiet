"""
AlmaDiet — Image Router (/api/v1)

Illustrative meal images only. Images are never a clinical trust signal,
never influence recommendations, and the recommendation flow works fully
when image generation or fetching fails. The static `/images/all` route is
declared BEFORE `/{meal_id}/image` so it can never be shadowed.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.image_service import (
    get_or_create_image_url,
    get_meal_image_url,
    list_generated_images,
)

router = APIRouter(prefix="/api/v1/meals", tags=["Meal Images"])


# ── STATIC ROUTE (must precede any parameterized routes) ───────
@router.get("/images/all")
async def list_images(
    current_user=Depends(_noop_user_dep := None) if False else Depends(),
):
    """List cached illustrative image URLs (static route)."""
    return await list_generated_images()


# ── PARAMETERIZED ROUTES ───────────────────────────────────────
@router.get("/{meal_id}/image")
async def get_image_url(
    meal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get an illustrative image URL for a meal (may be absent)."""
    try:
        return await get_meal_image_url(db, meal_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{meal_id}/image", status_code=status.HTTP_201_CREATED)
async def create_image_url(
    meal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get or cache an illustrative image URL for a meal."""
    try:
        return await get_or_create_image_url(db, meal_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
