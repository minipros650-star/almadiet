# AlmaDiet — Supabase + Vercel Deployment Guide

Architecture: **Flutter mobile app → Supabase Auth (Google OAuth) → FastAPI on Vercel → Supabase Postgres + Supabase Storage**

Supabase project ref: `ipquqyzlqugalmhfhfbt` (ap-south-1)

---

## 1. What was migrated (summary)

| Area | Before | After |
|---|---|---|
| Database | Docker/localhost Postgres, SQLAlchemy models | **Supabase Postgres**, versioned SQL migrations in `supabase/migrations/` (applied + verified live) |
| Identity | App-owned `users` table, custom JWTs | **Supabase Auth** (`auth.users`) + `public.profiles` keyed by `auth.users.id`, auto-provisioned by trigger |
| Backend auth | HS256 first-party JWTs | **Supabase JWT validation** server-side (`AUTH_MODE=supabase`); local mode kept for dev/tests |
| Flutter auth | Custom email/password + self-managed tokens | **supabase_flutter** Google OAuth (PKCE), SDK-managed secure session persistence |
| Images | External Pollinations.ai generated URLs | **Supabase Storage** service (`meal-images` public catalog, `user-private` private + signed URLs) with magic-byte upload validation |
| Deployment | localhost/dev uvicorn | **Vercel** serverless (`backend/api/index.py`), controlled `python -m scripts.migrate` / `scripts.seed_meals` |

Safety invariants preserved: server-side BMI/week derivation, deterministic allergen/food-safety filter before ranking, no-safe-meals safe state, clinician-review gates, no ML in the decision path.

---

## 2. Migration & rollback

**Applied migrations (Supabase, in order):**
1. `profiles_and_user_data_rls` — legacy tables renamed to `legacy_*` (rollback point); `profiles` (FK → `auth.users.id`, CHECK constraints, indexes, trigger auto-provision on user creation); catalog (`meals`, `allergens`, `meal_allergens`); user data (`health_records`, `diet_plans`, `meal_favorites`, `consents`, `urgent_notes`, `audit_logs`, `user_files`); RLS enabled on every table; self-service policies with `WITH CHECK`.
2. `storage_buckets_and_allergens` — 12-code allergen taxonomy (mirrors `backend/app/domain/allergens.py`); Storage RLS policies (public read on `meal-images`; `user-private` confined to `{auth.uid()}/...` prefix for select/insert/update/delete).
3. `security_hardening` — legacy tables locked (RLS + REVOKE); functions pinned with `set search_path = ''`; `handle_new_user()` EXECUTE revoked from anon/authenticated (Supabase linter clean).
4. `governance_tables_parity` — evidence/policy/model-governance tables matching the SQLAlchemy models so the FastAPI policy gate works unchanged.

**Migration-history parity (verified):** the files in `supabase/migrations/` are byte-identical to the applied live SQL (MD5 + length checked against `supabase_migrations.schema_migrations` for all four). Local history == live history:

| Version | Name | Applied |
|---|---|---|
| 20260923120749 | profiles_and_user_data_rls | ✓ (MD5 b2700e83…) |
| 20260923120824 | storage_buckets_and_allergens | ✓ (MD5 5279d5ee…) |
| 20260923120924 | security_hardening | ✓ (MD5 91e8d075…) |
| 20260923121415 | governance_tables_parity | ✓ (MD5 0fcb1971…) |

**Verified live:** 9/9 RLS cross-user denial tests passed against the production database (two simulated users; forged `user_id` inserts rejected by `WITH CHECK`; catalog readable; profiles auto-provisioned). Supabase security linter: 0 errors, 0 warnings.

**To re-apply from scratch (new project):**
```bash
supabase link --project-ref <ref>
supabase db push            # applies supabase/migrations/*.sql in order
```

**Rollback:** within each transaction boundary —
```sql
-- Reverse order:
DROP TABLE ... (governance tables);
DROP POLICY ...; DROP TRIGGER on_auth_user_created; DROP FUNCTION handle_new_user;
DROP TABLE user_files, audit_logs, urgent_notes, consents, meal_favorites, diet_plans, health_records, meal_allergens, meals, allergens, profiles;
ALTER TABLE legacy_users RENAME TO users;  -- etc. for all 6 legacy tables
```
Legacy tables were empty at migration time (verified: 0 rows), so rollback risk is nil.

---

## 3. Required environment variables

### Vercel (backend — server-only secrets, NEVER in Flutter)
| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` (or `preview` for preview deployments) |
| `DEBUG` | `false` |
| `AUTH_MODE` | `supabase` |
| `DATABASE_URL` | Supabase **connection pooler** URI: `postgresql+asyncpg://postgres.<ref>:<PASSWORD>@aws-0-<region>.pooler.supabase.com:6543/postgres` |
| `SUPABASE_URL` | `https://ipquqyzlqugalmhfhfbt.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | current public key (`sb_publishable_…`); legacy `SUPABASE_ANON_KEY` name also accepted |
| `SUPABASE_SECRET_KEY` | current server-only key (private-bucket uploads/signed URLs); legacy `SUPABASE_SERVICE_ROLE_KEY` name also accepted |
| `SUPABASE_AUTH_VERIFY_MODE` | `jwks` (default, supported). `legacy_secret` is refused in production |
| `SUPABASE_JWKS_URL` | optional override; defaults to `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` |
| `ALLOWED_ORIGINS` | explicit list, e.g. `https://almadiet.vercel.app` (+ any web preview origins). Never `*`. |
| `JWT_SECRET_KEY` | random 48-char secret (only used if `AUTH_MODE=local`) |

### Flutter (public values only — `frontend/env.local.json` / `--dart-define`)
| Variable | Value |
|---|---|
| `SUPABASE_URL` | `https://ipquqyzlqugalmhfhfbt.supabase.co` |
| `SUPABASE_ANON_KEY` | the anon/public key (already in `env.local.json`, gitignored) |
| `API_BASE_URL` | `https://almadiet.vercel.app` (your Vercel deployment URL) |

**Never** place `SUPABASE_SECRET_KEY` (or legacy service-role key), `DATABASE_URL`, JWT secrets, or Google client secrets in Flutter, the repo, or logs. Token verification needs **no** Supabase JWT secret: FastAPI validates asymmetrically via the JWKS endpoint.

---

## 4. Manual dashboard setup checklist

### Supabase Dashboard
- [ ] **Storage**: create bucket `meal-images` (public ✅ — reviewed catalog imagery only) and `user-private` (public ❌ — enforced policies already live).
- [ ] **Auth → Providers → Google**: enable; paste the Google Cloud OAuth Client ID + Client Secret.
- [ ] **Auth → URL Configuration → Site URL**: `https://almadiet.vercel.app` (production landing).
- [ ] **Auth → URL Configuration → Redirect URLs** — add ALL of:
  - `com.almadiet.almadiet://login-callback/` (Android/iOS deep link)
  - `https://almadiet.vercel.app/**` (production)
  - `https://<project>.vercel.app/**` (each preview domain)
  - `http://localhost:4200/**` (Flutter web dev)
- [ ] **Settings → API**: no JWT secret is needed (JWKS verification). Copy the publishable key into Flutter config only.

### Google Cloud Console
- [ ] Create **OAuth 2.0 Client ID** (type: Web application).
- [ ] **Authorized redirect URIs** — add exactly:
  `https://ipquqyzlqugalmhfhfbt.supabase.co/auth/v1/callback`
- [ ] For Android (optional native sign-in flow): add an **Android** OAuth client with package name `com.almadiet.almadiet` and your signing-certificate SHA-1.

### Vercel
- [ ] Import the repository; framework preset: Other; root: repo root (config in `vercel.json`).
- [ ] Set every backend env var from the table above (Production + Preview).
- [ ] Deploy; verify `https://<deployment>/healthz` returns `{"status":"ok"}`.
- [ ] Run migrations once per release: `DATABASE_URL=... python -m scripts.migrate` (CI step or locally against the pooled URI).
- [ ] Seed the catalog once: `DATABASE_URL=... python -m scripts.seed_meals` — then approve meals through the governance endpoints (seeds are `REVIEW_REQUIRED`, never auto-approved).

### Android
- [x] `applicationId` is `com.almadiet.almadiet` (verified in `android/app/build.gradle.kts`).
- [x] Deep-link intent filter added: scheme `com.almadiet.almadiet`, host `login-callback` (launcher filter untouched).
- [ ] After Google sign-in works: `flutter build apk --release --dart-define-from-file=env.local.json`.

---

## 5. Test evidence

| Suite | Command | Result |
|---|---|---|
| Supabase RLS (live DB, 2 simulated users) | MCP `execute_sql` transaction | **9/9 pass** (auto-provision, own-row access, cross-user denial ×4, forged-insert rejection, own-insert OK, catalog readable) |
| Supabase security linter | MCP `get_advisors` | **0 errors, 0 warnings** (INFO-only intentional default-denies) |
| JWT validation matrix | `pytest backend/tests/test_supabase_migration.py` | valid ✓, expired ✓, tampered ✓, wrong secret ✓, wrong issuer ✓, wrong audience ✓, garbage ✓, missing sub ✓, no-credentials 401 ✓ |
| Upload validation | same | empty ✓, tiny ✓, oversize ✓, non-image ✓, path safety ✓ (2 skipped-safe) |
| Full backend suite | `pytest tests -q` | **154 passed, 1 skipped** |
| Flutter analyzer | `flutter analyze` | **No issues** |
| Flutter tests | `flutter test` | **17/17 pass** (config validation, no-legacy-token guarantees, OAuth cancellation safety, logout reset) |

**Remaining limitations (require humans/infrastructure, not code):**
1. Google OAuth end-to-end cannot run until the Supabase Google provider + redirect URLs are configured manually (checklist above) — the app deliberately does NOT claim the flow is complete before then.
2. Vercel deployment itself requires the Vercel project + env vars to be created by a human with account access; `vercel.json` + `backend/api/index.py` are ready.
3. Storage buckets must be created in the dashboard (SQL-created buckets are not supported; policies are already in place and tested).
4. Existing local-dev accounts (Argon2id, dev-only) are NOT migrated into Supabase Auth — production had zero users; real users onboard via Google. Password users, if any appear, use Supabase's own import/reset path.
5. Clinical content approvals (meals → PUBLISHED, policy versions) remain human clinician decisions, as designed.
