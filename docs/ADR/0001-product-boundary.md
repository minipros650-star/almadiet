# ADR 0001 — Product boundary: no clinical claims; ML removed from the decision path

**Status:** Accepted · **Date:** 2026-09-22

## Context

The original AlmaDiet implementation:

1. Trained a Random Forest on **synthetic data generated from hard-coded
   rules** (`app/ml/trainer.py`), then marketed it as "R² = 95.14%" accuracy —
   which measures fit to the synthetic generator, not clinical validity.
2. Hard-coded `clinically_approved = true` on every seeded meal.
3. Shipped free-text "WHO alignment" claims in meal content without any
   documented evidence source or governance process.
4. Offered an "Emergency" feature that generated condition-specific
   treatment-style diet plans and allowed marking emergencies "resolved" —
   implying the app could assess and resolve medical emergencies.
5. Presented meal plans as "ML-powered personalization" without explaining
   that the underlying "knowledge" was a deterministic rule generator.

None of these claims were supportable. Together they created a real safety
risk: users could reasonably believe they were receiving clinically approved,
WHO-endorsed, doctor-like guidance during pregnancy.

## Decision

1. **Product boundary (binding):** AlmaDiet is evidence-informed pregnancy
   nutrition support — it organizes food information and meal ideas and helps
   users talk to clinicians. It never diagnoses, treats, triages, or claims
   clinical approval. Enforced repo-wide by a claims test and documented in
   `docs/CLINICAL_SAFETY.md`.
2. **ML removed from the nutrition decision path.** Nutrient prioritization is
   now a transparent, deterministic, documented mapping (trimester → focus
   nutrients with rationale strings shown to users as "why suggested").
   The Random Forest trainer was subsequently **removed entirely** from the
   repository (no dead code in the decision path). A validated model can be
   offline experimentation, clearly labelled that synthetic evaluation
   establishes nothing about clinical validity.
3. **If ML returns**, it must be reintroduced behind the
   reintroduced later behind a service interface with: model version, feature-schema
   version, stored metadata, input validation, output-class validation,
   deterministic fallback, logged version, and — above all — safety rules
   that always take precedence over model output.
4. **`clinically_approved` removed** from the schema; replaced by the
   content-governance lifecycle (`docs/CONTENT_GOVERNANCE.md`). Seed content
   imports as `REVIEW_REQUIRED`, never implicitly `PUBLISHED`.
5. **"Emergency" replaced by "Urgent Help"**: an information-only safety
   pathway with no treatment content and no resolution state
   (see CLINICAL_SAFETY §5).

## Consequences

- Positive: honest positioning; every claim in the product is traceable to
  implemented code or documented content; safety filtering is testable and
  deterministic; audit trail for content.
- Negative: we lose the (illusory) "AI personalization" marketing angle;
  regeneration of the model no longer affects the product.
- Neutral: meal selection variety is achieved with a seeded deterministic
  RNG instead of model-driven scores; "why suggested" strings are generated
  from explicit, explainable factors.

## Compliance checks added

- `frontend/test/*claims*_test` + backend static check: banned claim phrases
  ("clinically approved", "medically validated", "WHO approved", "95%",
  "treatment", "cure") must not appear in user-facing strings or seed data.
- Automated allergen, gestational-validation, urgent-help wording tests
  (see docs/TEST_STRATEGY.md).
