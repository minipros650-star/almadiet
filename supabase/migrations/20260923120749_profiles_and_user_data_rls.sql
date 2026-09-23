-- AlmaDiet — Supabase migration 0001: profiles + user data + catalog + RLS
-- Architecture: Flutter → FastAPI (Vercel) → Supabase Postgres.
--
-- Safety rules encoded here:
--   * profiles.id == auth.users.id — one identity, no orphan app user table.
--   * RLS on EVERY user-owned table; policies use auth.uid() with WITH CHECK
--     on INSERT/UPDATE so a signed-in user can only touch their own rows.
--   * Catalog (meals, allergens, meal_allergens) is read-only for authenticated
--     users; writes happen via the backend's direct connection (owner), never from clients.
--   * Health data lives only in user-scoped tables — never public.

-- ── 0. Rollback point: preserve any legacy tables under a reserved name ──
do $$
declare t text;
begin
  foreach t in array array['users','meals','health_records','emergency_records','meal_images','diet_plans'] loop
    if exists (select 1 from information_schema.tables
               where table_schema='public' and table_name = t)
       and not exists (select 1 from information_schema.tables
               where table_schema='public' and table_name = 'legacy_' || t) then
      execute format('alter table public.%I rename to legacy_%I', t, t);
    end if;
  end loop;
end $$;

-- ── 1. profiles — the ONLY identity table, keyed by auth.users.id ────────
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null unique,
  name text not null default '',
  phone text,
  region text not null default 'kerala'
    constraint ck_profiles_region check (region in ('kerala','tamilnadu','karnataka','andhra')),
  language text not null default 'en'
    constraint ck_profiles_language check (language in ('en','ml','ta','kn','te')),
  auth_provider text not null default 'email'
    constraint ck_profiles_provider check (auth_provider in ('google','email')),
  lmp_date date,
  due_date date,
  age integer constraint ck_profiles_age check (age is null or age between 14 and 55),
  height_cm numeric constraint ck_profiles_height check (height_cm is null or height_cm between 100 and 250),
  pre_pregnancy_weight_kg numeric
    constraint ck_profiles_prepreg_weight check (pre_pregnancy_weight_kg is null or pre_pregnancy_weight_kg between 30 and 200),
  pre_pregnancy_bmi numeric
    constraint ck_profiles_bmi check (pre_pregnancy_bmi is null or pre_pregnancy_bmi between 10 and 60),
  gestational_week integer constraint ck_profiles_week check (gestational_week is null or gestational_week between 1 and 42),
  trimester integer constraint ck_profiles_trimester check (trimester is null or trimester between 1 and 3),
  profile_complete boolean not null default false,
  declared_allergies jsonb,
  dietary_preference text constraint ck_profiles_diet check (dietary_preference is null or dietary_preference in ('veg','nonveg','eggetarian')),
  disliked_ingredients jsonb not null default '[]'::jsonb,
  cooking_time_preference text constraint ck_profiles_cook check (cooking_time_preference is null or cooking_time_preference in ('quick','moderate','relaxed')),
  budget_preference text constraint ck_profiles_budget check (budget_preference is null or budget_preference in ('low','medium','high')),
  avatar_path text,
  clinician_review_required boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_profiles_email on public.profiles (email);

create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$
begin new.updated_at = now(); return new; end $$;
drop trigger if exists trg_profiles_touch on public.profiles;
create trigger trg_profiles_touch before update on public.profiles
for each row execute function public.touch_updated_at();

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email, name, auth_provider)
  values (
    new.id,
    lower(coalesce(new.email, '')),
    coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', ''),
    coalesce(new.raw_user_meta_data->>'provider', 'email')
  )
  on conflict (id) do nothing;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

-- ── 2. Catalog (read-only for users) ─────────────────────────────────
create table if not exists public.allergens (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  label text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.meals (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  description text,
  region text not null default 'kerala',
  meal_type text not null default 'Lunch',
  dietary_preference text not null default 'veg',
  calories numeric not null default 0 constraint ck_meals_cal check (calories between 0 and 3000),
  protein_g numeric not null default 0,
  iron_mg numeric not null default 0,
  calcium_mg numeric not null default 0,
  folate_mcg numeric not null default 0,
  preparation_time_minutes integer,
  ingredients jsonb not null default '[]'::jsonb,
  instructions text,
  image_path text,
  image_source text not null default 'storage'
    constraint ck_meals_imgsrc check (image_source in ('storage','external','none')),
  content_status text not null default 'REVIEW_REQUIRED'
    constraint ck_meals_status check (content_status in ('DRAFT','REVIEW_REQUIRED','REVIEWED','PUBLISHED','RETIRED')),
  source text,
  source_url text,
  evidence_version text,
  catalog_version text not null default '1',
  approved_by text,
  approved_at timestamptz,
  retired_at timestamptz,
  clinician_review_required boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_meals_status on public.meals (content_status);
create index if not exists idx_meals_type on public.meals (meal_type);

create table if not exists public.meal_allergens (
  meal_id uuid not null references public.meals(id) on delete cascade,
  allergen_id uuid not null references public.allergens(id) on delete cascade,
  primary key (meal_id, allergen_id)
);
create index if not exists idx_meal_allergens_allergen on public.meal_allergens (allergen_id);

-- ── 3. User-owned data ───────────────────────────────────────────────
create table if not exists public.health_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  week_number integer constraint ck_hr_week check (week_number is null or week_number between 1 and 42),
  current_weight_kg numeric constraint ck_hr_weight check (current_weight_kg is null or current_weight_kg between 30 and 200),
  blood_pressure_sys numeric constraint ck_hr_bps check (blood_pressure_sys is null or blood_pressure_sys between 60 and 250),
  blood_pressure_dia numeric constraint ck_hr_bpd check (blood_pressure_dia is null or blood_pressure_dia between 40 and 150),
  hemoglobin numeric constraint ck_hr_hb check (hemoglobin is null or hemoglobin between 3 and 20),
  blood_sugar_fasting numeric constraint ck_hr_bs check (blood_sugar_fasting is null or blood_sugar_fasting between 20 and 600),
  allergies jsonb not null default '[]'::jsonb,
  medical_conditions jsonb not null default '[]'::jsonb,
  is_vegetarian boolean,
  dietary_preference text,
  recorded_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index if not exists idx_hr_user on public.health_records (user_id, recorded_at desc);

create table if not exists public.diet_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  health_record_id uuid references public.health_records(id) on delete set null,
  trimester integer not null default 2 constraint ck_dp_tri check (trimester between 1 and 3),
  week_number integer not null default 12 constraint ck_dp_week check (week_number between 1 and 42),
  days jsonb not null default '[]'::jsonb,
  target_calories numeric not null default 0,
  target_protein numeric not null default 0,
  target_iron numeric not null default 0,
  target_calcium numeric not null default 0,
  dietary_alerts jsonb not null default '[]'::jsonb,
  exclusions_applied jsonb not null default '{}'::jsonb,
  user_corrections jsonb not null default '[]'::jsonb,
  plan_start date not null,
  plan_end date not null,
  policy_version text,
  catalog_version text,
  ranking_version text,
  created_at timestamptz not null default now(),
  constraint ck_dp_dates check (plan_end >= plan_start)
);
create index if not exists idx_dp_user on public.diet_plans (user_id, created_at desc);

create table if not exists public.meal_favorites (
  user_id uuid not null references public.profiles(id) on delete cascade,
  meal_id uuid not null references public.meals(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, meal_id)
);

create table if not exists public.consents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  consent_version text not null,
  accepted_at timestamptz not null default now()
);
create index if not exists idx_consents_user on public.consents (user_id, accepted_at desc);

create table if not exists public.urgent_notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  note text not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_urgent_user on public.urgent_notes (user_id, created_at desc);

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete set null,
  event text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_audit_user on public.audit_logs (user_id, created_at desc);

create table if not exists public.user_files (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  bucket text not null constraint ck_uf_bucket check (bucket in ('user-private','meal-images')),
  object_path text not null,
  content_type text not null,
  size_bytes bigint not null,
  created_at timestamptz not null default now(),
  unique (bucket, object_path)
);
create index if not exists idx_user_files_user on public.user_files (user_id);

-- ── 4. Row Level Security ────────────────────────────────────────────
alter table public.profiles        enable row level security;
alter table public.allergens       enable row level security;
alter table public.meals           enable row level security;
alter table public.meal_allergens  enable row level security;
alter table public.health_records  enable row level security;
alter table public.diet_plans      enable row level security;
alter table public.meal_favorites  enable row level security;
alter table public.consents        enable row level security;
alter table public.urgent_notes    enable row level security;
alter table public.audit_logs      enable row level security;
alter table public.user_files      enable row level security;

-- profiles: strict self-service.
drop policy if exists p_profiles_self_select on public.profiles;
create policy p_profiles_self_select on public.profiles
  for select to authenticated using (id = auth.uid());
drop policy if exists p_profiles_self_insert on public.profiles;
create policy p_profiles_self_insert on public.profiles
  for insert to authenticated with check (id = auth.uid());
drop policy if exists p_profiles_self_update on public.profiles;
create policy p_profiles_self_update on public.profiles
  for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

-- User-owned tables: full self CRUD with WITH CHECK on writes.
do $$
declare t text;
begin
  foreach t in array array['health_records','diet_plans','consents','urgent_notes'] loop
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

-- meal_favorites: composite key.
drop policy if exists p_fav_self_select on public.meal_favorites;
create policy p_fav_self_select on public.meal_favorites
  for select to authenticated using (user_id = auth.uid());
drop policy if exists p_fav_self_insert on public.meal_favorites;
create policy p_fav_self_insert on public.meal_favorites
  for insert to authenticated with check (user_id = auth.uid());
drop policy if exists p_fav_self_delete on public.meal_favorites;
create policy p_fav_self_delete on public.meal_favorites
  for delete to authenticated using (user_id = auth.uid());

-- user_files: read/insert own metadata only.
drop policy if exists p_uf_self_select on public.user_files;
create policy p_uf_self_select on public.user_files
  for select to authenticated using (user_id = auth.uid());
drop policy if exists p_uf_self_insert on public.user_files;
create policy p_uf_self_insert on public.user_files
  for insert to authenticated with check (user_id = auth.uid());

-- audit_logs: append-only for users.
drop policy if exists p_audit_self_select on public.audit_logs;
create policy p_audit_self_select on public.audit_logs
  for select to authenticated using (user_id = auth.uid());
drop policy if exists p_audit_self_insert on public.audit_logs;
create policy p_audit_self_insert on public.audit_logs
  for insert to authenticated with check (user_id = auth.uid());

-- Catalog: readable by authenticated users; NO write policies for
-- authenticated/anon — content changes only through the backend (owner role).
drop policy if exists p_meals_read on public.meals;
create policy p_meals_read on public.meals
  for select to authenticated using (true);
drop policy if exists p_allergens_read on public.allergens;
create policy p_allergens_read on public.allergens
  for select to authenticated using (true);
drop policy if exists p_meal_allergens_read on public.meal_allergens;
create policy p_meal_allergens_read on public.meal_allergens
  for select to authenticated using (true);
