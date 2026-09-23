-- AlmaDiet — Supabase migration 0002: Storage policies + allergen taxonomy

-- ── Allergen taxonomy (values mirror backend/app/domain/allergens.py) ──
insert into public.allergens (code, label) values
  ('peanut','Peanut'),
  ('tree_nut','Tree nuts'),
  ('milk','Milk / dairy'),
  ('egg','Egg'),
  ('wheat_gluten','Wheat / gluten'),
  ('soy','Soy'),
  ('fish','Fish'),
  ('shellfish','Shellfish'),
  ('sesame','Sesame'),
  ('mustard','Mustard'),
  ('sulfite','Sulfites'),
  ('other','Other allergen')
on conflict (code) do nothing;

-- ── Storage RLS: users may manage only their own prefix in user-private ──
-- Objects are stored at {user_id}/... so ownership is path-derivable.
-- The backend (service role) handles all writes with validation + audit;
-- these policies govern any direct client access.

-- meal-images: world-readable, but ONLY the backend (service role) writes
-- (reviewed/approved catalog imagery; no user content here).
drop policy if exists "meal-images public read" on storage.objects;
create policy "meal-images public read" on storage.objects
  for select to anon, authenticated using (bucket_id = 'meal-images');

-- user-private: nobody reads via anon/authenticated except own prefix.
drop policy if exists "user-private own read" on storage.objects;
create policy "user-private own read" on storage.objects
  for select to authenticated
  using (bucket_id = 'user-private' and (storage.foldername(name))[1] = auth.uid()::text);

-- Writes go through FastAPI (service role). If ever opened to clients,
-- these WITH CHECK policies still confine users to their own prefix.
drop policy if exists "user-private own insert" on storage.objects;
create policy "user-private own insert" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'user-private' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists "user-private own update" on storage.objects;
create policy "user-private own update" on storage.objects
  for update to authenticated
  using (bucket_id = 'user-private' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'user-private' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists "user-private own delete" on storage.objects;
create policy "user-private own delete" on storage.objects
  for delete to authenticated
  using (bucket_id = 'user-private' and (storage.foldername(name))[1] = auth.uid()::text);

-- Explicit denial surface for tests: anon can NEVER read user-private
-- (no anon policy exists — RLS default-deny does this; nothing to add).
