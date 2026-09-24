-- AlmaDiet — Supabase migration: content review & publication workflow
--
-- Purpose
--   1. Give review and publication authority a database home
--      (content_role_grants) instead of an environment-variable allowlist.
--   2. Record every content state change (content_transitions) with the actor,
--      previous/new state, source/version snapshot and rationale.
--   3. Stop ordinary authenticated users reading UNREVIEWED meals through
--      PostgREST: p_meals_read was USING (true), which exposed every meal
--      regardless of content_status.
--   4. Stop allergen links leaking the existence of unreviewed meals.
--   5. Make consent acceptance idempotent (one row per user + version).
--
-- DDL mirrors the SQLAlchemy models (backend/app/models/content_role.py and
-- content_transition.py) so the API works against Supabase unchanged.
--
-- Rollback: see docs/CONTENT_GOVERNANCE.md ("Rollback"). Short version:
-- restore the previous p_meals_read (USING (true)), drop the two tables, drop
-- public.has_content_role(uuid, text[]), and drop the consents unique index.
-- No data is deleted by the downgrade except the grants/ledger rows themselves.
--
-- Safe to re-run: every statement is guarded (if not exists / or replace /
-- drop policy if exists).

-- ── 1. Role grants ────────────────────────────────────────────────────────
create table if not exists public.content_role_grants (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  role varchar(20) not null,
  granted_by_id uuid references public.users(id) on delete set null,
  granted_by_label varchar(255),
  note varchar(500),
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  constraint ck_content_role_grants_role check (role in ('REVIEWER','PUBLISHER')),
  constraint uq_content_role_grants_user_role unique (user_id, role)
);
create index if not exists ix_content_role_grants_user_id on public.content_role_grants (user_id);
create index if not exists ix_content_role_grants_role on public.content_role_grants (role);

-- ── 2. Transition ledger ──────────────────────────────────────────────────
create table if not exists public.content_transitions (
  id uuid primary key default gen_random_uuid(),
  meal_id uuid not null references public.meals(id) on delete cascade,
  actor_id uuid references public.users(id) on delete set null,
  actor_label varchar(255),
  actor_role varchar(20),
  from_status varchar(20) not null,
  to_status varchar(20) not null,
  source_snapshot varchar(500),
  evidence_version varchar(32),
  rationale text,
  created_at timestamptz not null default now(),
  constraint ck_content_transitions_to_status
    check (to_status in ('DRAFT','REVIEW_REQUIRED','REVIEWED','PUBLISHED','RETIRED'))
);
create index if not exists ix_content_transitions_meal_created
  on public.content_transitions (meal_id, created_at);

-- ── 3. Governance tables are backend-only ─────────────────────────────────
-- RLS on with NO client policies = default deny for anon/authenticated. The
-- explicit REVOKE also removes the blanket grants Supabase applies to new
-- public tables, so the denial does not depend on RLS alone.
alter table public.content_role_grants enable row level security;
alter table public.content_transitions enable row level security;
revoke all on public.content_role_grants from anon, authenticated;
revoke all on public.content_transitions from anon, authenticated;

-- ── 4. Role lookup usable from an RLS policy ──────────────────────────────
-- A policy expression runs as the querying role, so an inline subquery against
-- content_role_grants would be filtered by that table's own (deny-all) RLS and
-- always return false. SECURITY DEFINER evaluates it as the table owner, which
-- is the only reason the policy below can see a grant. search_path is empty so
-- every identifier is resolved explicitly.
create or replace function public.has_content_role(uid uuid, roles text[])
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.content_role_grants g
    where g.user_id = uid
      and g.revoked_at is null
      and g.role = any(roles)
  );
$$;

revoke all on function public.has_content_role(uuid, text[]) from public;
-- Supabase's default privileges grant EXECUTE on new functions in `public` to
-- anon/authenticated/service_role EXPLICITLY, so revoking from PUBLIC alone
-- leaves anon with EXECUTE and a role-membership oracle at
-- /rest/v1/rpc/has_content_role. Revoke it from anon by name.
revoke execute on function public.has_content_role(uuid, text[]) from anon;
grant execute on function public.has_content_role(uuid, text[]) to authenticated;

-- ── 5. Meals: only PUBLISHED content, or content staff ────────────────────
-- Replaces USING (true), which let any authenticated user read every meal
-- including REVIEW_REQUIRED / REVIEWED rows straight from PostgREST.
drop policy if exists p_meals_read on public.meals;
create policy p_meals_read on public.meals
  for select to authenticated
  using (
    content_status = 'PUBLISHED'
    or public.has_content_role(auth.uid(), array['REVIEWER','PUBLISHER'])
  );

-- ── 6. Allergen links must not reveal unreviewed meals ───────────────────
drop policy if exists p_meal_allergens_read on public.meal_allergens;
create policy p_meal_allergens_read on public.meal_allergens
  for select to authenticated
  using (
    exists (
      select 1
      from public.meals m
      where m.id = public.meal_allergens.meal_id
        and (
          m.content_status = 'PUBLISHED'
          or public.has_content_role(auth.uid(), array['REVIEWER','PUBLISHER'])
        )
    )
  );

-- ── 7. Consent acceptance is idempotent ──────────────────────────────────
-- Historic duplicate rows would make the unique index unbuildable. This aborts
-- the migration instead of silently deleting consent records: run the SELECT
-- below, reconcile deliberately, then re-apply.
do $$
declare dupes integer;
begin
  select count(*) into dupes from (
    select user_id, consent_version
    from public.consents
    group by user_id, consent_version
    having count(*) > 1
  ) d;
  if dupes > 0 then
    raise exception
      'consents holds % duplicate (user_id, consent_version) group(s); reconcile before applying this migration',
      dupes;
  end if;
end $$;

create unique index if not exists uq_consents_user_version
  on public.consents (user_id, consent_version);

-- To inspect duplicates without applying anything:
--   select user_id, consent_version, count(*)
--   from public.consents group by 1,2 having count(*) > 1;
