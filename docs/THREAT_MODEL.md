# Threat Model

**Status:** Implemented mitigations marked ✅ · Method: STRIDE per surface

## Assets
1. Authentication credentials & session tokens
2. Health records (weight, BP, Hb, glucose, allergies, conditions)
3. Consent records
4. Meal content integrity
5. Audit log integrity

## Trust boundaries
- Flutter app ⇄ FastAPI (public internet)
- FastAPI ⇄ PostgreSQL
- Admin/content-reviewer actions ⇄ normal user actions

## Threat catalogue (selected, with mitigations)

| # | Threat | Surface | Mitigation |
|---|---|---|---|
| T1 | Plaintext password theft | DB compromise | ✅ Argon2id hashes (passlib argon2), no plaintext anywhere |
| T2 | JWT forging via default/committed secret | Config | ✅ Startup **fails** if `JWT_SECRET_KEY` missing/known-default in non-debug (`app/config.py`), secret never in code |
| T3 | Long-lived stolen access token | Client | ✅ 15-min expiry + 30-day rotating refresh; refresh reuse revokes the family |
| T4 | Token theft from SharedPreferences | Client device | ✅ `flutter_secure_storage` (Keystore/Keychain); legacy `auth_token` key **deleted** on migration |
| T5 | Credential stuffing / brute force | `/auth/login` | ✅ Failed-attempt lockout (5 → 15 min) + login rate limit (5/min/IP), generic error messages |
| T6 | IDOR (user A reads user B health data) | All `/api/v1/*` user data | ✅ Every query filtered by `current_user.id` (+ dedicated tests) |
| T7 | Unauthenticated access to health data | API | ✅ All user-data routes require bearer token (+ tests) |
| T8 | Expired/invalid JWT accepted | API | ✅ Expiry & signature validated per request (+ tests) |
| T9 | Wildcard CORS in production | Browser clients | ✅ Production startup rejects `ALLOWED_ORIGINS="*"` (`config.py` validation, tested) |
| T10 | Route shadowing (`/api/meals/images/all` eaten by `/{meal_id}`) | API | ✅ Static routes registered before parameterized; UUID path converter; route-resolution tests |
| T11 | Verbose exception leakage | API | ✅ Global error envelope; stack traces never returned; `DEBUG=false` in prod |
| T12 | SQL injection | API | ✅ SQLAlchemy bound parameters exclusively; no string-built SQL |
| T13 | Mass assignment | `PATCH /auth/me` | ✅ Pydantic allow-list schema; password/email immutable via profile route |
| T14 | Audit log poisoning / sensitive data in logs | Logs | ✅ Structured logger with event codes; health values prohibited (code review + test greps log payload builders) |
| T15 | Allergen bypass through swap/plan flows | Recommendations | ✅ Single `SafetyValidator` used by plan, swap, and browse paths; property tests assert zero leakage |
| T16 | Emergency mis-triage by app | Urgent help | ✅ Feature provides information only; wording tests prohibit treatment/resolution claims |
| T17 | Content poisoning (unsafe meal text) | Governance | ✅ State machine; only `PUBLISHED` in prod; claims validator rejects unsourceable clinical claims |
| T18 | Consent bypass via direct API calls | `/health/record` | ✅ Server-side consent check (409 CONSENT_REQUIRED), tested |
| T19 | Refresh-token replay after logout | `/auth/refresh` | ✅ Revocation on logout; logout-all revokes all sessions |

## Residual risks (accepted, documented)
- Render/PAAS-level TLS termination assumed; HSTS set via proxy config in
  RELEASE_CHECKLIST.
- Image service availability depends on third party (degrades to placeholder;
  no data exposure — meal name only).
- No WAF/DDoS layer in current deployment; rate limiting is application-level.
