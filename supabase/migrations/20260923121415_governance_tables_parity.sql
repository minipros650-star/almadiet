-- AlmaDiet — Supabase migration 0004: governance + support tables (schema parity)
-- DDL mirrors the SQLAlchemy models (backend/app/models) so the FastAPI
-- policy gate and reviewer endpoints work unchanged against Supabase.

create table if not exists public.evidence_sources (
  id uuid primary key default gen_random_uuid(),
  url varchar(1000) not null,
  domain varchar(255) not null,
  publisher varchar(255),
  title varchar(500),
  published_on date,
  reviewed_on date,
  retrieved_at timestamptz not null default now(),
  content_hash varchar(64) not null unique,
  supporting_excerpt text,
  topic_tags jsonb,
  status varchar(32) not null,
  rejection_reason varchar(255)
);
create index if not exists ix_evidence_sources_domain on public.evidence_sources (domain);
create index if not exists ix_evidence_sources_status on public.evidence_sources (status);

create table if not exists public.evidence_claims (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.evidence_sources(id) on delete cascade,
  claim_text text not null,
  topic_tags jsonb,
  content_hash varchar(64) not null unique,
  status varchar(32) not null,
  created_at timestamptz not null default now()
);
create index if not exists ix_evidence_claims_status on public.evidence_claims (status);
create index if not exists ix_evidence_claims_source on public.evidence_claims (source_id);

create table if not exists public.clinical_review_decisions (
  id uuid primary key default gen_random_uuid(),
  claim_id uuid not null references public.evidence_claims(id) on delete cascade,
  decision varchar(16) not null,
  reviewed_by varchar(255) not null,
  reviewed_at timestamptz not null default now(),
  rationale text,
  superseded_by_id uuid references public.clinical_review_decisions(id) on delete set null
);
create index if not exists ix_crd_claim on public.clinical_review_decisions (claim_id, reviewed_at);

create table if not exists public.safety_policy_versions (
  id uuid primary key default gen_random_uuid(),
  policy_id varchar(100) not null,
  version varchar(32) not null,
  payload jsonb not null,
  status varchar(16) not null,
  approved_by varchar(255),
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  unique (policy_id, version)
);
create index if not exists ix_safety_policy_status on public.safety_policy_versions (status);

create table if not exists public.model_registry (
  id uuid primary key default gen_random_uuid(),
  model_name varchar(100) not null,
  model_version varchar(32) not null,
  feature_flag varchar(100) not null,
  status varchar(16) not null,
  policy_version varchar(32),
  catalog_version varchar(32),
  artifact_uri varchar(500),
  feature_definition_version varchar(32),
  dataset_version varchar(32),
  random_seed integer,
  approved_by varchar(255),
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  unique (model_name, model_version)
);
create index if not exists ix_model_registry_status on public.model_registry (status);

create table if not exists public.model_evaluation_runs (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references public.model_registry(id) on delete cascade,
  dataset_version varchar(32) not null,
  feature_definition_version varchar(32) not null,
  split_seed integer not null,
  metrics jsonb not null,
  beats_baseline boolean not null,
  subgroup_checks_pass boolean not null,
  result varchar(16) not null,
  notes text,
  created_at timestamptz not null default now(),
  unique (model_id, dataset_version, split_seed)
);
create index if not exists ix_eval_runs_model on public.model_evaluation_runs (model_id, created_at);

create table if not exists public.nutrition_policy_approvals (
  id uuid primary key default gen_random_uuid(),
  policy_id varchar(100) not null,
  policy_version varchar(32) not null,
  approved_by varchar(255) not null,
  approved_at timestamptz not null default now(),
  notes text,
  unique (policy_id, policy_version)
);
create index if not exists ix_nutrition_policy_approvals_policy_id on public.nutrition_policy_approvals (policy_id);

create table if not exists public.content_versions (
  id uuid primary key default gen_random_uuid(),
  meal_id uuid not null references public.meals(id) on delete cascade,
  version integer not null,
  payload jsonb,
  change_note varchar(500),
  reviewer varchar(255),
  status varchar(20) not null,
  created_at timestamptz not null default now()
);
create index if not exists ix_content_versions_meal on public.content_versions (meal_id, version);

create table if not exists public.meal_images (
  id uuid primary key default gen_random_uuid(),
  meal_id uuid not null references public.meals(id) on delete cascade,
  image_url varchar(500) not null,
  prompt_used text,
  generated_at timestamptz not null default now()
);
create index if not exists ix_meal_images_meal_id on public.meal_images (meal_id);

create table if not exists public.refresh_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  token_hash varchar(64) not null unique,
  family_id uuid not null,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists ix_refresh_tokens_user on public.refresh_tokens (user_id);
create index if not exists ix_refresh_tokens_family on public.refresh_tokens (family_id);

create table if not exists public.urgent_help_notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  note_text text,
  observed_symptoms jsonb,
  created_at timestamptz not null default now()
);
create index if not exists ix_urgent_help_notes_user_id on public.urgent_help_notes (user_id);

-- RLS on governance tables: readable only via the backend service
-- connection; no client policies (default-deny for anon/authenticated).
alter table public.evidence_sources          enable row level security;
alter table public.evidence_claims           enable row level security;
alter table public.clinical_review_decisions enable row level security;
alter table public.safety_policy_versions    enable row level security;
alter table public.model_registry            enable row level security;
alter table public.model_evaluation_runs     enable row level security;
alter table public.nutrition_policy_approvals enable row level security;
alter table public.content_versions          enable row level security;
alter table public.meal_images               enable row level security;
alter table public.refresh_tokens            enable row level security;
alter table public.urgent_help_notes         enable row level security;

-- urgent_help_notes is USER-OWNED: add self-service policies like the others.
drop policy if exists p_urgent_help_notes_self_select on public.urgent_help_notes;
create policy p_urgent_help_notes_self_select on public.urgent_help_notes
  for select to authenticated using (user_id = auth.uid());
drop policy if exists p_urgent_help_notes_self_insert on public.urgent_help_notes;
create policy p_urgent_help_notes_self_insert on public.urgent_help_notes
  for insert to authenticated with check (user_id = auth.uid());
drop policy if exists p_urgent_help_notes_self_update on public.urgent_help_notes;
create policy p_urgent_help_notes_self_update on public.urgent_help_notes
  for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists p_urgent_help_notes_self_delete on public.urgent_help_notes;
create policy p_urgent_help_notes_self_delete on public.urgent_help_notes
  for delete to authenticated using (user_id = auth.uid());

-- meals/audit reference: allow the backend owner role full access is implicit;
-- grants for the service connection are handled by the direct Postgres connection.
