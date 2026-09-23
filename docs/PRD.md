# AlmaDiet — Product Requirements Document

**Status:** Implemented (v2.0) · **Last updated:** 2026-09-22

## 1. Product definition

AlmaDiet is a **pregnancy nutrition support application**. It helps users organize
food information, meal ideas, dietary preferences, allergies, and clinician
discussions.

**Product boundary (binding):** AlmaDiet is not a medical device. It does not
diagnose, treat, triage, or replace a clinician. It does not provide emergency
care. It does not present algorithmic output as medically validated advice.
Where a situation may require medical attention, the app directs the user to a
qualified healthcare professional or emergency service.

Positioning statement:

> Evidence-informed pregnancy nutrition support that helps users organize food
> information, meal ideas, preferences, and clinician discussions.

## 2. Users

- **Pregnant person (primary):** wants trustworthy, regionally familiar meal
  ideas, organized nutrition information, and a way to share context with
  their clinician.
- **Content reviewer (internal):** reviews and publishes meal content
  (governance workflow, see CONTENT_GOVERNANCE.md).

## 3. Goals and non-goals

| Goals | Non-goals |
|---|---|
| Safe, allergy-aware meal idea browsing | Diagnosis of any condition |
| Genuine 7-day meal-plan structure with per-day ideas | Nutritional prescriptions or clinically validated personalization |
| Transparent "why suggested" explanations | "AI doctor" behaviour |
| Urgent-help safety pathway that defers to professionals | Emergency treatment, triage, or resolution tracking |
| Clinician summary export | Communication with clinics on the user's behalf |
| Consent, data export, account deletion | Analytics on health data |

## 4. Feature scope (as implemented)

### 4.1 Accounts and profile
- Email/password registration with strong password policy; Argon2id hashing.
- Login with access + refresh tokens (rotation, revocation, logout-all).
- Login attempt lockout and rate limiting.
- Profile view/update via authenticated `PATCH /api/v1/auth/me`.
- Consent record required before health data can be saved (`/api/v1/consent`).

### 4.2 Health context (not a diagnosis)
- Trimester + gestational week with **centralized consistency validation**
  (backend rejects contradictions such as trimester 1 with week 30).
- Weight, BMI, blood pressure, hemoglobin, fasting glucose are stored as
  **user-entered values**. The app does not interpret them as diagnoses; it
  surfaces clinician-discussion suggestions with appropriate wording when a
  value is outside commonly used reference ranges (see CLINICAL_SAFETY.md).
- Allergies and dietary preference are first-class inputs used by the
  recommendation pipeline.

### 4.3 Meal catalog
- 120 reviewed South Indian meals with structured nutrition, ingredients,
  allergen categories derived from ingredients, cuisine, serving size,
  preparation time, and food-safety notes.
- Content governance states (`DRAFT/REVIEW_REQUIRED/REVIEWED/PUBLISHED/RETIRED`)
  with source and evidence version. Only `PUBLISHED` (or explicitly permitted)
  content enters recommendations in production.
- Meal detail shows allergens, safety notes, source, content version, and
  substitutions.

### 4.4 Recommendations
- Deterministic, explainable pipeline: validation → safety → allergy filter →
  dietary filter → condition-safety filter → food-safety filter → nutritional
  selection → explanation. Allergy filtering happens **before** selection.
- Genuine 7-day plan (7 days × breakfast/lunch/snack/dinner) with
  no unsafe item passing through; per-day ideas, not prescriptions.
- Meal swap: same safety filters, same meal type, explanation included.
- ML is **not** used to make nutrition-priority decisions. A modular,
  versioned predictor interface exists for future validated models; safety
  rules always take precedence (see ADR/0001 and ARCHITECTURE.md).

### 4.5 Urgent help
- Information-only safety screen: explains the app cannot assess emergencies,
  lists warning signs that warrant contacting a clinician or emergency
  service, provides regional emergency number guidance, and lets the user
  note/observe symptoms to share with a clinician. No "resolve" action, no
  treatment instructions, no diagnosis.

### 4.6 Dashboard
- Today (meal ideas + completed meals + observed nutrition), next check-in,
  meal ideas, my preferences (allergies/diet), share-with-clinician summary,
  urgent help entry point.

### 4.7 Privacy
- Consent versioning, data export (JSON), account deletion, logout-all,
  audit logging of security- and safety-relevant events.

## 5. Localisation
Five languages (en, ml, ta, kn, te) with completeness enforced by tests.
Long translated strings are layout-tested.

## 6. Success measures (product, not clinical)
- Zero allergen leakage in automated tests.
- Plan generation success with safe fallback meals when the catalog is thin.
- Localization key completeness at 100% in CI.
- Users can export data and delete their accounts unaided.

## 7. Out of scope
Medical-device classification, clinician-side portal, delivery integration,
AI image generation as a trust signal (illustrative images only, clearly
labelled; recommendations work without images).
