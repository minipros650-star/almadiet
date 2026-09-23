# Test Strategy

**Status:** Implemented suites listed below · CI gate: all must pass

## Layers

### Backend (pytest, `backend/tests/`)
Run: `python -m pytest backend/tests -v` (SQLite aiosqlite in-memory; the
same code paths run against PostgreSQL in CI via docker service).

| Suite | File | Covers |
|---|---|---|
| Unit — domain | `test_gestational.py` | trimester/week boundaries, contradictions rejected (CRITICAL TEST 3) |
| Unit — allergens | `test_allergens.py` | taxonomy, synonyms (peanut/groundnut/peanut butter), normalized matching, cross-contamination metadata (CRITICAL TESTS 1, 2 at unit level) |
| Unit — conditions/food safety | `test_conditions_food_safety.py` | condition restrictions, pregnancy food-safety exclusions |
| Unit — content state | `test_content_state.py` | lifecycle transitions, invalid transitions |
| Unit — auth | `test_auth_service.py` | hashing, lockout, token expiry/invalid (CRITICAL TEST 6) |
| Integration — API | `test_api_auth.py` | register/login/refresh rotation/logout-all, generic errors |
| Integration — authorization | `test_api_authorization.py` | unauthenticated blocked (TEST 4), user A ≠ user B (TEST 5), IDOR on records/plans |
| Integration — routes | `test_api_routes.py` | image route vs UUID route ordering (TESTS 8, 9), 404 vs 422, error envelope shape |
| Integration — recommendations | `test_api_diet.py` | 7-day plan structure (TEST 10), final safety validation (TEST 11), swap preserves filters |
| Integration — privacy | `test_api_privacy.py` | export, deletion, consent gate (409), consent flow |
| Integration — urgent | `test_api_urgent.py` | no treatment/resolution semantics (TEST 12) |
| Config | `test_config_security.py` | wildcard CORS rejected in prod (TEST 14), missing secrets fail startup (TEST 15) |

### Frontend (flutter test, `frontend/test/`)
| Suite | Covers |
|---|---|
| `localization_test.dart` | key completeness across 5 locales (TEST 13) |
| `core/domain/gestional_test` → `gestational_test.dart` | Dart-side week/trimester validation parity |
| `profile_update_test.dart` | profile save calls PATCH, updates state on 200, shows success only after confirmation (TEST 7) |
| `widget/meal_card_test.dart` | meal card semantics, overflow at 320px |
| `auth_provider_test.dart` | token stored via secure storage mock, logout clears |
| `urgent_help_test.dart` | wording gate: no "resolved"/treatment claims |

### Security tests
Encoded in the backend suites above (auth abuse T5, IDOR T6, invalid/expired
JWT T8, CORS T9, secret validation T2, route shadowing T10). Manual checklist
in RELEASE_CHECKLIST.md covers what automation cannot (TLS, headers at proxy).

### Migration tests
`test_migrations.py` runs Alembic `upgrade head` against a scratch SQLite/
(migration-guarded) Postgres URL and asserts `alembic_version` at head and a
round-trip downgrade/upgrade of 0003.

## Rules
1. A failing test is never deleted to make CI green; fix code or fix test —
   both with justification in the PR.
2. Tests must not weaken safety assertions (allergen tests are immutable
   without owner sign-off).
3. New safety rules require a new test in the same PR (docs updated too).
