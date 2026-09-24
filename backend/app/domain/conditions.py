"""AlmaDiet — Condition-related food restrictions.

NON-TREATMENT RULES. The app never prescribes, treats, or doses. For a
user-declared context these functions only:
  1. prefer/exclude broad food categories where a documented safety rationale
     exists, and
  2. produce an explanation string that always defers to the clinician.

Every rule here is mirrored in docs/CLINICAL_SAFETY.md §3 — a PR changing one
must change both.
"""

from __future__ import annotations

from enum import Enum


class MedicalCondition(str, Enum):
    GESTATIONAL_DIABETES = "gestational_diabetes"
    HYPERTENSION = "hypertension"
    PREECLAMPSIA_HISTORY = "preeclampsia_history"
    ANEMIA = "anemia"
    SEVERE_NAUSEA_VOMITING = "severe_nausea_vomiting"
    MEDICATION_CONSTRAINED = "medication_constrained"
    OTHER = "other"


VALID_CONDITION_CODES = {c.value for c in MedicalCondition} - {MedicalCondition.OTHER.value}


# Meal-type text markers used for category-based preference/exclusion.
DESSERT_MARKERS = ("dessert", "payasam", "kheer", "sweet", "halwa", "gulab")
SPICY_MARKERS = ("spicy", "pickle", "chilli", "mirchi", "gongura")
FRIED_MARKERS = ("fried", "pappadam", "papad", "pur i", "puri", "bhaji", "vada")


def _has_marker(meal_name: str, markers: tuple[str, ...]) -> bool:
    n = meal_name.lower()
    return any(m in n for m in markers)


def restrictions_for_conditions(
    conditions: list[str],
) -> dict:
    """Build a restriction/explanation bundle for declared conditions.

    Returns:
        {
            "prefer": [tag, ...],          # selection boosts
            "exclude_meal_types": [...],   # hard category exclusions
            "explain": [str, ...],         # user-facing explanation strings
        }
    User-facing strings ALWAYS defer to the clinician and never instruct
    treatment.
    """
    prefer: list[str] = []
    exclude_meal_types: list[str] = []
    explain: list[str] = []
    codes = {c.strip().lower() for c in (conditions or []) if c and c.strip()}

    if MedicalCondition.GESTATIONAL_DIABETES.value in codes:
        prefer.append("lower_sugar")
        exclude_meal_types.append("Dessert")
        explain.append(
            "Meal ideas chosen with lower-sugar options in mind. "
            "Blood-sugar targets in pregnancy should be guided by your clinician."
        )

    if (
        MedicalCondition.HYPERTENSION.value in codes
        or MedicalCondition.PREECLAMPSIA_HISTORY.value in codes
    ):
        prefer.append("lower_sodium")
        exclude_meal_types.append("Condiment")
        explain.append(
            "Lower-sodium meal ideas selected. Sodium management in pregnancy "
            "should be discussed with your clinician."
        )

    if MedicalCondition.ANEMIA.value in codes:
        prefer.append("iron_rich")
        explain.append(
            "Iron-rich meal ideas included. Whether you need iron supplements "
            "is a decision for your clinician."
        )

    if MedicalCondition.SEVERE_NAUSEA_VOMITING.value in codes:
        prefer.append("gentle")
        exclude_meal_types.extend(["Condiment", "Dessert"])
        explain.append(
            "Gentler, less spicy meal ideas selected. Persistent vomiting in "
            "pregnancy needs clinician review."
        )

    if MedicalCondition.MEDICATION_CONSTRAINED.value in codes:
        explain.append(
            "Some foods can interact with medicines. Your clinician or "
            "pharmacist can advise on your specific medication."
        )

    if MedicalCondition.OTHER.value in codes and len(explain) == 0:
        explain.append(
            "Personalized medical nutrition advice requires clinician guidance; "
            "these are general meal ideas only."
        )

    return {
        "prefer": sorted(set(prefer)),
        "exclude_meal_types": sorted(set(exclude_meal_types)),
        "explain": explain,
    }


def explanations_for_conditions(conditions_list: list[str]) -> list[str]:
    """User-facing explanation strings (see restrictions_for_conditions)."""
    return restrictions_for_conditions(conditions_list)["explain"]


# ── Preference helpers used by the selection scorer ──────────────────────

def prefers_lower_sodium(conditions: list[str]) -> bool:
    return MedicalCondition.HYPERTENSION.value in {c.lower() for c in conditions or ()} or (
        MedicalCondition.PREECLAMPSIA_HISTORY.value in {c.lower() for c in conditions or ()}
    )


def prefers_lower_sugar(conditions: list[str]) -> bool:
    return MedicalCondition.GESTATIONAL_DIABETES.value in {c.lower() for c in conditions or ()}


def prefers_iron_rich(conditions: list[str]) -> bool:
    return MedicalCondition.ANEMIA.value in {c.lower() for c in conditions or ()}


def prefers_gentle(conditions: list[str]) -> bool:
    return MedicalCondition.SEVERE_NAUSEA_VOMITING.value in {c.lower() for c in conditions or ()}


def condition_requires_clinician(condition: str) -> bool:
    """True when a declared condition requires clinician involvement before
    customized suggestion generation (policy documented in
    docs/CLINICAL_SAFETY.md §3).

    GDM, hypertension/preeclampsia history, and medication-constrained
    diets need personalized clinical management, so AlmaDiet must not
    auto-generate customized plans for them.
    """
    return str(condition).strip().lower() in {
        MedicalCondition.GESTATIONAL_DIABETES.value,
        MedicalCondition.HYPERTENSION.value,
        MedicalCondition.PREECLAMPSIA_HISTORY.value,
        MedicalCondition.MEDICATION_CONSTRAINED.value,
    }


def meal_matches_preference(meal, prefer: list[str]) -> bool:
    """True if the meal satisfies hard category exclusions implied by `prefer`.

    Hard exclusions are carried via `exclude_meal_types`; this helper checks
    the text-level dessert/spice rules for prefer tags.
    """
    name = meal.get("name", "") if isinstance(meal, dict) else getattr(meal, "name", "")
    mtype = meal.get("meal_type", "") if isinstance(meal, dict) else getattr(meal, "meal_type", "")
    if "lower_sugar" in prefer and (
        "Dessert" == mtype or _has_marker(name, DESSERT_MARKERS)
    ):
        return False
    if "gentle" in prefer and _has_marker(name, SPICY_MARKERS):
        return False
    return True


def condition_exclusions(meal: dict, user_conditions: list[str]) -> list[str]:
    """Condition codes for which this meal must be EXCLUDED.

    Conservative and documented: desserts excluded for GDM; salty condiments
    excluded for hypertension/preeclampsia history; spicy/dessert items
    excluded for severe nausea. Returns [] when the meal passes.
    """
    codes = {c.strip().lower() for c in (user_conditions or []) if c and c.strip()}
    if not codes:
        return []
    excluded: list[str] = []
    name = str(meal.get("name", ""))
    mtype = str(meal.get("meal_type", ""))
    sugar = meal.get("sugar_g") or 0
    sodium = meal.get("sodium_mg") or 0

    if MedicalCondition.GESTATIONAL_DIABETES.value in codes:
        if mtype == "Dessert" or _has_marker(name, DESSERT_MARKERS) or sugar > 25:
            excluded.append(MedicalCondition.GESTATIONAL_DIABETES.value)

    if (
        MedicalCondition.HYPERTENSION.value in codes
        or MedicalCondition.PREECLAMPSIA_HISTORY.value in codes
    ):
        if mtype == "Condiment" or sodium > 800:
            excluded.append(MedicalCondition.HYPERTENSION.value)

    if MedicalCondition.SEVERE_NAUSEA_VOMITING.value in codes:
        if _has_marker(name, SPICY_MARKERS) or mtype == "Condiment":
            excluded.append(MedicalCondition.SEVERE_NAUSEA_VOMITING.value)

    return excluded
