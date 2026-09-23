# Release Checklist

## Code & build
- [ ] `python -m pytest backend/tests` — green
- [ ] `cd frontend && flutter analyze` — no issues
- [ ] `cd frontend && flutter test` — green
- [ ] `flutter build apk --release` (and target platform builds) — success
- [ ] Docker image builds (`docker build -t almadiet-backend ./backend`)

## Database
- [ ] Fresh database: `alembic upgrade head` succeeds from empty
- [ ] Existing database: migration dry-run reviewed (`alembic history`)
- [ ] Rollback path verified for the newest migration
- [ ] Seed content: `content_status` values audited (no implicit PUBLISHED)

## Configuration (production)
- [ ] `DEBUG=false`
- [ ] `JWT_SECRET_KEY` set from secret manager (≥ 32 random bytes) — startup
      fails otherwise
- [ ] `ALLOWED_ORIGINS` = explicit list (startup fails on `*`)
- [ ] `DATABASE_URL` points at production Postgres with TLS
- [ ] `ENVIRONMENT=production` set (enables all validation above)

## Runtime verification
- [ ] `/healthz` returns 200
- [ ] Login/refresh/logout round-trip on the deployed build
- [ ] Register → consent → health record → plan generation smoke test
- [ ] Peanut-allergy test account receives zero peanut-tagged meals (manual
      spot check alongside automated tests)
- [ ] TLS certificate valid; HSTS + security headers set at proxy:
      `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
      `Referrer-Policy: no-referrer`, `Content-Security-Policy` for any web host

## Privacy & legal
- [ ] Privacy policy URL live and linked on consent screen
- [ ] Consent version bumped if consent text changed
- [ ] Localization reviewed by native speakers for changed strings
- [ ] Store listing text free of clinical claims (no "medical", "doctor
      approved", "treatment")

## Audit
- [ ] `git log` reviewed — no secrets in new commits (gitleaks/`git diff`
      check in CI)
- [ ] Audit log table verified writable in production
- [ ] Rollback plan: previous image tag + `alembic downgrade -1` documented
