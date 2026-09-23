"""AlmaDiet — Versioned nutrition policy (BMI context, never a target).

A *policy* is an explicit, reviewable, versioned mapping from BMI bands to
non-prescriptive context adjustments. Policies live in code, carry an
id + version, and are gated behind an approval record (see
``NutritionPolicyApproval`` model). Nothing here computes treatment,
supplement doses, or exact medical calorie requirements — the numbers are
reference values shown for transparency and always defer to the clinician.

If no approved policy exists for a version, the caller MUST treat BMI as
display-only (informative profile field) and must not generate
"BMI-personalized" targets. This module makes that failure mode explicit
rather than silent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

POLICY_VERSION = "1.0.0"

# Non-prescriptive reference adjustments. These are broad, documented
# ranges commonly used for *general education* — they are not computed
# energy requirements and must never be presented as prescriptions.
# Values: delta to the trimester reference (calories) plus emphasis tags.
@dataclass(frozen=True)
class BMIBand:
    code: str
    label: str          # user-facing, non-judgmental
    min_bmi: float      # inclusive
    max_bmi: float      # exclusive (except last band)
    calorie_delta: int  # delta to trimester reference calories
    emphasis: tuple[str, ...] = field(default_factory=tuple)


POLICY_1_0_0 = {
    "policy_id": "alma-nutrition-context",
    "version": POLICY_VERSION,
    "description": (
        "General pregnancy nutrition context by pre-pregnancy BMI band. "
        "Reference values only — not prescriptions. Each user must discuss "
        "targets with their clinician or midwife."
    ),
    "bands": [
        BMIBand("below_18_5", "BMI below 18.5", 0.0, 18.5, 200, ("energy_dense_foods",)),
        BMIBand("18_5_24_9", "BMI 18.5-24.9", 18.5, 25.0, 0, ()),
        BMIBand("25_0_29_9", "BMI 25.0-29.9", 25.0, 30.0, -150, ("balanced_portions",)),
        BMIBand("30_plus", "BMI 30 and above", 30.0, 100.0, -250, ("nutrient_quality",)),
    ],
}


class PolicyNotApprovedError(RuntimeError):
    """No approval record exists for the requested policy version."""


def band_for_bmi(bmi: float) -> BMIBand:
    for band in POLICY_1_0_0["bands"]:
        if band.min_bmi <= bmi < band.max_bmi:
            return band
    raise ValueError(f"BMI {bmi} outside supported policy bands")


def apply_policy(
    bmi: Optional[float],
    trimester_reference: dict,
    approved_versions: set[str],
) -> dict:
    """Apply an approved policy to a trimester reference.

    Returns a dict with:
      * ``applied``: False when BMI is None or the policy is unapproved —
        the caller must then treat the reference values as unmodified and
        display-only.
      * ``context_note``: transparent user-facing explanation.
      * ``reference``: adjusted reference dict (calories only; macros are
        NEVER derived from BMI by this policy).

    Raises nothing: unapproved policy is a normal, reportable state.
    """
    if bmi is None:
        return {
            "applied": False,
            "policy_version": POLICY_VERSION,
            "reason": "no_bmi",
            "context_note": (
                "Pre-pregnancy BMI is not part of your profile yet, so the "
                "reference values below are general second/third-trimester "
                "education values, not personalized."
            ),
            "reference": dict(trimester_reference),
        }

    if POLICY_VERSION not in approved_versions:
        # Fail closed: BMI stays display-only without approval.
        return {
            "applied": False,
            "policy_version": POLICY_VERSION,
            "reason": "policy_not_approved",
            "context_note": (
                "Reference values are general education values. "
                "Personalized context from pre-pregnancy BMI requires a "
                "clinician-reviewed policy that is not yet approved."
            ),
            "reference": dict(trimester_reference),
        }

    band = band_for_bmi(bmi)
    adjusted = dict(trimester_reference)
    adjusted["calories"] = max(1200, trimester_reference["calories"] + band.calorie_delta)
    return {
        "applied": True,
        "policy_version": POLICY_VERSION,
        "reason": "approved_policy",
        "band": band.code,
        "band_label": band.label,
        "emphasis": list(band.emphasis),
        "context_note": (
            f"Reference values use general education guidance for {band.label} "
            "in pregnancy. They are not personalized medical targets — your "
            "clinician's advice always takes precedence."
        ),
        "reference": adjusted,
    }
