"""
AlmaDiet — Central Safety Validator.

Single choke-point used by plan generation, meal swap, and browse filtering.
Allergy filtering happens BEFORE selection (candidates that fail are never
returned), and `validate_meal` is re-run on every selected meal as a final
gate (defence in depth). No other module may bypass this service.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain import allergens, conditions, food_safety, content_state


@dataclass
class MealView:
    """
    Framework-agnostic view of a meal for safety checks. Built from the ORM
    Meal or a stored plan MealCard dict.
    """

    id: str
    name: str
    meal_type: str
    allergens: list[str] = field(default_factory=list)
    ingredients: list[dict] | None = None
    sugar_g: float | None = None
    sodium_mg: float | None = None
    content_status: str | None = None
    cautions: str | None = None
    food_safety_notes: str | None = None

    @classmethod
    def from_orm(cls, meal) -> "MealView":
        return cls(
            id=str(meal.id),
            name=meal.name,
            meal_type=meal.meal_type,
            allergens=list(meal.allergens or []),
            ingredients=meal.ingredients,
            sugar_g=meal.sugar_g,
            sodium_mg=meal.sodium_mg,
            content_status=meal.content_status,
            cautions=meal.cautions,
            food_safety_notes=meal.food_safety_notes,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "MealView":
        return cls(
            id=str(d.get("id", "")),
            name=str(d.get("name", "")),
            meal_type=str(d.get("meal_type", "")),
            allergens=list(d.get("allergens") or []),
            ingredients=d.get("ingredients"),
            sugar_g=d.get("sugar_g"),
            sodium_mg=d.get("sodium_mg"),
            content_status=d.get("content_status"),
            cautions=d.get("cautions"),
            food_safety_notes=d.get("food_safety_notes"),
        )


@dataclass
class SafetyResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)        # machine codes
    explanations: list[str] = field(default_factory=list)   # user-facing strings
    cross_contact: list[str] = field(default_factory=list)  # display names


class SafetyValidator:
    """
    Stateless validator combining all safety filters. Order matters:
    allergies first (hard exclusion), then conditions, food safety, content.
    """

    def __init__(self, include_statuses: frozenset[str] | None = None) -> None:
        self.include_statuses = include_statuses or content_state.DEFAULT_INCLUDE_STATUSES

    # ── Individual checks ─────────────────────────────────────
    def _allergy_check(
        self, view: MealView, user_allergies: list[str]
    ) -> tuple[bool, list[str], list[str]]:
        found = allergens.check_user_allergies(
            user_allergies, view.allergens, view.ingredients, view.name
        )
        if not found:
            return True, [], []
        display = [allergens.CATEGORY_DISPLAY.get(c, c) for c in found]
        return (
            False,
            [f"ALLERGEN:{c}" for c in found],
            [f"Excluded: contains {', '.join(display)} — matched your allergy."],
        )

    def _condition_check(
        self, view: MealView, user_conditions: list[str]
    ) -> tuple[bool, list[str], list[str]]:
        excluded = conditions.condition_exclusions(
            {
                "meal_type": view.meal_type,
                "ingredients": view.ingredients,
                "sugar_g": view.sugar_g,
                "sodium_mg": view.sodium_mg,
            },
            user_conditions,
        )
        if not excluded:
            return True, [], []
        return (
            False,
            [f"CONDITION:{c}" for c in excluded],
            ["Excluded: not suitable for a condition you have told us about."],
        )

    def _food_safety_check(self, view: MealView) -> tuple[bool, list[str], list[str]]:
        meal = {
            "ingredients": view.ingredients,
            "cautions": view.cautions,
            "food_safety_notes": view.food_safety_notes,
        }
        notes = food_safety.exclusion_notes(meal)
        if not notes:
            return True, [], []
        return False, ["FOOD_SAFETY"], notes

    def _content_check(self, view: MealView) -> tuple[bool, list[str], list[str]]:
        if view.content_status is None:
            return True, [], []
        if content_state.is_recommendable(view.content_status, self.include_statuses):
            return True, [], []
        return (
            False,
            ["CONTENT_NOT_PUBLISHED"],
            ["Excluded: content is not published for production use."],
        )

    # ── Public API ─────────────────────────────────────────────
    def validate_meal(
        self,
        view: MealView,
        user_allergies: list[str] | None = None,
        user_conditions: list[str] | None = None,
    ) -> SafetyResult:
        """Full safety validation of a single meal. Used as the FINAL gate."""
        reasons: list[str] = []
        explanations: list[str] = []
        allowed = True

        ok, r, e = self._allergy_check(view, user_allergies or [])
        if not ok:
            allowed = False
            reasons += r
            explanations += e

        ok, r, e = self._condition_check(view, user_conditions or [])
        if not ok:
            allowed = False
            reasons += r
            explanations += e

        ok, r, e = self._food_safety_check(view)
        if not ok:
            allowed = False
            reasons += r
            explanations += e

        ok, r, e = self._content_check(view)
        if not ok:
            allowed = False
            reasons += r
            explanations += e

        cross = allergens.cross_contamination_risk(
            {"cautions": view.cautions, "food_safety_notes": view.food_safety_notes},
            user_allergies or [],
        )
        return SafetyResult(
            allowed=allowed, reasons=reasons, explanations=explanations, cross_contact=cross
        )

    def filter_candidates(
        self,
        views: list[MealView],
        user_allergies: list[str] | None = None,
        user_conditions: list[str] | None = None,
    ) -> list[MealView]:
        """
        Pre-selection filter. Meals failing ANY safety rule are dropped
        BEFORE selection can consider them.
        """
        safe: list[MealView] = []
        for v in views:
            if self.validate_meal(v, user_allergies, user_conditions).allowed:
                safe.append(v)
        return safe


def build_validator(production: bool, config_statuses: str = "") -> SafetyValidator:
    """Build a validator with statuses resolved from config (never widens in prod)."""
    return SafetyValidator(
        content_state.statuses_from_config(config_statuses, production)
    )
