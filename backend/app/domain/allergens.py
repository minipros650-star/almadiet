"""AlmaDiet — Structured allergen taxonomy and matching engine.

Ingredient-level allergen detection with exact, normalized and synonym
matching. This module decides whether a meal is safe for a user; it is used
BEFORE meal selection (not as a post-filter) and again in the final
validation pass.

Category codes are stable API values (used in the Flutter UI and stored in
health_records.allergies and meal_allergens).
"""

from __future__ import annotations

import re
from enum import Enum

class AllergenCategory(str, Enum):
    PEANUT = "peanut"
    TREE_NUT = "tree_nut"
    MILK = "milk"
    EGG = "egg"
    WHEAT_GLUTEN = "wheat_gluten"
    SOY = "soy"
    FISH = "fish"
    SHELLFISH = "shellfish"
    SESAME = "sesame"
    MUSTARD = "mustard"
    SULFITE = "sulfite"
    OTHER = "other"


# Canonical display names per category.
DISPLAY_NAMES: dict[str, str] = {
    AllergenCategory.PEANUT.value: "Peanut",
    AllergenCategory.TREE_NUT.value: "Tree nuts",
    AllergenCategory.MILK.value: "Milk / dairy",
    AllergenCategory.EGG.value: "Egg",
    AllergenCategory.WHEAT_GLUTEN.value: "Wheat / gluten",
    AllergenCategory.SOY.value: "Soy",
    AllergenCategory.FISH.value: "Fish",
    AllergenCategory.SHELLFISH.value: "Shellfish",
    AllergenCategory.SESAME.value: "Sesame",
    AllergenCategory.MUSTARD.value: "Mustard",
    AllergenCategory.SULFITE.value: "Sulfites",
    AllergenCategory.OTHER.value: "Other allergen",
}


def normalize_term(term: str) -> str:
    """Lowercase, strip punctuation/plurals for tolerant matching."""
    t = term.lower().strip()
    t = re.sub(r"[^a-z\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 3 and t.endswith("es"):
        t = t[:-2]
    elif len(t) > 3 and t.endswith("s"):
        t = t[:-1]
    return t


# category → terms that indicate the allergen is present.
# Normalized (lowercase, singular); matching is substring-based in both
# directions for multi-word terms ("peanut butter" vs "butter peanut").
SYNONYMS: dict[str, tuple[str, ...]] = {
    AllergenCategory.PEANUT.value: (
        "peanut", "groundnut", "ground nut", "goober", "nut pea",
        "mandelona", "peanut butter", "peanut flour", "peanut oil",
        "arachis oil",
    ),
    AllergenCategory.TREE_NUT.value: (
        "almond", "cashew", "walnut", "pistachio", "pecan", "hazelnut",
        "hazel nut", "macadamia", "brazil nut", "pine nut", "shea nut",
        "nut",  # word-boundary matched (see WORD_BOUNDARY_TERMS)
    ),
    AllergenCategory.MILK.value: (
        "milk", "dairy", "curd", "curd ", "yogurt", "yoghurt", "ghee",
        "butter", "paneer", "cheese", "buttermilk", "cream", "khoya",
        "mawa", "whey", "casein", "lassi", "panir",
        "cow milk", "buffalo milk", "full cream milk", "toned milk",
    ),
    AllergenCategory.EGG.value: ("egg", "mayonnaise", "mayo", "albumin"),
    AllergenCategory.WHEAT_GLUTEN.value: (
        "wheat", "maida", "atta", "gluten", "semolina", "rava", "suji",
        "bread", "pasta", "noodle", "barley", "rye", "vermicelli",
        "sevai", "breadcrumb",
    ),
    AllergenCategory.SOY.value: (
        "soy", "soya", "tofu", "edamame", "miso", "tempeh", "soy sauce",
        "soybean", "soy bean",
    ),
    AllergenCategory.FISH.value: (
        "fish", "sardine", "anchovy", "pomfret", "mackerel", "seer",
        "tuna", "salmon", "meen", "mathi", "netholi", "ayila", "tilapia",
        "basa", "cod", "fish sauce",
    ),
    AllergenCategory.SHELLFISH.value: (
        "prawn", "shrimp", "crab", "lobster", "clam", "mussel", "oyster",
        "squid", "scallop", "crayfish", "konju", "chemmeen",
    ),
    AllergenCategory.SESAME.value: (
        "sesame", "til ", "ellu", "tahini", "gingelly", "sesame oil",
    ),
    AllergenCategory.MUSTARD.value: ("mustard", "kadugu", "sarson", "rai seeds"),
    AllergenCategory.SULFITE.value: (
        "sulfite", "sulphite", "sulphur dioxide", "sodium metabisulphite",
        "wine vinegar",
    ),
}


def _terms_for(category: str) -> tuple[str, ...]:
    return tuple(normalize_term(t) for t in SYNONYMS.get(category, ()))


# Ingredient names that contain a generic allergen word but are NOT that
# allergen (e.g. coconut milk contains no dairy). Matched as exceptions
# before the normal term scan.
NEGATIVE_OVERRIDES: tuple[str, ...] = (
    "coconut milk", "coconut cream", "coconut butter", "coconut curd",
    "peanut butter", "almond butter", "cashew butter", "sesame butter",
    "soy butter", "seed butter", "nut milk", "coconut oil",
)


def _is_negative_override(normalized: str) -> bool:
    return any(override in normalized for override in NEGATIVE_OVERRIDES)


# Generic single words that must only match as a WHOLE WORD — substring
# matching would otherwise fire inside "groundnut" (peanut), "coconut"
# (not a tree nut), "nutmeg" (not a tree nut), "donut" etc.
WORD_BOUNDARY_TERMS = frozenset({"nut", "nut "})


def match_ingredient(ingredient_name: str) -> set[str]:
    """Return the set of allergen category codes an ingredient name triggers.

    Longest-match-wins: a specific multi-word term ("peanut butter")
    suppresses shorter generic terms ("butter" → milk) contained within it,
    so compound ingredient names never trigger false positives from their
    own substrings.
    """
    normalized = normalize_term(ingredient_name)
    if not normalized:
        return set()

    # "peanut butter" itself must still signal peanut even though it is an
    # override for milk: strip the override words and re-scan the remainder.
    remainder = normalized
    for override in NEGATIVE_OVERRIDES:
        # Word-boundary strip so "nut milk" does not eat "coco(nut milk)".
        pattern = rf"\b{re.escape(override)}\b"
        if re.search(pattern, remainder):
            remainder = re.sub(pattern, " ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip()

    # Collect all (term_length, category, term) hits first.
    hits: list[tuple[int, str, str]] = []
    # Scan the remainder (override words like "coconut milk" removed); when
    # the whole input was an override, only explicit terms for the override's
    # own allergen apply (e.g. "peanut butter" → peanut via name check).
    scan_target = remainder if remainder else ""
    for category in AllergenCategory:
        if category is AllergenCategory.OTHER:
            continue
        for term in _terms_for(category.value):
            if not term:
                continue
            if term in WORD_BOUNDARY_TERMS:
                # Whole-word match only: "nut" must not hit "groundnut".
                if re.search(rf"\b{re.escape(term.strip())}\b", scan_target):
                    hits.append((len(term), category.value, term))
            elif term in scan_target:
                hits.append((len(term), category.value, term))

    found: set[str] = set()
    for _, category, term in hits:
        found.add(category)

    # Override phrases map to their OWN allergen explicitly: "peanut butter"
    # → peanut, "almond butter" → tree_nut, "soy butter" → soy.
    OVERRIDE_OWN_CATEGORY = {
        "peanut butter": AllergenCategory.PEANUT.value,
        "almond butter": AllergenCategory.TREE_NUT.value,
        "cashew butter": AllergenCategory.TREE_NUT.value,
        "sesame butter": AllergenCategory.SESAME.value,
        "soy butter": AllergenCategory.SOY.value,
        "nut milk": AllergenCategory.TREE_NUT.value,
    }
    for override, category in OVERRIDE_OWN_CATEGORY.items():
        if re.search(rf"\b{re.escape(override)}\b", normalized):
            found.add(category)

    return found


def allergens_for_ingredients(
    ingredients: list[dict] | list[str] | None,
) -> dict[str, list[str]]:
    """Map category code → matched ingredient terms for a meal's ingredients.

    Accepts [{"name": "...", "quantity": "..."}] (dataset shape) or ["..."].
    """
    matched: dict[str, list[str]] = {}
    if not ingredients:
        return matched
    for item in ingredients:
        if isinstance(item, dict):
            name = str(item.get("name", ""))
        else:
            name = str(item)
        if not name:
            continue
        for category in match_ingredient(name):
            matched.setdefault(category, []).append(name)
    return matched


def meal_contains_any(
    ingredients: list[dict] | list[str] | None,
    user_allergies: list[str] | set[str],
) -> dict[str, list[str]]:
    """Return ONLY the categories that intersect the user's allergies.

    The result maps allergen category → matched ingredient names. An empty
    result means the meal passed the allergen filter for this user.
    """
    user_set = {
        a.strip().lower() for a in (user_allergies or []) if a and a.strip()
    }
    if not user_set:
        return {}
    all_matched = allergens_for_ingredients(ingredients)
    return {k: v for k, v in all_matched.items() if k in user_set}


CATEGORY_DISPLAY = dict(DISPLAY_NAMES)


def check_user_allergies(
    user_allergies: list[str] | set[str],
    meal_allergen_categories: list[str] | set[str] | None,
    ingredients: list[dict] | list[str] | None = None,
    meal_name: str = "",
) -> set[str]:
    """Return user-allergy categories triggered by this meal.

    Checks three layers, in order of reliability:
      1. curated meal_allergen categories (from meal_allergens table),
      2. ingredient-level matching via the taxonomy,
      3. the meal NAME itself (e.g. "Peanut Chikki"), as a last net.
    """
    user_set = {
        a.strip().lower() for a in (user_allergies or []) if a and a.strip()
    }
    if not user_set:
        return set()

    found: set[str] = set()
    for category in (meal_allergen_categories or []):
        code = str(category).strip().lower()
        if code in user_set:
            found.add(code)

    if ingredients is not None:
        matched = allergens_for_ingredients(ingredients)
        found |= {c for c in matched if c in user_set}

    if meal_name:
        for category in match_ingredient(meal_name):
            if category in user_set:
                found.add(category)

    return found


# Known cross-contact phrases — meals whose *preparation* may introduce
# traces even if ingredients are clean. These never hard-block (that would
# hide genuinely safe meals) but must surface a warning.
CROSS_CONTACT_TERMS = (
    "shared equipment", "may contain traces", "processed in a facility",
    "roasted nut", "nut powder", "fried in nut oil",
)


def cross_contact_warning(text: str | None) -> bool:
    """True if free-text (cautions/preparation) suggests cross-contact risk."""
    if not text:
        return False
    t = normalize_term(text)
    return any(normalize_term(term) in t for term in CROSS_CONTACT_TERMS)


def cross_contamination_risk(
    text_fields: dict[str, str | None], user_allergies: list[str]
) -> list[str]:
    """Display names of the user's allergies needing a cross-contact warning."""
    joined = " ".join(str(v or "") for v in text_fields.values())
    if not cross_contact_warning(joined):
        return []
    return sorted(
        DISPLAY_NAMES.get(a.strip().lower(), a)
        for a in (user_allergies or [])
        if a and a.strip()
    )
