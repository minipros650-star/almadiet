"""
AlmaDiet — AI Image Service
Generates meal image URLs using Pollinations.ai (free, no API key required).
The Flutter frontend loads images directly from the Pollinations URL.
"""

import uuid
import logging
import urllib.parse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meal import Meal
from app.models.meal_image import MealImage

logger = logging.getLogger("almadiet.image")

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"


def _build_prompt(meal_name: str, region: str = "") -> str:
    """Build a food photography prompt from meal data."""
    region_style = {
        "kerala": "Kerala-style served on fresh banana leaf",
        "tamilnadu": "Tamil Nadu-style on traditional steel plate",
        "karnataka": "Karnataka-style on traditional brass plate",
        "andhra": "Andhra Pradesh-style on brass plate with condiments",
    }
    style = region_style.get(region, "South Indian-style on traditional plate")

    return (
        f"Professional food photography of {meal_name}, "
        f"{style}, "
        f"top-down view, warm natural lighting, "
        f"garnished, appetizing, high resolution, realistic"
    )


def build_image_url(meal_name: str, region: str = "", width: int = 400, height: int = 400) -> str:
    """Build a direct Pollinations.ai image URL for any meal."""
    prompt = _build_prompt(meal_name, region)
    encoded = urllib.parse.quote(prompt)
    return f"{POLLINATIONS_BASE}/{encoded}?width={width}&height={height}&nologo=true&seed=42"


async def get_cached_image(db: AsyncSession, meal_id: uuid.UUID) -> MealImage | None:
    """Check if we already have a cached image URL for this meal."""
    result = await db.execute(
        select(MealImage).where(MealImage.meal_id == meal_id).limit(1)
    )
    return result.scalar_one_or_none()


async def get_or_create_image_url(db: AsyncSession, meal_id: uuid.UUID) -> dict:
    """
    Get or create a Pollinations.ai image URL for a meal.
    Stores the URL in DB for consistency (same URL per meal).
    """
    # Check cache first
    cached = await get_cached_image(db, meal_id)
    if cached:
        return {
            "meal_id": str(cached.meal_id),
            "image_url": cached.image_url,
            "prompt": cached.prompt_used,
            "cached": True,
        }

    # Get meal details
    result = await db.execute(select(Meal).where(Meal.id == meal_id))
    meal = result.scalar_one_or_none()
    if not meal:
        raise ValueError(f"Meal {meal_id} not found")

    # Build URL
    prompt = _build_prompt(meal.name, meal.region)
    image_url = build_image_url(meal.name, meal.region)

    # Cache in DB
    meal_image = MealImage(
        meal_id=meal_id,
        image_url=image_url,
        prompt_used=prompt,
    )
    db.add(meal_image)
    await db.commit()
    await db.refresh(meal_image)

    logger.info(f"🎨 Image URL created for: {meal.name}")

    return {
        "meal_id": str(meal_id),
        "image_url": image_url,
        "prompt": prompt,
        "cached": False,
    }


async def get_meal_image_url(db: AsyncSession, meal_id: uuid.UUID) -> dict:
    """Get a direct Pollinations.ai URL for a meal (instant, no caching needed)."""
    result = await db.execute(select(Meal).where(Meal.id == meal_id))
    meal = result.scalar_one_or_none()
    if not meal:
        raise ValueError(f"Meal {meal_id} not found")

    image_url = build_image_url(meal.name, meal.region)
    return {
        "meal_id": str(meal_id),
        "image_url": image_url,
        "meal_name": meal.name,
    }


async def list_generated_images(db: AsyncSession) -> list[dict]:
    """List all cached image URLs."""
    result = await db.execute(select(MealImage).order_by(MealImage.generated_at.desc()))
    images = result.scalars().all()
    return [
        {
            "id": str(img.id),
            "meal_id": str(img.meal_id),
            "image_url": img.image_url,
            "generated_at": img.generated_at.isoformat() if img.generated_at else None,
        }
        for img in images
    ]
