"""AlmaDiet — Recommendation service (deterministic, safety-first).

Pipeline (docs/ARCHITECTURE.md §2):
  validation → allergy filter → dietary filter → condition filter →
  food-safety filter → availability/content filter → nutritional selection →
  7-day assembly → FINAL safety validation → explanation + sources.

Allergy filtering happens BEFORE selection; a final validation re-checks
every selected meal. ML plays no part in this path (ADR/0001).
"""

from __future__ import annotations

import copy
import random
import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import conditions as conditions_domain
from app.domain.content_state import is_recommendable
from app.domain.gestational import TRIMESTER_LABELS, validate_gestational_age
from app.models.allergen import MealAllergen
from app.models.diet_plan import DietPlan
from app.models.health_record import HealthRecord
from app.models.meal import Meal
from app.models.user import User
from app.services.health_service import ConsentRequiredError, has_current_consent
from app.services.image_service import build_image_url
from app.services.safety_validator import MealView, SafetyValidator

# ── Transparent trimester nutrition focus (documented, explainable) ──────
# Each focus carries a user-facing rationale. These are general education
# statements, NOT personalized medical advice.
TRIMESTER_FOCUS: dict[int, list[dict]] = {
    1: [
        {"nutrient": "folate", "column": "folate_mcg", "rationale": "folate is widely recommended in early pregnancy"},
        {"nutrient": "fiber", "column": "fiber_g", "rationale": "gentler digestion is often helpful in the first trimester"},
        {"nutrient": "iron", "column": "iron_mg", "rationale": "iron supports your changing blood volume"},
    ],
    2: [
        {"nutrient": "iron", "column": "iron_mg", "rationale": "iron needs commonly rise in the second trimester"},
        {"nutrient": "calcium", "column": "calcium_mg", "rationale": "calcium supports your baby's bone development"},
        {"nutrient": "protein", "column": "protein_g", "rationale": "protein supports growth in the second trimester"},
    ],
    3: [
        {"nutrient": "protein", "column": "protein_g", "rationale": "protein supports the rapid growth phase"},
        {"nutrient": "iron", "column": "iron_mg", "rationale": "iron continues to support blood volume"},
        {"nutrient": "calcium", "column": "calcium_mg", "rationale": "calcium supports bone development"},
    ],
}

# Reference context values shown in the UI — explicitly not prescriptions.
TRIMESTER_REFERENCE = {
    1: {"calories": 1800, "protein": 60, "iron": 27, "calcium": 1000},
    2: {"calories": 2200, "protein": 75, "iron": 30, "calcium": 1200},
    3: {"calories": 2200, "protein": 75, "iron": 27, "calcium": 1200},
}

MEAL_TYPE_PATTERNS = {
    "breakfast": ["Breakfast", "Breakfast / Dinner", "Breakfast / Snack", "Breakfast / Lunch", "Breakfast Side"],
    "lunch": ["Lunch", "Lunch Side", "Lunch / Dinner", "Lunch Appetizer", "Breakfast / Lunch"],
    "dinner": ["Lunch / Dinner", "Breakfast / Dinner", "Dinner Appetizer", "Snack / Light Dinner", "Lunch"],
    "snack": ["Snack", "Snack / Appetizer", "Snack / Side", "Mid-Morning Snack",
              "Breakfast / Snack", "Snack / Light Dinner", "Beverage", "Dessert",
              "Lunch Side / Snack", "Beverage / Snack"],
}

SLOTS = ("breakfast", "lunch", "snack", "dinner")


def _meal_card(meal: Meal, why: list[str], cross_contact: list[str] | None = None) -> dict:
    return {
        "id": str(meal.id),
        "meal_id": str(meal.id),
        "name": meal.name,
        "name_tamil": meal.name_tamil,
        "name_malayalam": meal.name_malayalam,
        "name_kannada": meal.name_kannada,
        "name_telugu": meal.name_telugu,
        "region": meal.region,
        "meal_type": meal.meal_type,
        "calories": meal.calories,
        "protein_g": meal.protein_g,
        "carbs_g": meal.carbs_g,
        "fat_g": meal.fat_g,
        "fiber_g": meal.fiber_g,
        "iron_mg": meal.iron_mg,
        "calcium_mg": meal.calcium_mg,
        "folate_mcg": meal.folate_mcg,
        "vitamin_c_mg": meal.vitamin_c_mg,
        "sodium_mg": meal.sodium_mg,
        "sugar_g": meal.sugar_g,
        "is_vegetarian": meal.is_vegetarian,
        "allergens": meal.allergens,
        "ingredients": meal.ingredients,
        "serving_size": meal.serving_size,
        "preparation_time_minutes": meal.preparation_time_minutes,
        "benefits": meal.benefits,
        "cautions": meal.cautions,
        "food_safety_notes": meal.food_safety_notes,
        "substitutions": meal.substitutions,
        "image_url": meal.image_url or build_image_url(meal.name, meal.region),
        "source": meal.source,
        "source_url": meal.source_url,
        "evidence_version": meal.evidence_version,
        "content_status": meal.content_status,
        "why_suggested": why,
        "cross_contact_warning": cross_contact or [],
    }


def _why_for(meal: Meal, record: HealthRecord | User | None, prefer: list[str], focus: list[dict]) -> list[str]:
    """Deterministic, explainable reasons (no 'AI knows' language)."""
    why: list[str] = []
    is_veg_user = bool(getattr(record, "is_vegetarian", False)) or (
        getattr(record, "dietary_preference", None) == "veg"
    )
    if record is not None and is_veg_user and meal.is_vegetarian:
        why.append("matches your vegetarian preference")
    if "iron_rich" in prefer and meal.iron_mg >= 3:
        why.append("contains documented iron-rich ingredients")
    if "lower_sodium" in prefer and meal.sodium_mg <= 150:
        why.append("chosen as a lower-sodium option")
    if "lower_sugar" in prefer and meal.sugar_g <= 8:
        why.append("chosen as a lower-sugar option")
    if "gentle" in prefer and meal.meal_type not in ("Condiment",):
        why.append("chosen as a gentler option")
    for f in focus:
        value = getattr(meal, f["column"], 0) or 0
        if value >= 15:
            why.append(f"good source of {f['nutrient']} — {f['rationale']}")
            break
    if not why:
        why.append("matches your selected trimester and dietary preferences")
    return why


class _CandidatePool:
    """Per-slot candidate pools with rotation exclusion across the week."""

    def __init__(self, meals_by_slot: dict[str, list[Meal]]) -> None:
        self.by_slot = {slot: list(meals) for slot, meals in meals_by_slot.items()}

    def take(self, slot: str, rng: random.Random, n: int, exclude_ids: set[str],
             day_index: int = 1) -> list[Meal]:
        pool = [m for m in self.by_slot.get(slot, []) if str(m.id) not in exclude_ids]
        if not pool:
            # Recycle: allow reuse only when the catalog is genuinely thin.
            # Rotate by day so later days cycle through the catalog rather
            # than repeating the same meals every day.
            pool = list(self.by_slot.get(slot, []))
            if pool:
                shift = ((day_index - 1) * n) % len(pool)
                pool = pool[shift:] + pool[:shift]
        rng.shuffle(pool)
        picked = pool[:n]
        return picked


async def _load_candidates(
    db: AsyncSession,
    validator: SafetyValidator,
    record: HealthRecord,
    user: User,
    prefer: list[str],
) -> dict[str, list[Meal]]:
    """Load, then apply safety filters BEFORE selection."""
    trimester_label = TRIMESTER_LABELS.get(record.trimester, "First")
    veg_only = record.dietary_preference == "veg" or (
        record.dietary_preference == "nonveg" and record.is_vegetarian
    )

    eager = selectinload(Meal.allergen_links).selectinload(MealAllergen.allergen)
    is_pg = db.get_bind().dialect.name == "postgresql"
    if is_pg:
        result = await db.execute(
            select(Meal).options(eager).where(Meal.trimester_suitability.contains([trimester_label]))
        )
        all_meals = list(result.scalars().all())
    else:
        # SQLite (tests): fetch and filter in Python (no @> operator).
        result = await db.execute(select(Meal).options(eager))
        all_meals = [
            m for m in result.scalars().all()
            if trimester_label in (m.trimester_suitability or [])
        ]
    if not all_meals:
        result = await db.execute(select(Meal).options(eager))
        all_meals = list(result.scalars().all())

    user_allergies = list(record.allergies or [])
    user_conditions = list(record.medical_conditions or [])

    pools: dict[str, list[Meal]] = {slot: [] for slot in SLOTS}
    for meal in all_meals:
        if veg_only and not meal.is_vegetarian:
            continue
        if meal.meal_type == "Dessert" and "Dessert" in conditions_domain.restrictions_for_conditions(user_conditions)["exclude_meal_types"]:
            pass  # hard condition exclusion handled below via validator too
        view = MealView.from_orm(meal)
        result = validator.validate_meal(view, user_allergies, user_conditions)
        if not result.allowed:
            continue
        if not conditions_domain.meal_matches_preference(
            {"name": meal.name, "meal_type": meal.meal_type}, prefer
        ):
            continue
        for slot, patterns in MEAL_TYPE_PATTERNS.items():
            if meal.meal_type in patterns:
                pools[slot].append(meal)
                break
    return pools


async def generate_diet_plan(
    db: AsyncSession,
    user_id: uuid.UUID,
    health_record_id: uuid.UUID,
    validator: SafetyValidator,
    seed: int | None = None,
) -> tuple[DietPlan, list[str]]:
    """Generate a genuine 7-day plan. Returns (plan, exclusions_summary_lines)."""
    user = await db.get(User, user_id)
    if not user:
        raise ValueError("User not found")

    # Same consent gate as health records — meal planning is a use of
    # personal health data (docs/PRIVACY_AND_DATA.md).
    if not await has_current_consent(db, user_id):
        raise ConsentRequiredError()

    result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id == health_record_id, HealthRecord.user_id == user_id
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise ValueError("Health record not found")

    # Centralized gestational consistency (backend gate; TEST 3).
    validate_gestational_age(record.trimester, record.week_number)

    user_conditions = list(record.medical_conditions or [])
    condition_bundle = conditions_domain.restrictions_for_conditions(user_conditions)
    prefer = condition_bundle["prefer"]

    focus = TRIMESTER_FOCUS.get(record.trimester, TRIMESTER_FOCUS[2])
    pools = await _load_candidates(db, validator, record, user, prefer)

    rng = random.Random(seed if seed is not None else record.week_number)
    days: list[dict] = []
    used_ids: set[str] = set()

    for day_index in range(1, 8):
        day_meals: dict[str, list[dict]] = {}
        for slot in SLOTS:
            picked = _CandidatePool(pools).take(
                slot, rng, n=2, exclude_ids=used_ids, day_index=day_index
            )
            cards = []
            for meal in picked:
                view = MealView.from_orm(meal)
                final = validator.validate_meal(
                    view, list(record.allergies or []), user_conditions
                )
                if not final.allowed:
                    # FINAL SAFETY VALIDATION (TEST 11) — never include.
                    continue
                why = _why_for(meal, record, prefer, focus)
                cards.append(_meal_card(meal, why, final.cross_contact))
                used_ids.add(str(meal.id))
            day_meals[slot] = cards
        days.append({"day_index": day_index, "meals": day_meals})

    # Exclusion summary for transparency.
    total_candidates = sum(len(v) for v in pools.values())
    exclusions = {
        "candidate_pool_size": total_candidates,
        "filters_applied": [
            "allergy_hard_exclusion",
            "dietary_preference",
            *(["condition_safety"] if user_conditions else []),
            "food_safety",
            "content_status",
        ],
        "allergy_categories": sorted({a.lower() for a in (record.allergies or [])}),
    }

    reference = TRIMESTER_REFERENCE.get(record.trimester, TRIMESTER_REFERENCE[2])
    alerts = list(condition_bundle["explain"])
    alerts.append(
        "Meal ideas are based on your selected preferences and available "
        "nutrition information. This is general information, not a "
        "prescription — discuss targets with your clinician."
    )

    today = date.today()
    plan = DietPlan(
        user_id=user_id,
        health_record_id=health_record_id,
        trimester=record.trimester,
        week_number=record.week_number,
        days=days,
        target_calories=reference["calories"],
        target_protein=reference["protein"],
        target_iron=reference["iron"],
        target_calcium=reference["calcium"],
        dietary_alerts=alerts,
        exclusions_applied=exclusions,
        user_corrections=[],
        plan_start=today,
        plan_end=today + timedelta(days=6),  # 7 days inclusive
    )
    db.add(plan)
    await db.flush()
    await db.refresh(plan)
    return plan, alerts


async def swap_meal(
    db: AsyncSession,
    user_id: uuid.UUID,
    plan_id: uuid.UUID,
    day_index: int,
    slot: str,
    current_meal_id: str,
    validator: SafetyValidator,
    seed: int | None = None,
) -> Optional[DietPlan]:
    """Swap one meal for another compatible meal — full safety re-run."""
    if slot not in SLOTS:
        raise ValueError("Invalid meal slot")
    if not 1 <= day_index <= 7:
        raise ValueError("Day index must be 1-7")

    result = await db.execute(
        select(DietPlan).where(DietPlan.id == plan_id, DietPlan.user_id == user_id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        return None

    result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id == plan.health_record_id, HealthRecord.user_id == user_id
        )
    )
    record = result.scalar_one_or_none()

    user = await db.get(User, user_id)
    if record is not None:
        user_conditions = list(record.medical_conditions or [])
        user_allergies = list(record.allergies or [])
        trimester = record.trimester
    else:
        # Personalized-plan path: safety context lives on the profile.
        if plan.health_record_id is not None:
            raise ValueError("Original health record no longer available")
        if user is None:
            raise ValueError("User not found")
        user_conditions = []
        user_allergies = list(user.declared_allergies or [])
        trimester = plan.trimester
    prefer = conditions_domain.restrictions_for_conditions(user_conditions)["prefer"]
    focus = TRIMESTER_FOCUS.get(trimester, TRIMESTER_FOCUS[2])

    # Mutate a DEEP COPY of the plan days: in-place mutation of the loaded
    # JSON structure is invisible to the ORM's change detection (the "old"
    # and "new" values would compare equal), so the swap would silently
    # never persist.
    days = copy.deepcopy(plan.days)
    current_day = next(d for d in days if d["day_index"] == day_index)
    current_ids = {
        m["id"] for slot_meals in current_day["meals"].values() for m in slot_meals
    }

    trimester_label = TRIMESTER_LABELS.get(trimester, "First")
    eager = selectinload(Meal.allergen_links).selectinload(MealAllergen.allergen)
    if db.get_bind().dialect.name == "postgresql":
        result = await db.execute(
            select(Meal).options(eager).where(Meal.trimester_suitability.contains([trimester_label]))
        )
        candidates = list(result.scalars().all())
    else:
        result = await db.execute(select(Meal).options(eager))
        candidates = [
            m for m in result.scalars().all()
            if trimester_label in (m.trimester_suitability or [])
        ]

    patterns = MEAL_TYPE_PATTERNS[slot]
    rng = random.Random(seed if seed is not None else int(uuid.uuid4().int % 1e9))

    replacement_card = None
    for meal in rng.sample(candidates, len(candidates)) if candidates else []:
        if str(meal.id) in current_ids or str(meal.id) == current_meal_id:
            continue
        if meal.meal_type not in patterns:
            continue
        view = MealView.from_orm(meal)
        final = validator.validate_meal(view, user_allergies, user_conditions)
        if not final.allowed:
            continue
        if not conditions_domain.meal_matches_preference(
            {"name": meal.name, "meal_type": meal.meal_type}, prefer
        ):
            continue
        why = _why_for(meal, record or user, prefer, focus)
        why.append(
            "swapped in as an alternative for the same meal slot — all your "
            "safety filters were re-applied"
        )
        replacement_card = _meal_card(meal, why, final.cross_contact)
        break

    if replacement_card is None:
        raise ValueError("No safe alternative meal is available for this slot")

    # Replace only the swapped card within the same slot.
    slot_cards = current_day["meals"][slot]
    new_slot_cards = [
        replacement_card if m["id"] == current_meal_id else m for m in slot_cards
    ]
    if all(m["id"] != replacement_card["id"] for m in new_slot_cards):
        # current_meal_id not present — replace the first card.
        new_slot_cards = [replacement_card] + new_slot_cards[1:]
    current_day["meals"][slot] = new_slot_cards

    plan.days = days
    await db.flush()
    await db.refresh(plan)
    return plan


async def get_diet_plans(db: AsyncSession, user_id: uuid.UUID) -> list[DietPlan]:
    result = await db.execute(
        select(DietPlan).where(DietPlan.user_id == user_id).order_by(DietPlan.created_at.desc())
    )
    return list(result.scalars().all())


async def get_diet_plan_by_id(
    db: AsyncSession, plan_id: uuid.UUID, user_id: uuid.UUID
) -> Optional[DietPlan]:
    result = await db.execute(
        select(DietPlan).where(DietPlan.id == plan_id, DietPlan.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def submit_feedback(
    db: AsyncSession, user_id: uuid.UUID, plan_id: uuid.UUID, feedback: str, rating: int
) -> DietPlan:
    plan = await get_diet_plan_by_id(db, plan_id, user_id)
    if plan is None:
        raise ValueError("Diet plan not found")
    corrections = list(copy.deepcopy(plan.user_corrections or []))
    corrections.append({
        "feedback": feedback,
        "rating": rating,
        "timestamp": str(date.today()),
    })
    plan.user_corrections = corrections
    await db.flush()
    await db.refresh(plan)
    return plan
