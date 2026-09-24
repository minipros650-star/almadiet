"""RLS posture for the content review workflow.

Two layers of proof:

  1. Structural — the Supabase migration is parsed and asserted to keep
     unreviewed content away from ordinary readers, to keep the governance
     tables client-inaccessible, and to mirror the ORM models exactly.
  2. Live (opt-in) — a direct PostgREST request proves the deployed database
     refuses to hand out unreviewed meals. Skipped unless the Supabase
     credentials are supplied, because CI has no database:

         SUPABASE_URL=https://<ref>.supabase.co \
         SUPABASE_ANON_KEY=<publishable key> \
         SUPABASE_NON_STAFF_JWT=<a valid token for an ordinary user> \
             python -m pytest tests/test_content_rls_posture.py -v
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
# Named after the version Supabase recorded when the migration was applied, so
# the file and the live migration history stay in step.
MIGRATION = (
    PROJECT_ROOT / "supabase" / "migrations" / "20260924183610_content_review_workflow.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(sql: str) -> str:
    """Whitespace-collapsed, lowercased SQL for robust matching."""
    return re.sub(r"\s+", " ", sql).lower()


def _create_table_block(sql: str, table: str) -> str:
    match = re.search(
        rf"create table if not exists public\.{table}\s*\((.*?)\n\);",
        sql,
        flags=re.DOTALL,
    )
    assert match, f"no create table block found for {table}"
    return match.group(1)


# ── governance tables are client-inaccessible ─────────────────────────────


def test_migration_exists():
    assert MIGRATION.exists(), f"missing migration {MIGRATION}"


def test_rls_enabled_on_governance_tables(flat):
    for table in ("content_role_grants", "content_transitions"):
        assert f"alter table public.{table} enable row level security" in flat


def test_no_client_policies_exist_on_governance_tables(flat):
    """RLS on with no policies is default-deny for anon/authenticated."""
    for table in ("content_role_grants", "content_transitions"):
        assert not re.search(
            rf"create policy \w+ on public\.{table}", flat
        ), f"{table} must not carry a client policy"


def test_client_privileges_are_revoked(flat):
    for table in ("content_role_grants", "content_transitions"):
        assert f"revoke all on public.{table} from anon, authenticated" in flat


# ── the role helper must be able to read a deny-all table ─────────────────


def test_role_helper_is_security_definer_with_empty_search_path(flat):
    assert "security definer" in flat
    assert "set search_path = ''" in flat, (
        "SECURITY DEFINER with a caller-controlled search_path is a privilege "
        "escalation risk"
    )
    assert "create or replace function public.has_content_role(uid uuid, roles text[])" in flat


def test_role_helper_execute_is_granted_only_to_authenticated(flat):
    assert "revoke all on function public.has_content_role(uuid, text[]) from public" in flat
    assert "grant execute on function public.has_content_role(uuid, text[]) to authenticated" in flat
    # Supabase's default privileges grant EXECUTE on new `public` functions to
    # anon EXPLICITLY, so revoking from PUBLIC alone leaves an unauthenticated
    # role-membership oracle at /rest/v1/rpc/has_content_role. This was a real
    # finding from Supabase's security advisors after the first apply.
    assert (
        "revoke execute on function public.has_content_role(uuid, text[]) from anon" in flat
    ), "anon must not be able to execute the role lookup"


# ── unreviewed meals must not leak ────────────────────────────────────────


def _policy_body(flat: str, policy: str, table: str) -> str:
    """The body of the CREATE POLICY for this table (not the DROP)."""
    match = re.search(
        rf"create policy {policy} on public\.{table}(.*?);", flat, flags=re.DOTALL
    )
    assert match, f"no create policy {policy} on {table}"
    return match.group(1)


def test_meals_policy_is_no_longer_permissive(flat):
    """p_meals_read used to be USING (true): every meal to every reader."""
    block = _policy_body(flat, "p_meals_read", "meals")
    assert "using ( true )" not in block
    assert "content_status = 'published'" in block
    assert "public.has_content_role(auth.uid(), array['reviewer','publisher'])" in block
    assert "to authenticated" in block


def test_meal_allergens_policy_is_scoped_to_visible_meals(flat):
    block = _policy_body(flat, "p_meal_allergens_read", "meal_allergens")
    assert "from public.meals m" in block
    assert "m.content_status = 'published'" in block
    assert "has_content_role" in block


def test_old_policies_are_dropped_first(flat):
    for policy in ("p_meals_read on public.meals", "p_meal_allergens_read on public.meal_allergens"):
        assert f"drop policy if exists {policy}" in flat


# ── consent idempotency ───────────────────────────────────────────────────


def test_consent_unique_index_present(flat):
    assert "create unique index if not exists uq_consents_user_version" in flat
    assert "on public.consents (user_id, consent_version)" in flat


def test_migration_aborts_on_duplicate_consents(flat):
    """It must refuse rather than delete consent records."""
    assert "raise exception" in flat
    assert "having count(*) > 1" in flat
    assert "delete from public.consents" not in flat


# ── schema parity with the ORM ────────────────────────────────────────────


def test_sql_mirrors_orm_models(sql):
    from app.models.content_role import ContentRoleGrant
    from app.models.content_transition import ContentTransition

    for model, table in (
        (ContentRoleGrant, "content_role_grants"),
        (ContentTransition, "content_transitions"),
    ):
        block = _create_table_block(sql, table)
        for column in model.__table__.columns.keys():
            assert column in block, f"{table}.{column} is missing from the migration"


def test_orm_constraints_are_mirrored(sql):
    block = _create_table_block(sql, "content_role_grants")
    assert "uq_content_role_grants_user_role" in block
    assert "role in ('REVIEWER','PUBLISHER')" in block

    transitions = _create_table_block(sql, "content_transitions")
    for status in ("DRAFT", "REVIEW_REQUIRED", "REVIEWED", "PUBLISHED", "RETIRED"):
        assert status in transitions


def test_orm_consent_model_declares_the_unique_constraint():
    from app.models.consent import Consent

    names = {c.name for c in Consent.__table__.constraints}
    assert "uq_consents_user_version" in names


# ── alembic head ──────────────────────────────────────────────────────────


def test_alembic_head_is_the_workflow_migration():
    versions_dir = BACKEND_DIR / "alembic" / "versions"
    revisions, down_revisions = set(), set()
    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        revision = re.search(r'^revision: str = "([^"]+)"', text, flags=re.MULTILINE)
        if revision:
            revisions.add(revision.group(1))
        down = re.search(r'^down_revision: Union\[str, None\] = "([^"]+)"', text, flags=re.MULTILINE)
        if down:
            down_revisions.add(down.group(1))

    heads = revisions - down_revisions
    assert heads == {"0006"}, f"expected a single head 0006, found {heads}"


# ── live direct-PostgREST proof (opt-in) ──────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_PUBLISHABLE_KEY") or ""
NON_STAFF_JWT = os.getenv("SUPABASE_NON_STAFF_JWT", "")

live = pytest.mark.skipif(
    not (SUPABASE_URL and ANON_KEY),
    reason="set SUPABASE_URL and SUPABASE_ANON_KEY to run the live PostgREST checks",
)


def _rest_get(path: str, token: str | None):
    import httpx

    headers = {"apikey": ANON_KEY}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.get(f"{SUPABASE_URL}/rest/v1/{path}", headers=headers, timeout=30)


@live
def test_postgrest_anonymous_cannot_read_meals():
    """No anon policy on meals: the request must return nothing at all."""
    resp = _rest_get("meals?select=id,content_status", token=None)
    assert resp.status_code < 500, resp.text
    if resp.status_code == 200:
        assert resp.json() == [], "anon read returned meal rows"


@live
def test_postgrest_ordinary_user_sees_only_published_meals():
    """Real direct-PostgREST proof that unreviewed content does not leak."""
    if not NON_STAFF_JWT:
        pytest.skip("set SUPABASE_NON_STAFF_JWT for an ordinary-user JWT")
    resp = _rest_get("meals?select=content_status", token=NON_STAFF_JWT)
    assert resp.status_code == 200, resp.text
    statuses = {row.get("content_status") for row in resp.json()}
    assert statuses <= {"PUBLISHED"}, f"unreviewed meals leaked through PostgREST: {statuses}"


@live
def test_postgrest_ordinary_user_cannot_read_role_grants():
    token = NON_STAFF_JWT or None
    resp = _rest_get("content_role_grants?select=role", token=token)
    assert resp.status_code in (401, 403, 404) or resp.json() == [], resp.text
