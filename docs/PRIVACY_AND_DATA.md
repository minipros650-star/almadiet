# Privacy & Data Lifecycle

**Status:** Implemented

## 1. What we collect and why

| Data | Purpose | Storage | Retention |
|---|---|---|---|
| Email, name, phone, region, language | Account + app language | `users` (Postgres) | Until account deletion |
| Password | Authentication | Argon2id hash only (never plaintext, never logged) | Until changed/deletion |
| Pregnancy week/trimester, weight, optional BP/Hb/glucose, allergies, dietary preference | Meal personalization + clinician summary | `health_records` | Until account deletion |
| Consent version + timestamp | Legal/consent proof | `consents` | Until account deletion |
| Generated meal plans | App functionality | `diet_plans` | Until account deletion |
| Security events (login, lockout, token revocation, profile change, export/deletion) | Abuse detection & audit | `audit_logs` (no health values) | 12 months |
| Refresh token hashes | Session management | `refresh_tokens` (hashed; revocable) | Until revocation/expiry/deletion |

Not collected: precise location, contacts, analytics SDKs, advertising IDs.
The app contains **no third-party analytics**. Crash reports are not
integrated; if they ever are, they must exclude health fields.

## 2. Data flows

- Flutter ⇄ FastAPI over HTTPS; JWT access token (15 min) + rotating refresh
  token (30 days) stored in **platform secure storage** (Android Keystore /
  iOS Keychain via `flutter_secure_storage`), never SharedPreferences.
- Images: illustrative meal images are fetched from a third-party image URL
  service; requests contain only the meal name — never user data.
- Audit logs contain **user ids, event codes, and IPs only** — never health
  values, never allergy lists, never meal-plan contents.

## 3. User rights (implemented endpoints)

| Right | Endpoint | Behaviour |
|---|---|---|
| Access/export | `GET /api/v1/privacy/export` | JSON download of profile, health records, plans, consents |
| Delete health records | `DELETE /api/v1/health/records/{id}` | Owner-only hard delete, audited |
| Delete account | `DELETE /api/v1/privacy/account` | Cascades all user data; audit row kept without health content |
| Logout everywhere | `POST /api/v1/auth/logout-all` | Revokes all refresh tokens |

## 4. Consent

Before any health data is saved, the client must show the consent screen
(what the app does/does not do, data collected, clinician disclaimer) and
record acceptance. `POST /api/v1/consent` stores `consent_version` +
`accepted_at`. Health-record creation returns **409 CONSENT_REQUIRED** until
a current-version consent exists (enforced server-side, tested).

## 5. Compliance notes

- This documentation is an engineering description, not legal advice;
  a DPO/legal review is required before public launch in any jurisdiction.
- Health data is sensitive: transport is TLS-only, at-rest encryption is the
  database host's responsibility (documented in RELEASE_CHECKLIST.md),
  and access is strictly user-scoped (IDOR-tested).

## 6. Secrets

No secrets are committed. See `.env.example` and THREAT_MODEL.md §secrets.
`docker-compose.yml` credentials are development-only placeholders that must
be overridden in any real deployment.
