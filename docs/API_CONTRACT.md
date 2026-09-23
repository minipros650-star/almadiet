# API Contract (v1)

Base URL: `/api/v1` · JSON only · Bearer auth unless marked **public**.

## Error envelope (all non-2xx responses)

```json
{ "error": { "code": "INVALID_INPUT", "message": "The submitted health information is invalid.", "details": {} } }
```

Codes: `INVALID_INPUT` (422) · `UNAUTHORIZED` (401) · `FORBIDDEN` (403) ·
`NOT_FOUND` (404) · `CONFLICT` (409) · `LOCKED` (423, login lockout) ·
`RATE_LIMITED` (429) · `CONSENT_REQUIRED` (409 with this code) ·
`INTERNAL` (500, no stack trace). Pydantic validation errors are translated
to this envelope by the app-level exception handler; `details` carries
field-level messages.

## Conventions
- Pagination: `?limit` (1–200, default 50) + `?offset` (≥0) on list endpoints.
- Idempotency: GET/PUT/DELETE are idempotent; POST plan-generation is not
  (creates a new plan), all other POSTs are safe.
- All ids are UUIDs. Dates ISO-8601. Timestamps UTC with offset.
- Route order: static segments before parameterized; `/{meal_id}` accepts
  UUIDs only (422 otherwise) — see ROUTES tests.

## Authentication

| Method | Path | Auth | Request | Responses |
|---|---|---|---|---|
| POST | /auth/register | public | `{email, password(≥8), name, region?, language?, age?, height_cm?, pre_pregnancy_weight_kg?, lmp_date?, accept_consent?: bool}` | 201 `{access_token, refresh_token, token_type:"bearer", user}` · 409 email exists · 422 |
| POST | /auth/login | public | `{email, password}` | 200 TokenPair · 401 `UNAUTHORIZED` (generic message) · 423 LOCKED after 5 fails for 15 min · 429 RATE_LIMITED >5/min/IP |
| POST | /auth/refresh | public (refresh token) | `{refresh_token}` | 200 new TokenPair (old refresh revoked — rotation) · 401 on invalid/expired/**reused** (family revoked) |
| POST | /auth/logout | bearer | `{refresh_token}` | 204 · revokes token |
| POST | /auth/logout-all | bearer | – | 204 · revokes all sessions |
| GET | /auth/me | bearer | – | 200 User |
| PATCH | /auth/me | bearer | partial UserUpdate (no email/password) | 200 User · 422. Frontend profile save uses this route; success is shown only after 200. |

## Consent

| Method | Path | Auth | Request | Responses |
|---|---|---|---|---|
| POST | /consent | bearer | `{consent_version}` | 201 Consent |
| GET | /consent/current | bearer | – | 200 `{accepted, consent_version, accepted_at}` |

## Health records

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | /health/record | bearer | Body HealthRecordCreate. **422** on trimester/week contradiction (e.g. T1+W30). **409 CONSENT_REQUIRED** without current-version consent. Allergies are normalized to category codes server-side. |
| GET | /health/records | bearer | List, newest first, paginated |
| GET | /health/records/{id} | bearer | 404 unless owned by caller |
| DELETE | /health/records/{id} | bearer | 204 · audited |
| GET | /health/records/{id}/discussion-points | bearer | **Informational** list of clinician-discussion suggestions (see CLINICAL_SAFETY §4). No diagnosis, no corrections. |

## Meals

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | /meals | public | Filters: region, trimester(1–3), meal_type, is_vegetarian, exclude_allergen (repeatable category codes), limit, offset. Only `PUBLISHED` rows in prod (`CONTENT_INCLUDE_STATUSES` overrides in dev). |
| GET | /meals/images/all | bearer | Lists cached image metadata. **Registered before** `/{meal_id}`; not shadowed. |
| GET | /meals/{meal_id} | public | 404 unknown · 422 non-UUID. Includes allergens, substitutions, source, evidence_version, content_status, safety notes. |
| GET | /meals/{meal_id}/image | public | `{meal_id, image_url, illustrative: true}` — labelled illustrative; may be null. |

## Diet plans

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | /diet/generate | bearer | `{health_record_id}` → 201 PlanResponse. Plan contains `days` (exactly 7), each with breakfast/lunch/snack/dinner arrays; every meal passed final safety validation; `exclusions_applied` records filtered items count by reason; alerts include explanation + source. |
| GET | /diet/plans | bearer | List (paginated) |
| GET | /diet/plans/{id} | bearer | 404 unless owned |
| POST | /diet/plans/{id}/swap | bearer | `{day_index, slot, current_meal_id}` → 200 with the **same day/slot** replaced by a meal passing all safety filters, same meal-type class, with `why_suggested` including the swap rationale. |
| POST | /diet/feedback | bearer | `{plan_id, feedback, rating 1–5}` |

## Urgent help

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | /urgent/info | bearer | Static safety information: disclaimer, warning signs, regional emergency guidance, clinician-contact checklist. **No diagnosis, no treatment, no resolution state.** |
| POST | /urgent/notes | bearer | `{observed_symptoms}` → 201 note to share with a clinician. Never marks anything resolved. |
| GET | /urgent/notes | bearer | User's own notes |

## Privacy

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | /privacy/export | bearer | 200 JSON bundle (profile, records, plans, consents) · audited |
| DELETE | /privacy/account | bearer | 204 · cascades all user data · audited (event only) |

## Root

| Method | Path | Notes |
|---|---|---|
| GET | /healthz | public liveness (no version) |
| GET | / | service metadata |

## Versioning
Breaking changes ship under `/api/v2`; v1 documented here is the only live
version. Frontend pins `/api/v1`.
