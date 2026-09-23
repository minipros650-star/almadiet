# Clinical Safety Framework

**Status:** Implemented · **Owner:** Product + Clinical reviewer

## 1. What AlmaDiet is and is not

| AlmaDiet IS | AlmaDiet IS NOT |
|---|---|
| A tool to organize food and meal ideas | A medical device |
| An educational reference for common pregnancy nutrition topics | A diagnostic tool |
| A clinician-conversation aid (exportable summary) | A treatment planner |
| A safety filter that excludes known allergens | A replacement for clinician advice |

No content in the app or repository claims clinical approval, WHO endorsement,
or medically validated personalization. The previous "emergency diet plan"
feature (condition-specific treatment diets with a "mark resolved" action) has
been **removed** and replaced by the information-only "Urgent Help" pathway.

## 2. Safety rules (must always hold)

SR-1 **Allergen hard exclusion.** A meal containing any allergen mapped to a
user allergy is never selectable. Matching is ingredient-level, normalized,
with synonym support (`peanut/groundnut/peanut butter/peanut flour` are one
category). Cross-contamination risk meals may appear only with an explicit
warning and only for allergens not in the user's allergy list.

SR-2 **Safety precedes ML/selection.** The pipeline applies all safety filters
before meal selection; a final validation re-checks every selected meal.
No model output can bypass safety rules (no ML is currently used for
nutrition decisions at all — ADR/0001).

SR-3 **Gestational consistency.** `trimester` must match `gestational_week`
per the single authoritative table in `backend/app/domain/gestational.py`.
Contradictions are rejected with HTTP 422 on the backend and validated in
the Flutter form before submission.

SR-4 **No treatment content.** Meal text may describe nutrition composition
and preparation safety. It must not instruct on treating a condition,
adjusting medication, or "resolving" symptoms. Condition-related guidance in
the app is limited to: (a) restricting clearly unsafe foods for a declared
condition (see §4), (b) suggesting the user discuss the topic with their
clinician.

SR-5 **Urgent signs defer to professionals.** The urgent-help screen never
assesses severity, never declares resolution, and always points to local
emergency guidance. It is reachable from the dashboard but is deliberately
not a normal tab in the meal-planning flow.

SR-6 **Published content only.** In production, only meal content in the
`PUBLISHED` governance state with a recorded `source` participates in
recommendations.

SR-7 **No fabricated vitals.** If a user does not provide hemoglobin, blood
pressure, or glucose values, the app must not invent defaults (the old
frontend did). Missing values stay missing.

## 3. Condition-related handling

The system recognizes user-declared conditions from a fixed enum
(`gestational_diabetes`, `hypertension`, `preeclampsia_history`, `anemia`,
`severe_nausea_vomiting`, `medication_constrained`, `other`) and applies
**documented, conservative, non-treatment responses**:

| Declared context | Restriction applied | Wording used in-app |
|---|---|---|
| Gestational diabetes | Prefer lower-sugar meals; exclude dessert-type items | "Meal ideas chosen with lower-sugar options. Discuss blood-sugar targets with your clinician." |
| Hypertension / preeclampsia history | Prefer lower-sodium meals | "Lower-sodium meal ideas. Sodium management in pregnancy should be guided by your clinician." |
| Anemia | Prefer iron-rich meals, vitamin-C pairing notes | "Iron-rich meal ideas. Iron supplementation is a clinician decision." |
| Severe nausea/vomiting | Prefer lighter, less spicy meals; small-portion notes | "Gentler meal ideas. Persistent vomiting needs clinician review." |
| Medication-constrained | Restrict items flagged to interact with common pregnancy medications (e.g., high-vitamin-K foods are flagged in safety notes) | "Some foods may interact with medicines. Your clinician or pharmacist can advise." |

Every condition rule lives in `backend/app/domain/conditions.py`, is unit-tested,
and produces both a **restriction** and an **explanation string**. No rule ever
prescribes doses, supplements, or a treatment course. Any new rule requires a
PR that updates this document.

## 4. Health-value "discussion suggestions"

Values the user enters (BP, hemoglobin, glucose) may trigger a neutral,
non-diagnostic suggestion, e.g.:

> "Your recorded hemoglobin is below the commonly used reference range for
> pregnancy. This app cannot interpret lab values — please share this with
> your doctor or midwife."

Thresholds used for triggering these suggestions are documented in
`backend/app/domain/health_signals.py` and are **informational only**: they
never produce a diagnosis, never use the word "condition" for the user, and
never appear in the meal pipeline as a medical status.

## 5. Emergency/urgent content rules

- The words "treatment", "diagnosis", "cure", and "resolved" must not appear
  in urgent-help user-facing strings (enforced by test).
- Regional emergency guidance (India-first: 112/108/104, with a generic
  fallback for other regions) is static content, clearly labelled as guidance,
  not a dispatch service.

## 6. Review & change control

- Any change to SR rules, condition tables, or emergency wording requires
  review by the product owner and, where feasible, a qualified dietitian.
- Automated gates: allergy tests, trimester tests, urgent-help wording test,
  no-clinical-claims lint (see TEST_STRATEGY.md §5).
