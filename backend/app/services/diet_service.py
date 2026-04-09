"""
AlmaDiet — Diet Service
Generates personalized, trimester-specific diet plans using ML predictions
and regional meal data. Handles plan retrieval and user feedback.
Aligned with meals_dataset.json structure.
"""

import uuid
import random
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diet_plan import DietPlan
from app.models.health_record import HealthRecord
from app.models.meal import Meal
from app.models.user import User
from app.ml.predictor import predict_nutrient_priorities, get_top_nutrients
from app.services.image_service import build_image_url

# ── Trimester-specific daily nutrient targets ─────────────────
TRIMESTER_TARGETS = {
    1: {"calories": 1800, "protein": 60, "iron": 27, "calcium": 1000},
    2: {"calories": 2200, "protein": 75, "iron": 30, "calcium": 1200},
    3: {"calories": 2500, "protein": 85, "iron": 35, "calcium": 1300},
}

# ── Nutrient column mapping in Meal model ─────────────────────
NUTRIENT_COLUMNS = {
    "calories": "calories",
    "protein": "protein_g",
    "iron": "iron_mg",
    "calcium": "calcium_mg",
    "folate": "folate_mcg",
    "fiber": "fiber_g",
    "vitamin_c": "vitamin_c_mg",
}

# ── Map trimester int → dataset string ────────────────────────
TRIMESTER_MAP = {1: "First", 2: "Second", 3: "Third"}

# ── Map meal_type queries to dataset patterns ─────────────────
MEAL_TYPE_PATTERNS = {
    "breakfast": ["Breakfast", "Breakfast / Dinner", "Breakfast / Snack", "Breakfast / Lunch"],
    "lunch": ["Lunch", "Lunch Side", "Lunch / Dinner", "Lunch Appetizer", "Breakfast / Lunch"],
    "dinner": ["Lunch / Dinner", "Breakfast / Dinner", "Dinner Appetizer", "Snack / Light Dinner"],
    "snack": ["Snack", "Snack / Appetizer", "Snack / Side", "Mid-Morning Snack",
              "Breakfast / Snack", "Snack / Light Dinner", "Beverage", "Dessert",
              "Condiment", "Lunch Side / Snack"],
}


def _meal_to_dict(meal: Meal) -> dict:
    """Convert a Meal ORM object to a serializable dict for plan storage."""
    return {
        "id": str(meal.id),
        "meal_id": str(meal.id),
        "dataset_id": meal.dataset_id,
        "name": meal.name,
        "name_tamil": meal.name_tamil,
        "name_malayalam": meal.name_malayalam,
        "name_kannada": meal.name_kannada,
        "name_telugu": meal.name_telugu,
        "region": meal.region,
        "meal_type": meal.meal_type,
        "calories": meal.calories,
        "protein_g": meal.protein_g,
        "iron_mg": meal.iron_mg,
        "calcium_mg": meal.calcium_mg,
        "folate_mcg": meal.folate_mcg,
        "fiber_g": meal.fiber_g,
        "carbs_g": meal.carbs_g,
        "fat_g": meal.fat_g,
        "vitamin_c_mg": meal.vitamin_c_mg,
        "is_vegetarian": meal.is_vegetarian,
        "image_url": meal.image_url or build_image_url(meal.name, meal.region),
        "ingredients": meal.ingredients,
        "serving_size": meal.serving_size,
        "preparation_time_minutes": meal.preparation_time_minutes,
        "benefits": meal.benefits,
        "who_alignment": meal.who_alignment,
        "cautions": meal.cautions,
        "best_time_to_eat": meal.best_time_to_eat,
    }


async def _select_meals(
    db: AsyncSession,
    meal_type: str,
    region: str,
    trimester: int,
    is_vegetarian: bool,
    top_nutrients: list[str],
    count: int = 2,
    exclude_ids: set = None,
) -> list[Meal]:
    """
    Select meals for a specific meal type, optimized by top nutrient priorities.
    Applies region/trimester/diet filters, then scores by nutrient priority.
    """
    trimester_str = TRIMESTER_MAP.get(trimester, "First")
    meal_type_patterns = MEAL_TYPE_PATTERNS.get(meal_type, [meal_type])

    # Build query with region + trimester + meal_type patterns
    query = select(Meal).where(
        Meal.meal_type.in_(meal_type_patterns),
        Meal.region.ilike(f"%{region}%"),
        Meal.trimester_suitability.contains([trimester_str]),
    )
    if is_vegetarian:
        query = query.where(Meal.is_vegetarian == True)
    if exclude_ids:
        query = query.where(~Meal.id.in_(exclude_ids))

    result = await db.execute(query)
    candidates = list(result.scalars().all())

    if not candidates:
        # Fallback: try without region filter
        query = select(Meal).where(
            Meal.meal_type.in_(meal_type_patterns),
            Meal.trimester_suitability.contains([trimester_str]),
        )
        if is_vegetarian:
            query = query.where(Meal.is_vegetarian == True)
        if exclude_ids:
            query = query.where(~Meal.id.in_(exclude_ids))
        result = await db.execute(query)
        candidates = list(result.scalars().all())

    if not candidates:
        return []

    # Score each candidate by how well it matches top nutrient priorities
    def _score_meal(meal: Meal) -> float:
        score = 0.0
        for i, nutrient in enumerate(top_nutrients):
            col = NUTRIENT_COLUMNS.get(nutrient)
            if col:
                value = getattr(meal, col, 0) or 0
                weight = len(top_nutrients) - i  # Higher weight for higher priority
                score += value * weight
        return score

    candidates.sort(key=_score_meal, reverse=True)

    # Pick top candidates with some randomness for variety
    top_pool = candidates[:max(count * 3, 6)]
    selected = random.sample(top_pool, min(count, len(top_pool)))
    return selected


async def generate_diet_plan(
    db: AsyncSession,
    user_id: uuid.UUID,
    health_record_id: uuid.UUID,
) -> DietPlan:
    """
    Generate a personalized weekly diet plan based on health record and ML predictions.
    """
    # Fetch user and health record
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    hr_result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id == health_record_id,
            HealthRecord.user_id == user_id,
        )
    )
    health_record = hr_result.scalar_one_or_none()
    if not health_record:
        raise ValueError("Health record not found")

    # ── ML Prediction ────────────────────────────────────────
    weight_gain = 0.0
    if user.pre_pregnancy_weight_kg:
        weight_gain = health_record.current_weight_kg - user.pre_pregnancy_weight_kg

    priorities = predict_nutrient_priorities(
        trimester=health_record.trimester,
        week=health_record.week_number,
        bmi=health_record.bmi or 24.0,
        hemoglobin=health_record.hemoglobin,
        blood_sugar=health_record.blood_sugar_fasting,
        is_vegetarian=health_record.is_vegetarian,
        region=user.region,
        age=user.age or 28,
        weight_gain=weight_gain,
    )
    top_nutrients = get_top_nutrients(priorities, top_n=4)

    # ── Generate alerts based on priorities ───────────────────
    alerts = []
    if priorities.get("iron", 0) > 7:
        alerts.append("⚠️ Iron needs are elevated. Iron-rich meals prioritized.")
    if priorities.get("folate", 0) > 7:
        alerts.append("⚠️ Folate is critical this period. Folate-rich foods included.")
    if priorities.get("calcium", 0) > 7:
        alerts.append("⚠️ Calcium needs are high. Dairy and calcium-rich meals added.")
    if priorities.get("fiber", 0) > 7:
        alerts.append("🥬 Fiber needs elevated. High-fiber meals included for digestion.")

    # ── Select meals per type ─────────────────────────────────
    used_ids = set()

    breakfast_meals_db = await _select_meals(
        db, "breakfast", user.region, health_record.trimester,
        health_record.is_vegetarian, top_nutrients, count=3, exclude_ids=used_ids,
    )
    used_ids.update(m.id for m in breakfast_meals_db)

    lunch_meals_db = await _select_meals(
        db, "lunch", user.region, health_record.trimester,
        health_record.is_vegetarian, top_nutrients, count=3, exclude_ids=used_ids,
    )
    used_ids.update(m.id for m in lunch_meals_db)

    dinner_meals_db = await _select_meals(
        db, "dinner", user.region, health_record.trimester,
        health_record.is_vegetarian, top_nutrients, count=3, exclude_ids=used_ids,
    )
    used_ids.update(m.id for m in dinner_meals_db)

    snack_meals_db = await _select_meals(
        db, "snack", user.region, health_record.trimester,
        health_record.is_vegetarian, top_nutrients, count=2, exclude_ids=used_ids,
    )

    # ── Targets from trimester ────────────────────────────────
    targets = TRIMESTER_TARGETS.get(health_record.trimester, TRIMESTER_TARGETS[2])

    today = date.today()
    plan = DietPlan(
        user_id=user_id,
        health_record_id=health_record_id,
        trimester=health_record.trimester,
        week_number=health_record.week_number,
        breakfast_meals=[_meal_to_dict(m) for m in breakfast_meals_db],
        lunch_meals=[_meal_to_dict(m) for m in lunch_meals_db],
        dinner_meals=[_meal_to_dict(m) for m in dinner_meals_db],
        snack_meals=[_meal_to_dict(m) for m in snack_meals_db],
        target_calories=targets["calories"],
        target_protein=targets["protein"],
        target_iron=targets["iron"],
        target_calcium=targets["calcium"],
        dietary_alerts=alerts,
        user_corrections=[],
        is_emergency_plan=False,
        plan_start=today,
        plan_end=today + timedelta(days=7),
    )
    db.add(plan)
    await db.flush()
    await db.refresh(plan)
    return plan


async def get_diet_plans(
    db: AsyncSession, user_id: uuid.UUID
) -> list[DietPlan]:
    """Get all diet plans for a user, ordered by creation date."""
    result = await db.execute(
        select(DietPlan)
        .where(DietPlan.user_id == user_id)
        .order_by(DietPlan.created_at.desc())
    )
    return list(result.scalars().all())


async def get_diet_plan_by_id(
    db: AsyncSession, plan_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[DietPlan]:
    """Get a specific diet plan."""
    result = await db.execute(
        select(DietPlan).where(
            DietPlan.id == plan_id,
            DietPlan.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def submit_feedback(
    db: AsyncSession,
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    feedback: str,
    rating: int,
) -> DietPlan:
    """Add user feedback/corrections to a diet plan."""
    result = await db.execute(
        select(DietPlan).where(
            DietPlan.id == plan_id,
            DietPlan.user_id == user_id,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise ValueError("Diet plan not found")

    corrections = plan.user_corrections or []
    corrections.append({
        "feedback": feedback,
        "rating": rating,
        "timestamp": str(date.today()),
    })
    plan.user_corrections = corrections
    await db.flush()
    await db.refresh(plan)
    return plan
