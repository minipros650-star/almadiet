"""AlmaDiet — Pure safety & validation domain logic.

No I/O, no ORM, no framework imports. Everything here is unit-testable in
isolation and is the single source of truth for safety rules.
"""

from app.domain.gestational import (
    TRIMESTER_WEEK_RANGES,
    GestationalValidationError,
    validate_gestational_age,
    trimester_for_week,
)
from app.domain.allergens import (
    AllergenCategory,
    match_ingredient,
    allergens_for_ingredients,
    meal_contains_any,
    normalize_term,
)
from app.domain.conditions import (
    MedicalCondition,
    restrictions_for_conditions,
    prefers_lower_sodium,
    prefers_lower_sugar,
    prefers_iron_rich,
    prefers_gentle,
)
from app.domain.food_safety import unsafe_reason_for_ingredient
from app.domain.content_state import ContentStatus, can_transition, transition

__all__ = [
    "TRIMESTER_WEEK_RANGES",
    "GestationalValidationError",
    "validate_gestational_age",
    "trimester_for_week",
    "AllergenCategory",
    "match_ingredient",
    "allergens_for_ingredients",
    "meal_contains_any",
    "normalize_term",
    "MedicalCondition",
    "restrictions_for_conditions",
    "prefers_lower_sodium",
    "prefers_lower_sugar",
    "prefers_iron_rich",
    "prefers_gentle",
    "unsafe_reason_for_ingredient",
    "ContentStatus",
    "can_transition",
    "transition",
]
