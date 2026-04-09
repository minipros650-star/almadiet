"""
AlmaDiet — Meal Service
Manages meal data loading, querying, and database seeding.
Aligned with meals_dataset.json structure.
"""

import json
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.meal import Meal
from app.services.image_service import build_image_url

# Non-veg keywords for auto-detection
NON_VEG_KEYWORDS = {
    "fish", "chicken", "mutton", "prawn", "shrimp", "egg", "meat",
    "sardine", "anchovy", "seer", "pomfret", "mackerel", "crab",
    "liver", "netholi", "mathi", "meen", "mutta",
}


def _infer_vegetarian(meal_data: dict) -> bool:
    """Infer if a meal is vegetarian from its name and ingredients."""
    name_lower = meal_data.get("name", {}).get("english", "").lower()
    # Check name
    for kw in NON_VEG_KEYWORDS:
        if kw in name_lower:
            return False
    # Check ingredients
    for ing in meal_data.get("ingredients", []):
        ing_name = ing.get("name", "").lower()
        for kw in NON_VEG_KEYWORDS:
            if kw in ing_name:
                return False
    return True


async def get_meals(
    db: AsyncSession,
    region: Optional[str] = None,
    trimester: Optional[str] = None,
    meal_type: Optional[str] = None,
    is_vegetarian: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Meal]:
    """Query meals with optional filters."""
    query = select(Meal)

    if region:
        # Dataset uses "Karnataka / South India", user might search "karnataka"
        query = query.where(Meal.region.ilike(f"%{region}%"))
    if trimester is not None:
        # trimester_suitability is a JSONB array like ["First", "Second", "Third"]
        # Use PostgreSQL JSONB contains: '["Second"]' <@ trimester_suitability
        query = query.where(
            Meal.trimester_suitability.contains([trimester])
        )
    if meal_type:
        query = query.where(Meal.meal_type.ilike(f"%{meal_type}%"))
    if is_vegetarian is not None:
        query = query.where(Meal.is_vegetarian == is_vegetarian)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_meal_by_id(
    db: AsyncSession, meal_id: uuid.UUID
) -> Optional[Meal]:
    """Get a single meal by ID."""
    result = await db.execute(select(Meal).where(Meal.id == meal_id))
    return result.scalar_one_or_none()


async def get_meal_count(db: AsyncSession) -> int:
    """Get total number of meals in database."""
    result = await db.execute(select(func.count(Meal.id)))
    return result.scalar() or 0


async def seed_meals(db: AsyncSession) -> int:
    """
    Load meals from the JSON dataset into the database.
    Parses the nested structure from meals_dataset.json.
    Returns the number of meals seeded.
    """
    dataset_path = Path(settings.MEALS_DATASET_PATH)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Meals dataset not found at {dataset_path}")

    with open(dataset_path, "r", encoding="utf-8") as f:
        meals_data = json.load(f)

    count = 0
    for item in meals_data:
        # ── Parse names ───────────────────────────────────────
        name_obj = item.get("name", {})
        if isinstance(name_obj, str):
            english_name = name_obj
            tamil = malayalam = kannada = telugu = None
        else:
            english_name = name_obj.get("english", "Unknown Meal")
            tamil = name_obj.get("tamil")
            malayalam = name_obj.get("malayalam")
            kannada = name_obj.get("kannada")
            telugu = name_obj.get("telugu")

        # ── Parse nutrition ───────────────────────────────────
        nutrition = item.get("nutrition_per_serving", {})

        # ── Parse trimester ───────────────────────────────────
        trimester_raw = item.get("trimester", [])
        if isinstance(trimester_raw, list):
            trimester_list = trimester_raw
        else:
            trimester_list = [trimester_raw]

        # ── Infer vegetarian status ───────────────────────────
        is_veg = _infer_vegetarian(item)

        meal = Meal(
            dataset_id=item.get("id"),
            name=english_name,
            name_tamil=tamil,
            name_malayalam=malayalam,
            name_kannada=kannada,
            name_telugu=telugu,
            region=item.get("region", "South India"),
            meal_type=item.get("meal_type", "Snack"),
            trimester_suitability=trimester_list,
            # Nutrition
            calories=nutrition.get("calories", 0),
            protein_g=nutrition.get("protein_g", 0),
            carbs_g=nutrition.get("carbohydrates_g", 0),
            fat_g=nutrition.get("fat_g", 0),
            fiber_g=nutrition.get("fiber_g", 0),
            iron_mg=nutrition.get("iron_mg", 0),
            calcium_mg=nutrition.get("calcium_mg", 0),
            folate_mcg=nutrition.get("folate_mcg", 0),
            vitamin_c_mg=nutrition.get("vitamin_c_mg", 0),
            # Ingredients & prep
            ingredients=item.get("ingredients"),
            serving_size=item.get("serving_size"),
            preparation_time_minutes=item.get("preparation_time_minutes"),
            # Clinical
            benefits=item.get("benefits", []),
            who_alignment=item.get("who_alignment"),
            cautions=item.get("cautions"),
            best_time_to_eat=item.get("best_time_to_eat"),
            # Metadata
            allergens=[],
            image_url=item.get("image_url") or build_image_url(english_name, item.get("region", "")),
            is_vegetarian=is_veg,
            clinically_approved=True,
        )
        db.add(meal)
        count += 1

    await db.flush()
    return count
