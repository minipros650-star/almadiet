# 🌸 AlmaDiet — Pregnancy Nutrition Support

AlmaDiet is **evidence-informed pregnancy nutrition support**: it helps users
organize food information, meal ideas, preferences, allergies, and clinician
discussions across five languages (English, മലയാളം, தமிழ், ಕನ್ನಡ, తెలుగు).

> **What AlmaDiet is not.** AlmaDiet is **not a medical device** and makes no
> regulatory claims. It does **not** diagnose conditions, provide emergency
> treatment, triage symptoms, or replace a doctor, midwife, or dietitian.
> Recommendations are nutrition-support information only. For personalized
> medical advice — and for any urgent symptom — consult a qualified
> healthcare professional or local emergency service.

Stack: **Flutter** (Riverpod, go_router, secure token storage) ·
**FastAPI** `/api/v1` (Argon2id auth, refresh-token rotation, error envelope)
· **PostgreSQL** with **Alembic** migrations · deterministic safety-first
recommendation pipeline with allergen hard-exclusion, content governance, and
audit logging.

Full documentation lives in [`docs/`](docs/) — start with
[PRD](docs/PRD.md), [CLINICAL_SAFETY](docs/CLINICAL_SAFETY.md), and
[ARCHITECTURE](docs/ARCHITECTURE.md).

## Features (as actually implemented)

| Area | What exists |
|---|---|
| Accounts | Register/login, Argon2id hashing, access (15 min) + refresh (30 d) rotation, logout-all, lockout after 5 failed logins |
| Consent | Versioned consent required before saving health data (server-enforced) |
| Health context | Trimester/week **consistency validation** (backend + Flutter), allergies as structured categories, dietary preference; BP/Hb/glucose stored as entered — never invented |
| Meals | 120 South Indian meals with structured nutrition, ingredient-level **allergen metadata**, provenance (source, evidence version, review state) |
| Recommendations | Deterministic pipeline: validate → allergy filter → dietary filter → condition-safety filter → food-safety filter → select → **final safety validation** → explanation + sources. Genuine **7-day plan** (7 days × 4 slots) |
| Meal swap | Re-runs the full safety pipeline; same slot/type; explanation included |
| Urgent help | Information-only safety screen; warning signs, regional emergency guidance (India: 112/108/104), clinician-share; **no treatment and no "resolved" state** |
| Privacy | Data export (JSON), account deletion, health-record deletion, audit logging (no health values in logs) |
| Governance | Meal content lifecycle DRAFT→REVIEW_REQUIRED→REVIEWED→PUBLISHED→RETIRED; only published content in production recommendations |
| Images | Illustrative meal images (third-party service), clearly labelled; recommendations work fully without them |

Removed from the previous version (see
[ADR 0001](docs/ADR/0001-product-boundary.md)): the Random-Forest-driven
"95% accurate" nutrition engine (trained on synthetic data), the
`clinically_approved` flag, free-text WHO-alignment claims, and the
emergency "treatment diet + mark resolved" feature.

## Repository layout

```
├── backend/
│   ├── main.py                 # FastAPI app (v1 API, error envelope, CORS allowlist)
│   ├── alembic/                # migrations (0001 initial … 0003 safety schema)
│   ├── app/
│   │   ├── auth/               # Argon2id, JWT, refresh rotation
│   │   ├── core/               # config (env-validated), errors, logging
│   │   ├── domain/             # PURE safety logic: gestational, allergens,
│   │   │                       #   conditions, food_safety, content_state
│   │   ├── models/             # SQLAlchemy 2.0 (CHECKs, FKs, indexes)
│   │   ├── routers/            # auth, consent, health, meals, diet, urgent, privacy
│   │   ├── schemas/            # Pydantic v2
│   │   ├── services/           # user, health, meal, diet, privacy, audit
│   ├── data/meals_dataset.json # 120 meals (seed → REVIEW_REQUIRED state)
│   └── tests/                  # pytest: unit + API + security suites
├── frontend/
│   └── lib/
│       ├── core/               # theme, router, secure storage, localization (5 langs)
│       ├── features/           # onboarding, consent, auth, home, health input,
│       │                       #   diet plan, meal detail, urgent help, profile
│       └── providers/          # Riverpod state
├── docs/                       # PRD, CLINICAL_SAFETY, THREAT_MODEL, …
└── .github/workflows/ci.yml    # format, lint, tests, migrations, security, build
```

## Quick start

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env          # then EDIT .env — see table below

# Create schema (choose ONE):
alembic upgrade head                       # preferred — real migrations
python -c "import main"                    # dev convenience: create_all + seeding run on dev startup

# Run
uvicorn main:app --reload                  # http://localhost:8000/docs
```

Dev startup seeds the meal catalog automatically (empty database only);
imported meals arrive as `REVIEW_REQUIRED`.

Or with Docker (development only — the compose file uses placeholder
credentials and must not be used as-is in production):

```bash
docker compose up -d        # from repo root; Postgres 5432 + API 8000
```

### Frontend

```bash
cd frontend
flutter pub get
flutter run -d windows      # or -d <android-device>
```

The Flutter app reads the API base URL from `--dart-define` (defaults to the
Android emulator loopback `http://10.0.2.2:8000`), e.g.:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

### Environment variables (backend/.env)

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://user:pass@host:5432/almadiet` |
| `JWT_SECRET_KEY` | ✅ in production | Startup **fails** if missing or the known default when `ENVIRONMENT=production` |
| `ENVIRONMENT` | – | `development` (default) / `production` — production enables strict validation |
| `DEBUG` | – | `false` in production |
| `ALLOWED_ORIGINS` | ✅ in production | Comma-separated list; `*` is **rejected** in production |
| `REFRESH_TOKEN_EXPIRE_DAYS` | – | default 30 |
| `CONTENT_INCLUDE_STATUSES` | – | dev override for which content states recommendations may use |

Never commit `.env`. The CI runs a secret scan (`gitleaks`-style grep) and
history was audited for previously committed credentials.

## Tests

```bash
# Backend (uses SQLite in-memory; CI also runs against Postgres)
cd backend && python -m pytest tests -v

# Frontend
cd frontend && flutter test
cd frontend && flutter analyze
```

The suites include the fifteen critical safety tests (allergen leakage,
trimester contradictions, IDOR, expired tokens, route conflicts, 7-day plan
shape, urgent-help wording, localization completeness, production config
rejections, …) — mapped in [docs/TEST_STRATEGY.md](docs/TEST_STRATEGY.md).

## Known limitations

- Flutter SDK required for frontend builds/tests (installed locally at
  `%USERPROFILE%\flutter`; add `flutter/bin` to PATH or use `flutter.bat`).
- Seed meal content arrives in `REVIEW_REQUIRED`; a reviewer must publish it
  before production recommendations serve it (dev mode can include
  `REVIEWED`).
- Illustrative meal images come from a third-party service and are not
  guaranteed to depict the exact meal; they are labelled illustrative and are
  never a clinical trust signal.
- Localizations were reviewed by contributors, not certified translators.
- No WAF/DDoS layer; rate limiting is application-level only.
- The previous offline ML trainer was removed entirely (ADR 0001); the
  recommendation pipeline is deterministic and explainable. A properly
  validated model can be reintroduced later behind a service interface.

## License

For educational and research use as part of a pregnancy nutrition support
initiative.
