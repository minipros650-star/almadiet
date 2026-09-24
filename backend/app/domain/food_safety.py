"""AlmaDiet — General pregnancy food-safety filters.

Documented, conservative exclusions based on widely published food-safety
guidance for pregnancy (raw/undercooked animal products, high-mercury fish,
unpasteurized dairy, alcohol). Each exclusion carries a user-facing reason.

This is food-safety information, not medical treatment.
"""

from __future__ import annotations

# ingredient-name fragments (normalized) that hard-exclude a meal.
UNSAFE_INGREDIENT_TERMS: tuple[str, ...] = (
    "raw egg", "raw meat", "raw fish", "undercooked", "rare meat",
    "sushi (raw)", "sashimi", "raw sprout", "unpasteurized", "unpasteurised",
    "raw milk", "raw papaya", "alcohol", "wine", "beer", "rum", "brandy",
    "high mercury", "shark", "swordfish", "king mackerel", "tilefish",
    "liver (raw)",
)


def normalize(text: str) -> str:
    import re
    t = text.lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


def unsafe_reason_for_ingredient(ingredient_name: str) -> str | None:
    """Return a user-facing safety reason if the ingredient is excluded."""
    n = normalize(ingredient_name)
    for term in UNSAFE_INGREDIENT_TERMS:
        if normalize(term) in n:
            return (
                f"'{ingredient_name}' is excluded during pregnancy as a "
                "general food-safety precaution."
            )
    return None


def meal_unsafe_reasons(meal) -> list[str]:
    """All food-safety reasons for a meal (empty list = passes)."""
    reasons: list[str] = []
    name = meal.get("name", "") if isinstance(meal, dict) else getattr(meal, "name", "")
    ingredients = (
        meal.get("ingredients")
        if isinstance(meal, dict)
        else getattr(meal, "ingredients", None)
    ) or []
    if r := unsafe_reason_for_ingredient(name):
        reasons.append(r)
    for item in ingredients:
        ing = item.get("name", "") if isinstance(item, dict) else str(item)
        if r := unsafe_reason_for_ingredient(ing):
            reasons.append(r)
    return reasons


# Free-text fields also scanned (cautions / food_safety_notes).
UNSAFE_TEXT_TERMS: tuple[str, ...] = (
    "raw egg", "unpasteurized", "unpasteurised", "raw milk", "alcohol",
    "contains wine", "contains beer", "raw sprout",
)


def exclusion_notes(meal: dict) -> list[str]:
    """User-facing exclusion notes for a meal dict (ingredients + text)."""
    notes = list(meal_unsafe_reasons(meal))
    for key in ("cautions", "food_safety_notes"):
        text = str(meal.get(key) or "")
        n = normalize(text)
        for term in UNSAFE_TEXT_TERMS:
            if normalize(term) in n:
                notes.append(
                    f"Excluded as a general food-safety precaution ({term})."
                )
                break
    # de-duplicate while preserving order
    seen: set[str] = set()
    unique = [x for x in notes if not (x in seen or seen.add(x))]
    return unique
