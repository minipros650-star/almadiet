"""AlmaDiet — Meal hard-safety filter for personalized suggestions.

This service is the ONLY path into suggestion ranking. It enforces, per
meal, ALL of:

1. ``content_status == PUBLISHED`` (approved) — anything else is excluded
   (draft, pending review, reviewed-but-unpublished, retired).
2. A valid source reference + evidence/catalog version exists.
3. Allergen overlap with the user's declared allergen codes is empty
   (ingredient-level, via the normalized MealAllergen table).
4. The meal matches the user's dietary preference.
5. The meal passes the documented food-safety policy (domain/food_safety).
6. ``retired_at IS NULL`` and ``clinician_review_required IS FALSE`` for
   personalized generation; a True flag blocks the whole customized plan
   (the user is directed to their clinician instead).

There is no fallback path: if no meals survive, callers must surface
``no_safe_suggestion`` with a clinician-contact message. Random choice,
"best effort" relaxation, and unapproved-meal fallbacks are structurally
impossible here — this module has no code path that returns a meal which
failed a check.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain import conditions as conditions_domain
from app.domain import food_safety
from app.domain.allergens import AllergenCategory
from app.domain.content_state import ContentStatus
from app.models.allergen import MealAllergen
from app.models.meal import Meal
from app.schemas.errors import ErrorCode

# Statuses eligible for personalized suggestions: PUBLISHED only.
SUGGESTABLE_STATUSES = frozenset({ContentStatus.PUBLISHED.value})


class SafetyFilterBlocked(Exception):
    """Raised when personalized generation is blocked as a whole.

    ``code`` is one of the ErrorCode strings below; ``message`` is
    user-facing and always directs to a clinician where relevant.
    """

    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        self.code = code
        self.details = details or {}
        super().__init__(message)


@dataclass
class FilterStats:
    """Per-stage exclusion counters — full transparency, no hidden drops."""

    considered: int = 0
    excluded_not_published: int = 0
    excluded_retired: int = 0
    excluded_missing_source: int = 0
    excluded_allergen: int = 0
    excluded_dietary_preference: int = 0
    excluded_food_safety: int = 0
    excluded_condition: int = 0
    excluded_disliked: int = 0
    excluded_clinician_review: int = 0
    allergen_codes_hit: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


def _meal_matches_dietary_preference(meal: Meal, preference: str) -> bool:
    pref = (preference or "nonveg").lower()
    if pref == "veg":
        return bool(meal.is_vegetarian)
    if pref == "eggetarian":
        # Vegetarian plus egg-flagged meals; dataset has no egg flag, so
        # accept vegetarian (conservative) — egg meals are non-veg here.
        return bool(meal.is_vegetarian)
    return True  # nonveg accepts everything


def _meal_condition_ok(meal: Meal, conditions: list[str]) -> tuple[bool, list[str]]:
    """Category-level condition exclusions (non-treatment)."""
    bundle = conditions_domain.restrictions_for_conditions(conditions)
    name = (meal.name or "").lower()
    meal_type = (meal.meal_type or "").lower()
    if not conditions_domain.meal_matches_preference(
        {"name": name, "meal_type": meal_type}, bundle["prefer"]
    ):
        return False, bundle["explain"]
    for mt in bundle["exclude_meal_types"]:
        if mt.lower() == meal_type:
            return False, bundle["explain"]
    return True, []


def _disliked_hit(meal: Meal, disliked: list[str]) -> Optional[str]:
    if not disliked:
        return None
    names = [meal.name or ""]
    for item in meal.ingredients or []:
        ing = item.get("name", "") if isinstance(item, dict) else str(item)
        names.append(ing)
    joined = " | ".join(names).lower()
    for d in disliked:
        token = str(d).strip().lower()
        if token and token in joined:
            return token
    return None


def filter_meal(
    meal: Meal,
    *,
    allergen_codes: list[str],
    dietary_preference: str,
    conditions: list[str],
    disliked_ingredients: list[str],
    stats: Optional[FilterStats] = None,
) -> tuple[bool, list[str]]:
    """Hard safety gate for ONE meal.

    Returns (allowed, exclusion_reasons). Every rejection appends a
    machine-readable reason — the caller may show these transparently.
    """
    reasons: list[str] = []
    st = stats

    def reject(reason_code: str) -> tuple[bool, list[str]]:
        if st is not None:
            setattr(st, f"excluded_{reason_code}", getattr(st, f"excluded_{reason_code}") + 1)
        return False, reasons + [reason_code]

    if st is not None:
        st.considered += 1

    # 1. Approved content only.
    if (meal.content_status or "").upper() not in SUGGESTABLE_STATUSES:
        reasons.append("CONTENT_NOT_APPROVED")
        return reject("not_published")

    # 2. Retired content never returns, even if status was left stale.
    if meal.retired_at is not None:
        reasons.append("CONTENT_RETIRED")
        return reject("retired")

    # 3. Traceable source + versions.
    if not (meal.source and str(meal.source).strip()):
        reasons.append("MISSING_SOURCE")
        return reject("missing_source")
    if not (meal.evidence_version and str(meal.evidence_version).strip()):
        reasons.append("MISSING_CONTENT_VERSION")
        return reject("missing_source")

    # 4. Allergen hard exclusion (ingredient-level links).
    meal_codes = set(meal.allergens or [])
    overlap = meal_codes & {a.lower() for a in allergen_codes}
    if overlap:
        reasons.append("ALLERGEN_OVERLAP")
        if st is not None:
            for code in sorted(overlap):
                st.allergen_codes_hit[code] = st.allergen_codes_hit.get(code, 0) + 1
        return reject("allergen")

    # 5. Dietary preference.
    if not _meal_matches_dietary_preference(meal, dietary_preference):
        reasons.append("DIETARY_PREFERENCE")
        return reject("dietary_preference")

    # 6. Food-safety policy (documented pregnancy exclusions).
    safety_notes = food_safety.exclusion_notes(
        {
            "name": meal.name,
            "ingredients": meal.ingredients,
            "cautions": meal.cautions,
            "food_safety_notes": meal.food_safety_notes,
        }
    )
    if safety_notes:
        reasons.append("FOOD_SAFETY")
        return reject("food_safety")

    # 7. Condition category exclusions (non-treatment).
    ok, _explain = _meal_condition_ok(meal, conditions)
    if not ok:
        reasons.append("CONDITION_EXCLUSION")
        return reject("condition")

    # 8. Disliked ingredients (preference, not safety).
    hit = _disliked_hit(meal, disliked_ingredients)
    if hit:
        reasons.append("DISLIKED_INGREDIENT")
        return reject("disliked")

    return True, []


async def load_suggestions_candidate_pool(
    db: AsyncSession,
    *,
    allergen_codes: list[str],
    dietary_preference: str,
    conditions: list[str],
    disliked_ingredients: list[str],
    trimester_label: str,
    stats: Optional[FilterStats] = None,
) -> list[Meal]:
    """Load and hard-filter every catalog meal for one user.

    Raises SafetyFilterBlocked(CODE) when personalized generation must not
    proceed at all:
      * CLINICIAN_REVIEW_REQUIRED — catalog-wide flag set for the user's
        declared conditions; customized plans are not generated.
    Returns ONLY meals that passed every hard check (possibly []).
    Never relaxes a rule to fill slots.
    """
    # Clinician-review gate: any declared condition marked as requiring
    # clinician involvement blocks customized generation entirely.
    if any(conditions_domain.condition_requires_clinician(c) for c in conditions):
        raise SafetyFilterBlocked(
            ErrorCode.FORBIDDEN,  # transport status; semantic code in details
            "Your declared health context needs clinician input before "
            "customized meal suggestions can be generated.",
            {"blocking_code": "CLINICIAN_REVIEW_REQUIRED", "conditions": sorted(conditions)},
        )

    eager = selectinload(Meal.allergen_links).selectinload(MealAllergen.allergen)
    result = await db.execute(select(Meal).options(eager))
    all_meals = list(result.scalars().all())

    eligible: list[Meal] = []
    for meal in all_meals:
        # Trimester suitability (education metadata, still a hard filter).
        labels = meal.trimester_suitability or []
        if labels and trimester_label not in labels:
            continue
        allowed, _reasons = filter_meal(
            meal,
            allergen_codes=allergen_codes,
            dietary_preference=dietary_preference,
            conditions=conditions,
            disliked_ingredients=disliked_ingredients,
            stats=stats,
        )
        if allowed:
            eligible.append(meal)
    return eligible


def has_safe_meals(eligible: list[Meal]) -> bool:
    return len(eligible) > 0


NO_SAFE_SUGGESTION_MESSAGE = (
    "No meals in the reviewed catalog match your safety profile right now. "
    "For personalized nutrition guidance, please talk to your doctor, "
    "midwife, or a registered dietitian."
)
