"""
AlmaDiet — Image Router
Endpoints for meal image URLs via Pollinations.ai (free, no API key).
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt_handler import get_current_user
from app.models.user import User
from app.services.image_service import (
    get_or_create_image_url,
    get_meal_image_url,
    list_generated_images,
)

router = APIRouter(prefix="/api/meals", tags=["Meal Images"])


@router.get("/{meal_id}/image")
async def get_image_url(
    meal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get an AI-generated image URL for a meal (instant, via Pollinations.ai)."""
    try:
        return await get_meal_image_url(db, meal_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{meal_id}/image", status_code=status.HTTP_201_CREATED)
async def create_image_url(
    meal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get or cache an image URL for a meal. Stores in DB for consistency."""
    try:
        return await get_or_create_image_url(db, meal_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/images/all", tags=["Meal Images"])
async def list_images(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all cached meal image URLs."""
    return await list_generated_images(db)
