-- AlmaDiet — Supabase migration 0003: security hardening per linter

-- legacy_* tables are empty rollback artifacts; block all client access.
do $$
declare t text;
begin
  foreach t in array array['legacy_users','legacy_meals','legacy_health_records','legacy_emergency_records','legacy_meal_images','legacy_diet_plans'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
  end loop;
end $$;

-- Functions: fixed search_path; no direct RPC by anon/authenticated.
create or replace function public.touch_updated_at() returns trigger
language plpgsql
set search_path = ''
as $$
begin new.updated_at = now(); return new; end $$;

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer
set search_path = ''
as $$
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

revoke execute on function public.handle_new_user() from anon, authenticated, public;
revoke execute on function public.touch_updated_at() from anon, authenticated, public;
