# Content Governance

**Status:** Implemented · **Applies to:** every meal record

## 1. Principles

1. Every nutrition record is traceable to a **source** and **evidence version**.
2. Content moves through explicit lifecycle states; nothing enters production
   recommendations implicitly.
3. Reviewers are accountable: reviewer identity and review date are stored.
4. If provenance is unknown, the content is marked accordingly and excluded
   from production recommendation flows.
5. Review and publication authority is **data** kept in the database, not an
   environment variable or a value a request can submit.

## 2. Lifecycle states

| State | Meaning | In production recommendations? |
|---|---|---|
| `DRAFT` | Being authored | No |
| `REVIEW_REQUIRED` | Ready for review | No |
| `REVIEWED` | Content reviewed, awaiting publish decision | No |
| `PUBLISHED` | Reviewed and released | **Yes** |
| `RETIRED` | Withdrawn (unsafe, outdated, or unsourceable) | No |

State transitions are enforced in `backend/app/domain/content_state.py`:

```
DRAFT → REVIEW_REQUIRED → REVIEWED → PUBLISHED → RETIRED
            ↑                    │
            └────── (edit re-opens review) ──────┘
```

Invalid transitions raise `ValueError` (tested). The two transitions that move
content *towards* publication each require a distinct duty:

```
REVIEW_REQUIRED ──REVIEWER──▶ REVIEWED ──PUBLISHER──▶ PUBLISHED
```

## 3. Required provenance fields (meals table)

- `source` (human-readable origin, e.g. dataset reference)
- `source_url` (optional link)
- `evidence_version` (string, bumped on content change)
- `reviewed_at`, `reviewer`
- `content_status` (lifecycle state above)
- `serving_basis` (what one serving means)

**No field named `clinically_approved` exists.** The previous schema set
`clinically_approved=true` on every seed row without any review — that field
was removed. Governance status now reflects reality: seeded rows are imported
as `REVIEW_REQUIRED` with the dataset as `source`; they must be reviewed and
published before production recommendations use them. In development/test the
pipeline can be configured to include `REVIEWED` content so the app remains
testable (`CONTENT_INCLUDE_STATUSES`).

## 4. Review workflow (data model)

`content_versions` table records each version: meal_id, version, payload
snapshot, change note, reviewer, status, timestamps.

`content_transitions` is the governance ledger. Every state change records:

| Column | Meaning |
|---|---|
| `actor_id` | the user id from the **validated session token** |
| `actor_label`, `actor_role` | attribution snapshot and which duty authorised it |
| `from_status`, `to_status` | previous and new state |
| `source_snapshot`, `evidence_version` | provenance captured at decision time |
| `rationale` | the reviewer's stated reason |
| `created_at` | when the decision was made |

The administrative endpoints are role-guarded (see §7) and never exposed to
normal users. Seeding does not call them: nothing in the import path can
publish.

## 5. Prohibited claims

The seed dataset's free-text `who_alignment` claims were removed. Any content
string claiming "WHO approved/aligned", "clinically approved", "medically
validated", "doctor approved", or similar requires a documented evidence URL
and reviewer sign-off, and is otherwise rejected.

Enforcement lives in `backend/app/domain/clinical_claims.py` (the phrase list and
the patient-visible field inventory), applied at three points:

* **import** — `seed_meals` sanitizes the prose fields it owns, so unusable text
  never enters the catalog;
* **review** and **publish** — both gates reject a meal that still carries a
  claim anywhere a patient could see it (§8).

Two mechanisms cover every patient-visible field:

* **Mutable prose** (`cautions`, `food_safety_notes`, `best_time_to_eat`,
  `serving_basis`, `serving_size`, `benefits[]`, `substitutions[]`) — the
  offending sentence is removed.
* **Inspected fields** (`name`, the four translated names, `region`,
  `meal_type`, `cuisine`, `dataset_id`, `source`, `source_url`,
  `evidence_version`, `content_status`, `trimester_suitability[]`,
  `ingredients[].name|quantity`) — never rewritten, because editing them would
  change what the content *is*; a claim there blocks review and publication.

`allergens[]` is the one documented exemption
(`DERIVED_PATIENT_PATHS`): those are catalog taxonomy codes produced by the
safety matcher, not text a claim can live in. `patient_visible_text_paths()`
enumerates the coverage and `backend/tests/test_consent_and_claims.py` proves it
against the response schema, so the guarantee cannot silently rot.

## 6. Retiring content

Retired content stays queryable for audit but is excluded from all
recommendation and browse flows. Retiring requires a role-granted reviewer or
publisher and records a rationale in `content_transitions` (and a change note in
`content_versions`).

## 7. Roles and authority

| Action | Required role | Endpoint |
|---|---|---|
| `REVIEW_REQUIRED → REVIEWED` | `REVIEWER` | `POST /api/v1/content-governance/meals/{id}/review` |
| `REVIEWED → PUBLISHED` | `PUBLISHER` | `POST /api/v1/content-governance/meals/{id}/publish` |
| any → `RETIRED` | `REVIEWER` or `PUBLISHER` | `POST /api/v1/content-governance/meals/{id}/retire` |
| review queue | `REVIEWER` or `PUBLISHER` | `GET /api/v1/content-governance/meals/pending` |
| decision ledger | `REVIEWER` or `PUBLISHER` | `GET /api/v1/content-governance/meals/{id}/history` |
| governance / evidence surfaces | `REVIEWER` or `PUBLISHER` | `/api/v1/governance/*`, `/api/v1/evidence/*` |

A request body carries **only** `rationale`. The actor is the user identified by
the validated session token and the role is read from the database for that user
id. The request models set `extra="forbid"`, so submitting `email`, `user_id`,
`role` or any other field is a 422 — rejected, not silently ignored.

Grants live in `content_role_grants` (one row per user + role; revocation stamps
`revoked_at` and the row is kept for the grant history). There is deliberately no
HTTP route that grants a role, so privilege escalation has no request path.

### Bootstrap procedure

1. The person must **sign in once** — the local `users` row is provisioned from
   the validated Supabase token on first sight, and the grant references it.
2. Run the operator command against the target database:

   ```bash
   cd backend
   python -m scripts.bootstrap_content_role list
   python -m scripts.bootstrap_content_role grant --email reviewer@example.org --role REVIEWER
   python -m scripts.bootstrap_content_role grant --email lead@example.org --role PUBLISHER --note "clinical lead"
   python -m scripts.bootstrap_content_role revoke --email reviewer@example.org --role REVIEWER
   ```

3. Against production the command refuses unless the operator explicitly accepts
   the authority change:

   ```bash
   CONTENT_ROLE_BOOTSTRAP_CONFIRM=I-ACCEPT-AUTHORITY-CHANGE \
       python -m scripts.bootstrap_content_role grant --email lead@example.org --role PUBLISHER
   ```

Equivalent SQL, for environments where the command cannot run:

```sql
insert into public.content_role_grants (user_id, role, granted_by_label, note)
select id, 'REVIEWER', 'manual bootstrap', 'first reviewer'
from public.users where email = 'reviewer@example.org'
on conflict (user_id, role) do update set revoked_at = null, granted_at = now();
```

### Relationship to `REVIEWER_EMAILS`

The email allowlist is no longer the authority. Production review and
publication require a database grant. `REVIEWER_EMAILS` is not read anywhere in
the application (a test asserts this). `BOOTSTRAP_ADMIN_EMAILS` remains a
**development-only** convenience so local and test flows work without a grant
step; it is never consulted when `ENVIRONMENT=production`.

## 8. What both gates check

Both `review` and `publish` run the same blockers, so incomplete or unsafe
content cannot advance at either step. Falling short leaves the meal where it is
— the fail-closed direction. A refusal is
`422` / `blocking_code=CONTENT_NOT_PUBLISHABLE` with a `blockers` list:

| Blocker | Meaning |
|---|---|
| `MISSING_INGREDIENTS` | the meal lists no ingredients |
| `MISSING_NUTRITION_DATA` | calories ≤ 0, or no macronutrient recorded |
| `MISSING_EVIDENCE` | no `source`/`source_url`, or no `evidence_version` |
| `MISSING_ALLERGEN_LINKS` | stored links do not cover what the safety matcher detects |
| `UNSOURCED_CLINICAL_CLAIM` | a prohibited claim remains patient-visible |

`MISSING_ALLERGEN_LINKS` is the safety-critical one: the check recomputes
`allergens_for_ingredients` for the meal and requires a stored link for
everything it finds. A missing link is exactly how an allergen would reach a user
who declared it, so publication is blocked rather than waved through.

Invalid transitions and missing roles are refused with
`409` / `blocking_code=INVALID_TRANSITION` and `403` /
`blocking_code=ROLE_REQUIRED` respectively.

### Separation of duties

The publisher must not be the reviewer who passed the meal. The check compares
the actor id of the meal's most recent `REVIEWED` transition with the publishing
actor, so it is identity-based rather than name-based. Violations are refused
with `409` / `blocking_code=SELF_APPROVAL_FORBIDDEN`.

`settings.CONTENT_REQUIRE_SEPARATION_OF_DUTIES` defaults to `true`. **Production
cannot relax it** — like `CONTENT_INCLUDE_STATUSES`, the production resolver only
ever tightens. Development/test may turn it off so single-operator flows stay
testable.

## 9. Visibility

| Reader | Sees |
|---|---|
| Unauthenticated API caller | only `PUBLISHED` (the API filters to `PUBLISHED`) |
| Authenticated ordinary user | only `PUBLISHED` |
| Content staff | `PUBLISHED`, `REVIEW_REQUIRED`, `REVIEWED` |

At the database layer, `meals` carries `p_meals_read`:

```sql
using (
  content_status = 'PUBLISHED'
  or public.has_content_role(auth.uid(), array['REVIEWER','PUBLISHER'])
)
```

This replaced `USING (true)`, which allowed any holder of the publishable key
plus a valid JWT to read every meal — including unreviewed content — straight
from PostgREST. `meal_allergens` is scoped the same way, so allergen links no
longer reveal unreviewed meals either.

`public.has_content_role(uuid, text[])` is `SECURITY DEFINER` (owned by the table
owner, which bypasses RLS) with `search_path = ''`. It must be `SECURITY
DEFINER`: a policy expression evaluates as the *querying* role, and
`content_role_grants` is deny-all to clients, so an inline subquery would always
return false.

Anonymous and authenticated roles hold no privileges on `content_role_grants` or
`content_transitions` (RLS enabled, no policies, plus an explicit `REVOKE`).

## 10. Consent

`POST /api/v1/consent` is an ownership-scoped idempotent upsert. Acceptance is a
fact per (user, version): repeating the same version returns the existing record
(`created: false`) instead of appending a duplicate, and no duplicate audit entry
is written. The user always comes from the token — the request model forbids
extra fields. A unique constraint (`uq_consents_user_version` on
`(user_id, consent_version)`) backs the guarantee against concurrent requests,
and the insert runs inside a SAVEPOINT so a lost race cannot roll back the
surrounding request.

## 11. Implementation map

| Layer | File |
|---|---|
| Roles | `backend/app/domain/content_roles.py`, `backend/app/models/content_role.py` |
| Ledger | `backend/app/models/content_transition.py` |
| Authority | `backend/app/auth/content_authz.py` |
| Workflow | `backend/app/services/content_review_service.py`, `backend/app/routers/content_governance_router.py` |
| Claim policy | `backend/app/domain/clinical_claims.py` |
| Bootstrap | `backend/scripts/bootstrap_content_role.py` |
| Schema | `backend/alembic/versions/0006_content_review_workflow.py`, `supabase/migrations/20260924183610_content_review_workflow.sql` |

## 12. Migrations

* Alembic `0006_content_review_workflow` creates both tables and adds the
  consents unique constraint. It runs on PostgreSQL and SQLite (batch mode).
* `supabase/migrations/20260924183610_content_review_workflow.sql` mirrors the
  DDL, installs the RLS replacement and `has_content_role`, and adds the consents
  unique index. It was applied to Supabase on 2026-09-24 and is recorded in the
  project's migration history under that version.

Two entries exist in the live history: that migration, and a follow-up
`revoke_anon_execute_on_has_content_role`. Supabase's default privileges grant
EXECUTE on new `public` functions to `anon` **explicitly**, so
`REVOKE ... FROM public` left an unauthenticated role-membership oracle at
`/rest/v1/rpc/has_content_role`. The revoke is folded into the workflow
migration file above, so a fresh apply needs no second step; the follow-up
existed only to fix the database that had already been migrated.
`authenticated` deliberately keeps EXECUTE: the `meals` policy expression is
evaluated as the querying role and therefore requires it.

The SQL migration **aborts** if `consents` already holds duplicate
`(user_id, consent_version)` rows, rather than deleting patient records. Inspect
with:

```sql
select user_id, consent_version, count(*)
from public.consents group by 1, 2 having count(*) > 1;
```

### Rollback

Rollback of the Supabase migration, in order:

```sql
-- 1. Restore the previous (permissive) catalog policy.
drop policy if exists p_meals_read on public.meals;
create policy p_meals_read on public.meals
  for select to authenticated using (true);

-- 2. Restore the previous allergen-link policy.
drop policy if exists p_meal_allergens_read on public.meal_allergens;
create policy p_meal_allergens_read on public.meal_allergens
  for select to authenticated using (true);

-- 3. Drop the consents idempotency index.
drop index if exists public.uq_consents_user_version;

-- 4. Drop the workflow tables and helper.
drop table if exists public.content_transitions;
drop table if exists public.content_role_grants;
drop function if exists public.has_content_role(uuid, text[]);
```

Step 1 is a **security regression** — it re-exposes unreviewed meals to any
authenticated reader. Do not roll back that far unless the workflow itself is
being abandoned; rolling back the API deployment alone is sufficient to disable
review and publication, because the roles and ledger are inert without code that
reads them.

Alembic: `python -m scripts.migrate downgrade -1` drops the two tables and the
consents constraint; it does not touch RLS, which lives in the Supabase
migration.

### Production enablement order

1. Apply the Supabase migration (operator approval required).
2. Grant the first `REVIEWER` and `PUBLISHER` roles.
3. Import the dataset (staging first: `python -m scripts.staging_import_meals`),
   which lands every meal in `REVIEW_REQUIRED`.
4. Review and publish deliberately. Until step 4 happens the app correctly shows
   an empty catalog.

## 13. Safety ordering is unchanged

The hard exclusions run **server-side, before ranking**: declared allergies,
dietary restrictions, pregnancy food-safety rules, and clinician-review
conditions (`backend/app/services/meal_safety_service.py`, with the ranker
contract failing closed). Only `PUBLISHED` content is eligible
(`SUGGESTABLE_STATUSES`). This workflow does not alter that order — it only
decides which content becomes eligible for it.
