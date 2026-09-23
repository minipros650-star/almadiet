"""AlmaDiet — Meal service: catalog queries, governance-aware seeding,
allergen derivation from ingredients."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.allergens import DISPLAY_NAMES, AllergenCategory, allergens_for_ingredients
from app.domain.content_state import ContentStatus
from app.models.allergen import Allergen, MealAllergen
from app.models.meal import Meal
from app.services.image_service import build_image_url

logger = logging.getLogger("almadiet.meals")

# Non-veg keywords for vegetarian inference
NON_VEG_KEYWORDS = {
    "fish", "chicken", "mutton", "prawn", "shrimp", "egg", "meat",
    "sardine", "anchovy", "seer", "pomfret", "mackerel", "crab",
    "liver", "netholi", "mathi", "meen", "mutta",
}

# Claim phrases prohibited in seed content (ADR/0001).
BANNED_CLAIMS = (
    "clinically approved", "medically approved", "who approved",
    "who certified", "doctor approved", "clinically validated",
    "medically validated", "clinically proven", "medically proven",
    "ai doctor", "clinical ai",
)


def _infer_vegetarian(item: dict) -> bool:
    name = str(item.get("name", {}).get("english", "")).lower()
    for kw in NON_VEG_KEYWORDS:
        if kw in name:
            return False
    for ing in item.get("ingredients", []):
        ing_name = str(ing.get("name", "")).lower()
        for kw in NON_VEG_KEYWORDS:
            if kw in ing_name:
                return False
    return True


def _strip_banned_claims(text: str | None) -> str | None:
    """Remove unsourced clinical-claim sentences from free text."""
    if not text:
        return text
    cleaned_lines = []
    for line in text.replace("; ", ".\n").split(". "):
        low = line.lower()
        if any(claim in low for claim in BANNED_CLAIMS):
            continue
        cleaned_lines.append(line.strip().rstrip("."))
    return ". ".join(x for x in cleaned_lines if x) or None


async def _ensure_allergen_rows(db: AsyncSession) -> dict[str, Allergen]:
    result = await db.execute(select(Allergen))
    rows = {a.category: a for a in result.scalars()}
    for category in AllergenCategory:
        if category.value not in rows:
            row = Allergen(
                category=category.value,
                display_name=DISPLAY_NAMES[category.value],
            )
            db.add(row)
            rows[category.value] = row
    await db.flush()
    return rows


MEAL_EAGER_LOADS = (
    selectinload(Meal.allergen_links).selectinload(MealAllergen.allergen)
)


def _is_postgres(db: AsyncSession) -> bool:
    return db.get_bind().dialect.name == "postgresql"


async def get_meals(
    db: AsyncSession,
    region: Optional[str] = None,
    trimester: Optional[str] = None,
    meal_type: Optional[str] = None,
    is_vegetarian: Optional[bool] = None,
    include_statuses: Optional[list[str]] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Meal]:
    query = select(Meal).options(MEAL_EAGER_LOADS)

    if include_statuses:
        query = query.where(Meal.content_status.in_([s.upper() for s in include_statuses]))
    if region:
        query = query.where(Meal.region.ilike(f"%{region}%"))
    # JSONB @> containment is PostgreSQL-only; SQLite (tests) filters in Python.
    trimester_py = trimester if (trimester is not None and not _is_postgres(db)) else None
    if trimester is not None and _is_postgres(db):
        query = query.where(Meal.trimester_suitability.contains([trimester]))
    if meal_type:
        query = query.where(Meal.meal_type.ilike(f"%{meal_type}%"))
    if is_vegetarian is not None:
        query = query.where(Meal.is_vegetarian == is_vegetarian)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    meals = list(result.scalars().all())
    if trimester_py is not None:
        meals = [m for m in meals if trimester_py in (m.trimester_suitability or [])]
    return meals


async def get_meal_by_id(db: AsyncSession, meal_id: uuid.UUID) -> Optional[Meal]:
    result = await db.execute(
        select(Meal).options(MEAL_EAGER_LOADS).where(Meal.id == meal_id)
    )
    return result.scalar_one_or_none()


async def get_meal_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(Meal.id)))
    return result.scalar() or 0


async def seed_meals(db: AsyncSession) -> int:
    """Import the dataset.

    Governance: every imported row lands in REVIEW_REQUIRED — pending
    review. Nothing is ever auto-marked PUBLISHED (approved): promotion
    happens ONLY through approve_meal below, which writes an explicit
    approval record (reviewer + timestamp). This keeps the personalized
    suggestion pool empty until a human reviewer has approved content.
    """
    dataset_path = Path(settings.MEALS_DATASET_PATH)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Meals dataset not found at {dataset_path}")

    with open(dataset_path, "r", encoding="utf-8") as f:
        meals_data = json.load(f)

    allergen_rows = await _ensure_allergen_rows(db)
    count = 0

    for item in meals_data:
        name_obj = item.get("name", {})
        if isinstance(name_obj, str):
            english_name, tamil, malayalam, kannada, telugu = name_obj, None, None, None, None
        else:
            english_name = name_obj.get("english", "Unknown Meal")
            tamil = name_obj.get("tamil")
            malayalam = name_obj.get("malayalam")
            kannada = name_obj.get("kannada")
            telugu = name_obj.get("telugu")

        nutrition = item.get("nutrition_per_serving", {})
        trimester_raw = item.get("trimester", [])
        trimester_list = trimester_raw if isinstance(trimester_raw, list) else [trimester_raw]

        ingredients = item.get("ingredients") or []
        cautions = _strip_banned_claims(item.get("cautions"))

        meal = Meal(
            dataset_id=item.get("id"),
            name=english_name,
            name_tamil=tamil,
            name_malayalam=malayalam,
            name_kannada=kannada,
            name_telugu=telugu,
            region=item.get("region", "South India"),
            meal_type=item.get("meal_type", "Snack"),
            cuisine="South Indian",
            trimester_suitability=trimester_list,
            calories=nutrition.get("calories", 0) or 0,
            protein_g=nutrition.get("protein_g", 0) or 0,
            carbs_g=nutrition.get("carbohydrates_g", 0) or 0,
            fat_g=nutrition.get("fat_g", 0) or 0,
            fiber_g=nutrition.get("fiber_g", 0) or 0,
            iron_mg=nutrition.get("iron_mg", 0) or 0,
            calcium_mg=nutrition.get("calcium_mg", 0) or 0,
            folate_mcg=nutrition.get("folate_mcg", 0) or 0,
            vitamin_c_mg=nutrition.get("vitamin_c_mg", 0) or 0,
            sodium_mg=nutrition.get("sodium_mg", 0) or 0,
            sugar_g=nutrition.get("sugar_g", 0) or 0,
            ingredients=ingredients,
            serving_size=item.get("serving_size"),
            serving_basis="per serving as listed in source dataset",
            preparation_time_minutes=item.get("preparation_time_minutes"),
            benefits=item.get("benefits", []),
            cautions=cautions,
            best_time_to_eat=item.get("best_time_to_eat"),
            # Provenance — dataset is the documented source; review PENDING.
            source="AlmaDiet seed dataset (backend/data/meals_dataset.json)",
            source_url=None,
            evidence_version="1",
            content_status=ContentStatus.REVIEW_REQUIRED.value,
            image_url=item.get("image_url") or build_image_url(english_name, item.get("region", "")),
            is_vegetarian=_infer_vegetarian(item),
        )
        db.add(meal)
        await db.flush()

        # Derive allergen links from ingredients + name.
        detected = allergens_for_ingredients(ingredients)
        for category in allergens_for_ingredients([{"name": english_name}]):
            detected.setdefault(category, []).append(english_name)
        for category, terms in detected.items():
            allergen_row = allergen_rows[category]
            for term in sorted(set(terms)):
                db.add(
                    MealAllergen(
                        meal_id=meal.id,
                        allergen_id=allergen_row.id,
                        matched_term=term[:255],
                        match_type="synonym",
                    )
                )
        count += 1

    await db.flush()
    logger.info(
        "Seeded %d meals (content_status=REVIEW_REQUIRED — approval via approve_meal only)", count
    )
    return count


async def approve_meal(
    db: AsyncSession,
    meal_id: uuid.UUID,
    reviewer: str,
    notes: str | None = None,
) -> Meal:
    """Explicit approval — the ONLY path to PUBLISHED.

    Writes reviewer metadata and the approval timestamp on the meal and
    records a ContentVersion audit row. Seeding never calls this; a human
    reviewer (or an authenticated admin endpoint) must.
    """
    from datetime import datetime, timezone

    from app.domain.content_state import transition
    from app.models.content_version import ContentVersion

    meal = await get_meal_by_id(db, meal_id)
    if meal is None:
        raise ValueError("Meal not found")

    new_status = transition(meal.content_status, ContentStatus.PUBLISHED.value)
    meal.content_status = new_status.value
    meal.approved_by = reviewer[:255]
    meal.approved_at = datetime.now(timezone.utc)
    meal.reviewer = reviewer[:255]
    meal.reviewed_at = meal.approved_at

    db.add(
        ContentVersion(
            meal_id=meal.id,
            version=int(meal.evidence_version or "1"),
            change_note=notes or "Approved for personalized suggestions",
            reviewer=reviewer[:255],
            status=new_status.value,
        )
    )
    await db.flush()
    await db.refresh(meal)
    return meal


async def retire_meal(
    db: AsyncSession,
    meal_id: uuid.UUID,
    reviewer: str,
    notes: str | None = None,
) -> Meal:
    """Retire a meal — immediately excluded from ALL suggestion paths."""
    from datetime import datetime, timezone

    from app.domain.content_state import ContentStatus as CS

    meal = await get_meal_by_id(db, meal_id)
    if meal is None:
        raise ValueError("Meal not found")
    meal.content_status = CS.RETIRED.value
    meal.retired_at = datetime.now(timezone.utc)
    meal.reviewer = reviewer[:255]
    await db.flush()
    await db.refresh(meal)
    return meal
