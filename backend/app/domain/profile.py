"""AlmaDiet — Pregnancy profile domain (server-authoritative).

Everything in this module is computed ONLY on the server:

* ``pre_pregnancy_bmi`` is derived from height + pre-pregnancy weight.
  Users can never submit a BMI value; the schema layer rejects the field
  and the persistence layer ignores it even if present.
* ``gestational_week`` / ``trimester`` derive from LMP or a clinician
  confirmed due date — never from user-selected week numbers.
* ``profile_completion`` lists exactly what is missing before
  personalized suggestions may be generated.

BMI is context, never a target: it is passed to a versioned, explicit
clinician-approved policy (app.domain.nutrition_policy). With no approved
policy loaded, BMI is display-only and cannot influence suggestions.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from app.domain.gestational import (
    MAX_WEEK,
    MIN_WEEK,
    trimester_for_week,
)

# Naegele's rule: 280 days from LMP.
_GESTATION_DAYS = 280

# Fields the profile requires before personalized suggestions.
REQUIRED_PROFILE_FIELDS = (
    "height_cm",
    "pre_pregnancy_weight_kg",
    "gestation_date",
    "region",
    "dietary_preference",
    "allergies",  # may legitimately be [] but must be declared
)


class ProfileDataError(ValueError):
    """Raised for contradictory or invalid pregnancy profile data."""

    def __init__(self, message: str, code: str = "INVALID_PROFILE"):
        self.code = code
        super().__init__(message)


# ── BMI (server-only) ────────────────────────────────────────────


def calculate_pre_pregnancy_bmi(
    pre_pregnancy_weight_kg: float, height_cm: float
) -> float:
    """pre_pregnancy_bmi = kg / (m)^2, rounded to 1 decimal.

    Raises ProfileDataError on out-of-range inputs so callers can reject
    the request rather than persist a nonsensical value.
    """
    if not (30 <= pre_pregnancy_weight_kg <= 200):
        raise ProfileDataError(
            "Pre-pregnancy weight must be between 30 and 200 kg.",
            "INVALID_WEIGHT",
        )
    if not (100 <= height_cm <= 250):
        raise ProfileDataError(
            "Height must be between 100 and 250 cm.",
            "INVALID_HEIGHT",
        )
    height_m = height_cm / 100.0
    if height_m <= 0 or math.isnan(height_m) or math.isinf(height_m):
        raise ProfileDataError("Height must be a positive number.", "INVALID_HEIGHT")
    bmi = pre_pregnancy_weight_kg / (height_m**2)
    if not (10 <= bmi <= 60):
        # Implausible for any human — refuse rather than store.
        raise ProfileDataError(
            "The height/weight combination gives an implausible BMI.",
            "INVALID_BMI",
        )
    return round(bmi, 1)


# ── Gestational age from dates ───────────────────────────────────


def _reference_date(lmp_date: Optional[date], due_date: Optional[date]) -> tuple[date, str]:
    """Resolve the single pregnancy reference date.

    Precedence: LMP first (user-recorded), else clinician-confirmed due
    date. Providing both is allowed, but they must agree within 14 days —
    a wider gap means contradictory data and is rejected.
    """
    if lmp_date is None and due_date is None:
        raise ProfileDataError(
            "Either last menstrual period (LMP) date or a clinician-confirmed "
            "due date is required.",
            "MISSING_GESTATION_DATE",
        )

    if lmp_date is not None and due_date is not None:
        implied_due = lmp_date + timedelta(days=_GESTATION_DAYS)
        gap = abs((implied_due - due_date).days)
        if gap > 14:
            raise ProfileDataError(
                "The LMP date and due date disagree by more than two weeks. "
                "Please check the dates or confirm with your clinician.",
                "CONTRADICTORY_DATES",
            )

    if lmp_date is not None:
        if lmp_date > date.today():
            raise ProfileDataError(
                "The LMP date cannot be in the future.", "INVALID_LMP"
            )
        earliest = date.today() - timedelta(days=_GESTATION_DAYS + 42)
        if lmp_date < earliest:
            raise ProfileDataError(
                "The LMP date is more than 42 weeks in the past — please "
                "verify it or contact your clinician.",
                "INVALID_LMP",
            )
        return lmp_date, "lmp"

    assert due_date is not None
    if due_date <= date.today() - timedelta(days=7 * MAX_WEEK):
        raise ProfileDataError(
            "The due date implies the pregnancy is already past 42 weeks.",
            "INVALID_DUE_DATE",
        )
    return due_date - timedelta(days=_GESTATION_DAYS), "due_date"


def derive_gestational_age(
    lmp_date: Optional[date] = None,
    due_date: Optional[date] = None,
    today: Optional[date] = None,
) -> dict:
    """Derive week + trimester from LMP/due date.

    Returns ``{week, trimester, basis}``. Raises ProfileDataError for
    missing/contradictory data or a resulting week outside 1..42.
    """
    reference, basis = _reference_date(lmp_date, due_date)
    effective_today = today if today is not None else date.today()
    days_elapsed = (effective_today - reference).days
    week = days_elapsed // 7 + 1
    if not (MIN_WEEK <= week <= MAX_WEEK):
        raise ProfileDataError(
            f"The derived gestational age ({week} weeks) is outside the "
            "supported range of 1-42 weeks.",
            "GESTATION_OUT_OF_RANGE",
        )
    return {"week": week, "trimester": trimester_for_week(week), "basis": basis}


# ── Profile completion ───────────────────────────────────────────


def profile_completion_status(
    *,
    height_cm: Optional[float],
    pre_pregnancy_weight_kg: Optional[float],
    lmp_date: Optional[date],
    due_date: Optional[date],
    region: Optional[str],
    dietary_preference: Optional[str],
    allergies: Optional[list[str]],
) -> dict:
    """Summarize profile completeness. Never raises for missing data —
    it reports; validation errors come from the individual setters."""
    missing: list[str] = []
    if height_cm is None:
        missing.append("height_cm")
    if pre_pregnancy_weight_kg is None:
        missing.append("pre_pregnancy_weight_kg")
    if lmp_date is None and due_date is None:
        missing.append("gestation_date")
    if not region:
        missing.append("region")
    if not dietary_preference:
        missing.append("dietary_preference")
    if allergies is None:  # [] is valid — user declares "no known allergies"
        missing.append("allergies")

    # Optional: pre-pregnancy BMI when both inputs exist (server-computed).
    bmi: Optional[float] = None
    bmi_error: Optional[str] = None
    if height_cm is not None and pre_pregnancy_weight_kg is not None:
        try:
            bmi = calculate_pre_pregnancy_bmi(pre_pregnancy_weight_kg, height_cm)
        except ProfileDataError as e:
            bmi_error = e.code

    return {
        "complete": not missing,
        "missing_fields": missing,
        "pre_pregnancy_bmi": bmi,
        "bmi_error_code": bmi_error,
        "gestational_week": None,
        "trimester": None,
    }


def assert_no_client_bmi(payload: dict) -> None:
    """Reject any client attempt to supply BMI values.

    Defense in depth: Pydantic schemas already forbid the field; this
    guard is used anywhere raw dicts are accepted (imports, admin tools).
    """
    for key in ("bmi", "pre_pregnancy_bmi"):
        if key in payload and payload[key] is not None:
            raise ProfileDataError(
                "BMI is calculated by AlmaDiet from your height and "
                "pre-pregnancy weight and cannot be entered manually.",
                "BMI_NOT_ACCEPTED",
            )
