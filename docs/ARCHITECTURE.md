# Architecture

**Status:** Implemented

## 1. System overview

```
Flutter (Android / Windows)
│
├── Presentation        features/*/presentation  (screens, widgets)
├── State               providers/  (Riverpod Notifiers)
├── Domain              core/utils/gestational_validator.dart (pure validation)
├── Data                core/utils/api_client.dart (Dio + auth interceptor)
├── Secure Storage      core/data/secure_token_storage.dart (flutter_secure_storage)
└── Localization        core/localization (en, ml, ta, kn, te — completeness-tested)
        │
        ▼  HTTPS/JSON
Versioned FastAPI (/api/v1)
│
├── auth/            JWT issue/verify, refresh rotation, lockout, Argon2id
├── routers/         auth, health, meals, diet (plan+swap), urgent, privacy, consent
├── services/        user, health, meal, diet (recommendation), privacy, audit
├── domain/          PURE safety & validation logic (no I/O):
│                      gestational.py    trimester/week consistency
│                      allergens.py      taxonomy + matching engine
│                      conditions.py     condition-based food restrictions
│                      food_safety.py    pregnancy food-safety filters
│                      content_state.py  governance state machine
│                      health_signals.py informational value thresholds
├── core/            config (env-validated), errors (error envelope), logging
                      (the former ML module was removed entirely — ADR/0001)
        │
        ▼  SQLAlchemy 2.0 async + Alembic migrations
PostgreSQL
│
├── users, refresh_tokens, consents, audit_logs
├── health_records (FK→users, CHECK constraints, indexes)
├── meals (+ provenance columns), meal_allergens, ingredients (JSONB), content_versions
├── diet_plans (7-day JSONB days, FK→users/health_records)
└── urgent_help_notes (observations to share with clinician; no "resolution")
```

## 2. Request pipeline (recommendations)

```
USER INPUT
  → Pydantic input validation (types, ranges)
  → Gestational consistency validation      (domain/gestational.py)
  → Consent check                            (409 CONSENT_REQUIRED)
  → Allergen filter (HARD, ingredient-level) (domain/allergens.py)
  → Dietary preference filter                (veg/eggetarian/nonveg)
  → Medical-condition safety filter          (domain/conditions.py)
  → Food-safety filter                       (domain/food_safety.py)
  → Availability / content-status filter     (PUBLISHED only in prod)
  → Nutritional selection (deterministic scoring, seeded RNG)
  → 7-day plan assembly (no duplicate meals per slot pool)
  → FINAL safety validation (re-checks every selected meal)
  → Explanation + sources attached to each meal
  → Response
```

Allergy filtering happens **before** selection by construction: the candidate
query only yields meals that pass `SafetyValidator.filter_candidates()`, and a
final pass re-validates each chosen meal (defence in depth, unit-tested).

## 3. Key invariants

- Every user-data query includes `user_id = current_user.id`.
- Safety rules are pure functions in `app/domain` — testable without DB.
- No ML anywhere in the decision path; the former trainer/predictor module was
  removed from the repository (ADR/0001).
- Content governance state is checked at recommendation time, not just import.
- All errors use one envelope (`app/core/errors.py`):
  `{"error": {"code", "message", "details"}}`.

## 4. Data stores

- **PostgreSQL** — all user data; Alembic owns schema (create_all is dev/test
  convenience only, disabled in production startup).
- **Client**: secure storage for tokens; SharedPreferences only for
  non-sensitive UI state (locale, onboarding flag, profile image path).

## 5. Module ownership map

| Concern | Owner file(s) |
|---|---|
| Gestational validation | `backend/app/domain/gestational.py` (+ mirrored pure Dart `frontend/lib/core/utils/gestational_validator.dart`) |
| Allergen matching | `backend/app/domain/allergens.py` |
| Condition restrictions | `backend/app/domain/conditions.py` |
| Content lifecycle | `backend/app/domain/content_state.py`, `backend/app/services/meal_service.py` |
| Auth | `backend/app/auth/*` |
| Recommendation | `backend/app/services/diet_service.py` |
| Privacy endpoints | `backend/app/services/privacy_service.py` |
| Consent gate | `backend/app/routers/health_router.py` + `consent_router.py` |
| Token storage | `frontend/lib/core/utils/api_client.dart` (flutter_secure_storage) |

## 6. What was intentionally removed
- Random-forest-driven nutrient prioritization in the live path (synthetic
  data; see ADR/0001). The `app/ml/` module was deleted from the repository.
- Emergency diet treatment engine + "resolve emergency" flow.
- `clinically_approved` boolean.
- WHO-alignment free-text claims from seed data.
