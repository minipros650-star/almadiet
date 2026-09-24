-- AlmaDiet — Supabase migration 0005: ORM schema parity for catalog + identity
--
-- WHY: the FastAPI backend maps the SQLAlchemy models in backend/app/models
-- directly onto these tables. Migration 0001 (20260923120749) created a
-- parallel *re-design* of `meals`, `allergens`, `meal_allergens` and
-- `health_records`, and never created `users` at all (migration 0003 renamed
-- the ORM-shaped `users` aside to `legacy_users`). Every query against them
-- therefore failed at runtime, e.g.:
--
--   asyncpg.exceptions.UndefinedColumnError: column meals.dataset_id does not exist
--
-- Migration 0004 (20260923121415) established the intended direction in its
-- own header: "DDL mirrors the SQLAlchemy models (backend/app/models) so the
-- FastAPI policy gate and reviewer endpoints work unchanged against Supabase."
-- This migration finishes that parity work for the tables that were missed.
--
-- WHAT:
--   * creates public.users in the ORM shape (the API auto-provisions a mirror
--     row per Supabase Auth subject — see app.services.user_service
--     .ensure_user_for_supabase — and every user-scoped row FKs to it);
--   * rebuilds public.meals, public.meal_allergens, public.health_records,
--     public.consents and public.audit_logs in the ORM shape;
--   * rebuilds public.allergens from (code, label) to (category, display_name),
--     carrying the seeded rows across;
--   * repoints user-owned foreign keys from public.profiles(id) to public.users(id).
--
-- DATA: every table reshaped here was empty at the time of writing. The single
-- exception is public.allergens, whose 12 seeded rows are carried across. A
-- guard below aborts the whole migration if any table to be reshaped is
-- non-empty, so this can never silently discard data. The legacy_* rollback
-- artifacts are deliberately left untouched.

-- ── 0. Fail closed if anything we reshape holds data ─────────────────
do $$
declare
  t text;
  n bigint;
begin
  foreach t in array array['meals', 'meal_allergens', 'health_records', 'consents', 'audit_logs'] loop
    execute format('select count(*) from public.%I', t) into n;
    if n > 0 then
      raise exception
        'Refusing to reshape public.%: % row(s) present. Migrate the rows explicitly instead.', t, n;
    end if;
  end loop;
end $$;

-- ── 1. public.users — ORM shape (Alembic 0001 + 0004) ────────────────
create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  email varchar(255) not null,
  -- Supabase owns authentication; mirror rows carry a deliberately unusable
  -- marker hash so local password login can never succeed for them.
  password_hash varchar(255) not null,
  name varchar(255) not null,
  phone varchar(20),
  region varchar(20) not null default 'kerala',
  language varchar(5) not null default 'en',
  lmp_date date,
  due_date date,
  age integer,
  height_cm double precision,
  pre_pregnancy_weight_kg double precision,
  -- Server-derived profile fields — never client-supplied.
  pre_pregnancy_bmi double precision,
  gestational_week integer,
  trimester integer,
  profile_complete boolean not null default false,
  -- Suggestion preferences (ranking inputs). NULL vs [] is load-bearing for
  -- profile completion: NULL = not yet declared, [] = declared "none".
  declared_allergies jsonb,
  dietary_preference varchar(20),
  disliked_ingredients jsonb,
  cooking_time_preference varchar(20),
  budget_preference varchar(20),
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  constraint uq_users_email unique (email),
  constraint ck_users_age check (age is null or (age between 14 and 55)),
  constraint ck_users_height check (height_cm is null or (height_cm between 100 and 250)),
  constraint ck_users_prepreg_weight
    check (pre_pregnancy_weight_kg is null or (pre_pregnancy_weight_kg between 30 and 200)),
  constraint ck_users_region check (region in ('kerala','tamilnadu','karnataka','andhra')),
  constraint ck_users_language check (language in ('en','ml','ta','kn','te')),
  constraint ck_users_prepreg_bmi
    check (pre_pregnancy_bmi is null or (pre_pregnancy_bmi between 10 and 60)),
  constraint ck_users_gest_week
    check (gestational_week is null or (gestational_week between 1 and 42)),
  constraint ck_users_trimester check (trimester is null or (trimester between 1 and 3)),
  constraint ck_users_diet_pref
    check (dietary_preference is null or dietary_preference in ('veg','nonveg','eggetarian')),
  constraint ck_users_cook_pref
    check (cooking_time_preference is null or cooking_time_preference in ('quick','moderate','relaxed')),
  constraint ck_users_budget_pref
    check (budget_preference is null or budget_preference in ('low','medium','high'))
);
create index if not exists ix_users_email on public.users (email);

-- ── 2. Detach foreign keys pointing at the tables being rebuilt ──────
do $$
declare
  r record;
begin
  for r in
    select c.conrelid::regclass::text as tbl, c.conname
    from pg_constraint c
    where c.contype = 'f'
      and c.confrelid in (
        'public.meals'::regclass,
        'public.health_records'::regclass,
        'public.allergens'::regclass
      )
  loop
    execute format('alter table %s drop constraint %I', r.tbl, r.conname);
  end loop;
end $$;

-- User-owned tables were pointed at profiles(id); the API writes to users(id).
do $$
declare
  r record;
begin
  for r in
    select c.conrelid::regclass::text as tbl, c.conname
    from pg_constraint c
    where c.contype = 'f' and c.confrelid = 'public.profiles'::regclass
  loop
    execute format('alter table %s drop constraint %I', r.tbl, r.conname);
  end loop;
end $$;

-- ── 3. Drop the divergent, empty tables ──────────────────────────────
drop table if exists public.meal_allergens;
drop table if exists public.meals;
drop table if exists public.health_records;
drop table if exists public.consents;
drop table if exists public.audit_logs;

-- ── 4. public.meals — ORM shape (Alembic 0002 + 0004) ────────────────
create table public.meals (
  id uuid primary key default gen_random_uuid(),
  dataset_id varchar(20),
  name varchar(255) not null,
  name_tamil varchar(255),
  name_malayalam varchar(255),
  name_kannada varchar(255),
  name_telugu varchar(255),
  region varchar(100) not null,
  meal_type varchar(50) not null,
  trimester_suitability jsonb,
  cuisine varchar(100),
  calories double precision not null default 0,
  protein_g double precision not null default 0,
  carbs_g double precision not null default 0,
  fat_g double precision not null default 0,
  fiber_g double precision not null default 0,
  iron_mg double precision not null default 0,
  calcium_mg double precision not null default 0,
  folate_mcg double precision not null default 0,
  vitamin_c_mg double precision not null default 0,
  sodium_mg double precision not null default 0,
  sugar_g double precision not null default 0,
  ingredients jsonb,
  serving_size varchar(100),
  serving_basis varchar(200),
  preparation_time_minutes integer,
  preparation_notes text,
  benefits jsonb,
  cautions text,
  food_safety_notes text,
  best_time_to_eat varchar(50),
  substitutions jsonb,
  image_url varchar(500),
  is_vegetarian boolean not null default true,
  -- Content governance (replaces the legacy clinically_approved / who_alignment).
  source varchar(500),
  source_url varchar(500),
  evidence_version varchar(32) not null default '1',
  reviewed_at timestamptz,
  reviewer varchar(255),
  approved_at timestamptz,
  approved_by varchar(255),
  retired_at timestamptz,
  clinician_review_required boolean not null default false,
  catalog_version varchar(32) not null default '1',
  content_status varchar(20) not null default 'REVIEW_REQUIRED',
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  constraint uq_meals_dataset_id unique (dataset_id),
  constraint ck_meal_cal check (calories >= 0),
  constraint ck_meal_macros check (protein_g >= 0 and carbs_g >= 0 and fat_g >= 0),
  constraint ck_meal_micro check (fiber_g >= 0 and iron_mg >= 0 and calcium_mg >= 0),
  constraint ck_meal_micro2 check (folate_mcg >= 0 and vitamin_c_mg >= 0),
  constraint ck_meal_micro3 check (sodium_mg >= 0 and sugar_g >= 0),
  constraint ck_meal_prep check (preparation_time_minutes is null or preparation_time_minutes >= 0),
  constraint ck_meal_content_status
    check (content_status in ('DRAFT','REVIEW_REQUIRED','REVIEWED','PUBLISHED','RETIRED'))
);
create index if not exists ix_meals_name on public.meals (name);
create index if not exists ix_meals_region on public.meals (region);
create index if not exists ix_meals_dataset_id on public.meals (dataset_id);
create index if not exists ix_meals_content_status on public.meals (content_status);
create index if not exists ix_meals_content_status_version on public.meals (content_status, catalog_version);

-- ── 5. public.allergens — (category, display_name), rows carried over ─
alter table public.allergens rename to allergens_pre_parity;

create table public.allergens (
  id uuid primary key default gen_random_uuid(),
  category varchar(32) not null,
  display_name varchar(100) not null,
  constraint uq_allergens_category unique (category)
);
create index if not exists ix_allergens_category on public.allergens (category);

-- The previous design used (code, label) with the same stable category codes.
insert into public.allergens (id, category, display_name)
select b.id, b.code, b.label
from public.allergens_pre_parity b
where b.code in (
  'peanut','tree_nut','milk','egg','wheat_gluten','soy',
  'fish','shellfish','sesame','mustard','sulfite','other'
)
on conflict (category) do nothing;

do $$
declare
  src bigint;
  dst bigint;
begin
  select count(*) into src from public.allergens_pre_parity;
  select count(*) into dst from public.allergens;
  if dst < src then
    raise exception
      'Allergen parity mapping lost rows (% of % carried). Inspect code values before continuing.',
      dst, src;
  end if;
  if dst = 0 then
    raise exception 'Allergen parity mapping carried zero rows.';
  end if;
end $$;

drop table public.allergens_pre_parity;

-- ── 6. public.meal_allergens — ORM shape ────────────────────────────
create table public.meal_allergens (
  meal_id uuid not null references public.meals(id) on delete cascade,
  allergen_id uuid not null references public.allergens(id) on delete restrict,
  match_type varchar(20) not null default 'synonym',
  matched_term varchar(255) not null,
  primary key (meal_id, allergen_id, matched_term),
  constraint uq_meal_allergen_term unique (meal_id, allergen_id, matched_term)
);

-- ── 7. public.health_records — ORM shape ────────────────────────────
create table public.health_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  trimester integer not null,
  week_number integer not null,
  current_weight_kg double precision not null,
  bmi double precision,
  blood_pressure_sys double precision,
  blood_pressure_dia double precision,
  hemoglobin double precision,
  blood_sugar_fasting double precision,
  allergies jsonb,
  medical_conditions jsonb,
  is_vegetarian boolean not null default false,
  dietary_preference varchar(20) not null default 'nonveg',
  notes text,
  recorded_at timestamptz default now(),
  constraint ck_hr_trimester check (trimester between 1 and 3),
  constraint ck_hr_week check (week_number between 1 and 42),
  constraint ck_hr_trimester_week_consistent check (
    (trimester = 1 and week_number between 1 and 13) or
    (trimester = 2 and week_number between 14 and 26) or
    (trimester = 3 and week_number between 27 and 42)
  ),
  constraint ck_hr_weight check (current_weight_kg between 30 and 200),
  constraint ck_hr_bmi check (bmi is null or (bmi between 10 and 60)),
  constraint ck_hr_bpsys check (blood_pressure_sys is null or (blood_pressure_sys between 60 and 250)),
  constraint ck_hr_bpdia check (blood_pressure_dia is null or (blood_pressure_dia between 40 and 150)),
  constraint ck_hr_hb check (hemoglobin is null or (hemoglobin between 3 and 20)),
  constraint ck_hr_bs check (blood_sugar_fasting is null or (blood_sugar_fasting between 20 and 600)),
  constraint ck_hr_dietpref check (dietary_preference in ('veg','nonveg','eggetarian'))
);
create index if not exists ix_hr_user_time on public.health_records (user_id, recorded_at);

-- ── 8. public.consents — ORM shape ──────────────────────────────────
create table public.consents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  consent_version varchar(32) not null,
  accepted_at timestamptz default now(),
  ip_hash varchar(64)
);
create index if not exists ix_consents_user_time on public.consents (user_id, accepted_at);

-- ── 9. public.audit_logs — ORM shape (no health values in context) ──
create table public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users(id) on delete set null,
  event_code varchar(64) not null,
  context jsonb,
  ip_hash varchar(64),
  created_at timestamptz default now()
);
create index if not exists ix_audit_user_time on public.audit_logs (user_id, created_at);
create index if not exists ix_audit_event on public.audit_logs (event_code);

-- ── 10. Restore foreign keys the ORM expects ────────────────────────
alter table public.meal_images
  add constraint meal_images_meal_id_fkey
  foreign key (meal_id) references public.meals(id) on delete cascade;

alter table public.content_versions
  add constraint content_versions_meal_id_fkey
  foreign key (meal_id) references public.meals(id) on delete cascade;

alter table public.meal_favorites
  add constraint meal_favorites_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade;

alter table public.meal_favorites
  add constraint meal_favorites_meal_id_fkey
  foreign key (meal_id) references public.meals(id) on delete cascade;

alter table public.diet_plans
  add constraint diet_plans_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade;

alter table public.diet_plans
  add constraint diet_plans_health_record_id_fkey
  foreign key (health_record_id) references public.health_records(id) on delete set null;

alter table public.urgent_help_notes
  add constraint urgent_help_notes_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade;

alter table public.user_files
  add constraint user_files_user_id_fkey
  foreign key (user_id) references public.users(id) on delete cascade;

-- ── 11. Row Level Security ──────────────────────────────────────────
-- The backend connects as the table owner (service role) and therefore
-- bypasses RLS; these policies exist for defence in depth against any client
-- that reaches PostgREST directly.
alter table public.users           enable row level security;
alter table public.meals           enable row level security;
alter table public.allergens       enable row level security;
alter table public.meal_allergens  enable row level security;
alter table public.health_records  enable row level security;
alter table public.consents        enable row level security;
alter table public.audit_logs      enable row level security;

-- Identity mirror: backend-only, no client access.
revoke all on public.users from anon, authenticated;

-- Catalog: readable by authenticated users; writes only through the backend.
drop policy if exists p_meals_read on public.meals;
create policy p_meals_read on public.meals
  for select to authenticated using (true);
drop policy if exists p_allergens_read on public.allergens;
create policy p_allergens_read on public.allergens
  for select to authenticated using (true);
drop policy if exists p_meal_allergens_read on public.meal_allergens;
create policy p_meal_allergens_read on public.meal_allergens
  for select to authenticated using (true);

-- User-owned tables: full self-service with WITH CHECK on writes.
do $$
declare
  t text;
begin
  foreach t in array array['health_records', 'consents'] loop
    execute format('drop policy if exists p_%I_self_select on public.%I', t, t);
    execute format($f$create policy p_%I_self_select on public.%I
      for select to authenticated using (user_id = auth.uid())$f$, t, t);
    execute format('drop policy if exists p_%I_self_insert on public.%I', t, t);
    execute format($f$create policy p_%I_self_insert on public.%I
      for insert to authenticated with check (user_id = auth.uid())$f$, t, t);
    execute format('drop policy if exists p_%I_self_update on public.%I', t, t);
    execute format($f$create policy p_%I_self_update on public.%I
      for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid())$f$, t, t);
    execute format('drop policy if exists p_%I_self_delete on public.%I', t, t);
    execute format($f$create policy p_%I_self_delete on public.%I
      for delete to authenticated using (user_id = auth.uid())$f$, t, t);
  end loop;
end $$;

-- audit_logs: append-only for users.
drop policy if exists p_audit_self_select on public.audit_logs;
create policy p_audit_self_select on public.audit_logs
  for select to authenticated using (user_id = auth.uid());
drop policy if exists p_audit_self_insert on public.audit_logs;
create policy p_audit_self_insert on public.audit_logs
  for insert to authenticated with check (user_id = auth.uid());

-- ── 12. Indexes/statistics refresh for the planner ──────────────────
analyze public.users;
analyze public.meals;
analyze public.allergens;
analyze public.meal_allergens;
analyze public.health_records;
