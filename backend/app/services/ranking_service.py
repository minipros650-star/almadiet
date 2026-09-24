"""AlmaDiet — Deterministic preference ranking for eligible meals.

Ranking happens ONLY on meals that already passed the hard safety filter
(meal_safety_service). Ranking is preference ordering, never safety.

Determinism contract: for the same (profile, catalog_version,
ranking_version) the ordering is identical across runs. There is NO
randomness — selection takes a stable top-N slice instead of sampling.

RANKING_VERSION increments whenever factor weights change.
"""

from __future__ import annotations

from typing import Optional

RANKING_VERSION = "1.0.0"

# Weights (documented, reviewable). Ties break by stable meal id so the
# total order is fully determined.
WEIGHTS = {
    "region_match": 30,
    "dietary_preference_match": 20,
    "favorite": 15,
    "cooking_time": 12,
    "budget": 8,
    "positive_feedback": 6,
    "negative_feedback": -10,
    "disliked_penalty": -40,  # belt & braces — filter already drops these
}

_SLOT_MEAL_TYPES: dict[str, tuple[str, ...]] = {
    "breakfast": ("breakfast",),
    "lunch": ("lunch",),
    "dinner": ("dinner", "snack / light dinner"),
    "snack": ("snack", "beverage", "dessert"),
}


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _region_matches(meal_region: str, user_region: str) -> bool:
    m, u = _norm(meal_region), _norm(user_region)
    if not u:
        return False
    # User region codes (kerala, tamilnadu, ...) appear in meal region text
    # ("Kerala"), with legacy synonyms.
    synonyms = {
        "kerala": ("kerala",),
        "tamilnadu": ("tamil", "tamilnadu"),
        "karnataka": ("karnataka",),
        "andhra": ("andhra",),
    }
    return any(s in m for s in synonyms.get(u, (u,)))


def _cooking_time_score(meal, preference: Optional[str]) -> int:
    if not preference:
        return 0
    t = meal.preparation_time_minutes
    if t is None:
        return 0
    pref = _norm(preference)
    if pref == "quick":
        return WEIGHTS["cooking_time"] if t <= 20 else 0
    if pref == "moderate":
        return WEIGHTS["cooking_time"] if 15 <= t <= 45 else 0
    if pref == "relaxed":
        return WEIGHTS["cooking_time"] if t >= 25 else 0
    return 0


def _budget_score(meal, preference: Optional[str]) -> int:
    """Budget fit via simple ingredient-count proxy (documented heuristic)."""
    if not preference:
        return 0
    n_ingredients = len(meal.ingredients or [])
    simple = n_ingredients <= 6
    if _norm(preference) == "low":
        return WEIGHTS["budget"] if simple else 0
    if _norm(preference) == "medium":
        return WEIGHTS["budget"] if n_ingredients <= 10 else 0
    return WEIGHTS["budget"]  # high: no penalty


def score_meal(
    meal,
    *,
    user_region: Optional[str],
    dietary_preference: str,
    cooking_time_preference: Optional[str],
    budget_preference: Optional[str],
    favorite_ids: set[str],
    feedback_scores: dict[str, int],
) -> tuple[int, list[str]]:
    """Deterministic preference score for an already-safe meal.

    Returns (score, why_chips). ``why_chips`` are user-facing, honest
    reason strings for the UI ("why suggested" chips).
    """
    score = 0
    chips: list[str] = []

    pref = _norm(dietary_preference)
    if pref == "veg" and meal.is_vegetarian:
        score += WEIGHTS["dietary_preference_match"]
        chips.append("vegetarian preference")

    if _region_matches(getattr(meal, "region", ""), user_region or ""):
        score += WEIGHTS["region_match"]
        chips.append("matches your region")

    ct = _cooking_time_score(meal, cooking_time_preference)
    if ct:
        score += ct
        chips.append("quick preparation" if _norm(cooking_time_preference) == "quick" else "fits your cooking time")

    bs = _budget_score(meal, budget_preference)
    if bs:
        score += bs
        chips.append("fits your budget preference")

    if str(meal.id) in favorite_ids:
        score += WEIGHTS["favorite"]
        chips.append("meal you saved")

    fb = feedback_scores.get(str(meal.id), 0)
    if fb > 0:
        score += WEIGHTS["positive_feedback"]
        chips.append("you rated similar meals highly")
    elif fb < 0:
        score += WEIGHTS["negative_feedback"]

    return score, chips


def rank_meals(
    meals: list,
    *,
    user_region: Optional[str],
    dietary_preference: str,
    cooking_time_preference: Optional[str],
    budget_preference: Optional[str],
    favorite_ids: set[str],
    feedback_scores: dict[str, int],
) -> list[tuple[object, int, list[str]]]:
    """Stable total order over safe meals.

    Sort key: (-score, meal_id) — descending preference, ascending id for
    ties. Fully deterministic: no randomness anywhere.
    """
    scored: list[tuple[int, str, object, list[str]]] = []
    for meal in meals:
        s, chips = score_meal(
            meal,
            user_region=user_region,
            dietary_preference=dietary_preference,
            cooking_time_preference=cooking_time_preference,
            budget_preference=budget_preference,
            favorite_ids=favorite_ids,
            feedback_scores=feedback_scores,
        )
        scored.append((s, str(meal.id), meal, chips))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [(meal, s, chips) for s, _mid, meal, chips in scored]


def slot_for_meal_type(meal_type: str) -> Optional[str]:
    mt = _norm(meal_type)
    for slot, patterns in _SLOT_MEAL_TYPES.items():
        for p in patterns:
            if mt == p or (p in mt and slot == "snack"):
                return slot
    if "breakfast" in mt:
        return "breakfast"
    if "lunch" in mt:
        return "lunch"
    if "dinner" in mt:
        return "dinner"
    return "snack"
