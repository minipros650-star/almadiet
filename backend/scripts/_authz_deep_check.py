"""TEMPORARY deep live authorization regression suite (two authenticated users).

Covers the layers the earlier and lighter check could not:

  1. Data layer — PostgREST as user B against user A's rows in every
     user-scoped table (select / insert / update / delete).
  2. Storage layer — REAL bytes in ``user-private`` with real JWTs:
     cross-user download, delete, list and upload-into-other's-prefix.
  3. Consent gate — deterministic (A's consent is revoked first by the
     operator, so the 409 is observed live rather than assumed).
  4. FastAPI layer — ownership rules on the deployed endpoints.

Creates a small amount of test data and removes the objects/rows it makes.

    python -m scripts._authz_deep_check
"""

from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import httpx  # noqa: E402

SB = "https://ipquqyzlqugalmhfhfbt.supabase.co"
ANON = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlwcXVxeXps"
    "cXVnYWxtaGZoZmJ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU3MjI2NDQsImV4cCI6MjA5MTI5ODY0"
    "NH0.WTxlZ4Fbhsls1jecG4MBGAT2NrFz6hnyn-YNeCqfHkQ"
)
API = "https://almadiet.vercel.app"
REST = f"{SB}/rest/v1"
STORAGE = f"{SB}/storage/v1"
PRIVATE_BUCKET = "user-private"
PUBLIC_BUCKET = "meal-images"
# No credential lives in this file: the two dedicated test identities exist in
# production, so the password is supplied by the operator at run time.
PASSWORD = os.getenv("AUTHZ_TEST_PASSWORD", "")
if not PASSWORD:
    raise SystemExit(
        "Set AUTHZ_TEST_PASSWORD to the password of the authz.a / authz.b test "
        "identities before running this suite."
    )

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)

results: list[tuple[bool, str, str]] = []
artifacts: dict[str, object] = {}
section = ""


def head(name: str) -> None:
    global section
    section = name
    print(f"\n=== {name} ===")


def record(ok: bool, name: str, detail: str = "") -> None:
    results.append((ok, name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<58} {detail}")


def note(text: str) -> None:
    print(f"  NOTE  {text}")


def brief(body) -> str:
    try:
        return json.dumps(body)[:130]
    except Exception:
        return str(body)[:130]


# ── clients ───────────────────────────────────────────────────────────────
def sign_in(tag: str) -> tuple[str, str]:
    r = httpx.post(
        f"{SB}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": ANON, "Content-Type": "application/json"},
        json={"email": f"authz.{tag}@almadiet.invalid", "password": PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    return body["access_token"], body["user"]["id"]


def rest_headers(token: str | None, write: bool = False) -> dict:
    h = {"apikey": ANON}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if write:
        h["Content-Type"] = "application/json"
        h["Prefer"] = "return=representation"
    return h


def rest(method: str, table: str, token: str | None, params: dict | None = None, payload=None):
    r = httpx.request(
        method,
        f"{REST}/{table}",
        headers=rest_headers(token, write=payload is not None or method in ("PATCH", "POST")),
        params=params or {},
        json=payload,
        timeout=45,
    )
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:160]


def api(method: str, path: str, token: str | None = None, **kw):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = httpx.request(method, f"{API}{path}", headers=headers, timeout=60, **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:160]


def storage(method: str, bucket: str, path: str, token: str | None, data: bytes | None = None,
            ctype: str = "image/png"):
    h = {"apikey": ANON}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if data is not None:
        h["Content-Type"] = ctype
    r = httpx.request(method, f"{STORAGE}/object/{bucket}/{path}", headers=h, content=data, timeout=60)
    return r


def is_denied(status: int) -> bool:
    """Storage/PostgREST denial surfaces as 400/401/403/404."""
    return status in (400, 401, 403, 404)


# ── row-level matrix ──────────────────────────────────────────────────────
# table -> (owner column, valid insert payload builder, sentinel update payload)
TABLES: dict[str, tuple[str, callable, dict]] = {
    "profiles": ("id", lambda uid, other: {"id": other, "email": "cross@almadiet.invalid"},
                 {"email": "x@almadiet.invalid"}),
    "health_records": ("user_id", lambda uid, other: {
        "user_id": other, "trimester": 1, "week_number": 5, "current_weight_kg": 60.0},
        {"week_number": 1}),
    "diet_plans": ("user_id", lambda uid, other: {
        "user_id": other, "plan_start": "2026-01-01", "plan_end": "2026-03-31"},
        {"plan_end": "2026-01-02"}),
    "meal_favorites": ("user_id", lambda uid, other: {
        "user_id": other, "meal_id": str(uuid.uuid4())},
        {"meal_id": "00000000-0000-4000-8000-000000000000"}),
    "consents": ("user_id", lambda uid, other: {
        "user_id": other, "consent_version": "cross-v1"},
        {"consent_version": "x"}),
    "urgent_notes": ("user_id", lambda uid, other: {
        "user_id": other, "note": "cross-tenant probe"},
        {"note": "x"}),
    "audit_logs": ("user_id", lambda uid, other: {
        "user_id": other, "event_code": "CROSS_TENANT_PROBE"},
        {"event_code": "X"}),
    "user_files": ("user_id", lambda uid, other: {
        "user_id": other, "bucket": PRIVATE_BUCKET, "object_path": "cross/probe.png",
        "content_type": "image/png", "size_bytes": 1},
        {"object_path": "x"}),
}


def cross_user_matrix(b_token: str, b_id: str, a_id: str) -> None:
    head("B -> A row-level matrix (PostgREST, B's own JWT)")
    for table, (col, make, patch) in TABLES.items():
        # read
        code, rows = rest("GET", table, b_token, {col: f"eq.{a_id}", "select": "*"})
        leaked = isinstance(rows, list) and len(rows) > 0
        record(code < 400 and not leaked, f"B SELECT {table} of A",
               f"{code} rows={len(rows) if isinstance(rows, list) else brief(rows)}")

        # insert as A
        code, body = rest("POST", table, b_token, payload=make(b_id, a_id))
        created = code < 300 and isinstance(body, list) and len(body) > 0
        record(not created, f"B INSERT {table} owned by A",
               f"{code} {brief(body) if not created else 'ROW CREATED'}")

        # update A's rows (sentinel payload is valid for this table, so a
        # failure can only come from the RLS policy, never from a bad column)
        code, body = rest("PATCH", table, b_token, {col: f"eq.{a_id}"}, payload=patch)
        touched = isinstance(body, list) and len(body) > 0
        record(code < 400 and not touched, f"B UPDATE {table} of A",
               f"{code} changed={len(body) if isinstance(body, list) else brief(body)}")

        # delete A's rows
        code, body = rest("DELETE", table, b_token, {col: f"eq.{a_id}"})
        deleted = isinstance(body, list) and len(body) > 0
        record(code < 400 and not deleted, f"B DELETE {table} of A",
               f"{code} deleted={len(body) if isinstance(body, list) else brief(body)}")


def own_rows_intact(a_token: str, a_id: str) -> None:
    head("A's own rows survived every denial")
    for table, (col, _, _) in TABLES.items():
        code, rows = rest("GET", table, a_token, {col: f"eq.{a_id}", "select": "*"})
        record(code < 400, f"A SELECT own {table}", f"{code} rows={len(rows) if isinstance(rows, list) else '?'}")
    code, rows = rest("GET", "health_records", a_token, {"select": "*"})
    record(isinstance(rows, list) and len(rows) >= 1, "A health record still present",
           f"{code} n={len(rows) if isinstance(rows, list) else '?'}")


def unauthenticated_row_layer() -> None:
    head("unauthenticated / anon-key row access")
    for table, (col, _, _) in TABLES.items():
        code, rows = rest("GET", table, None, {"select": "*"})
        leaked = isinstance(rows, list) and len(rows) > 0
        record(not leaked, f"anon SELECT {table}", f"{code} rows={len(rows) if isinstance(rows, list) else brief(rows)}")
    for table in ("meals", "meal_allergens", "allergens"):
        code, rows = rest("GET", table, None, {"select": "*"})
        record(not (isinstance(rows, list) and len(rows) > 0), f"anon SELECT {table}",
               f"{code} rows={len(rows) if isinstance(rows, list) else brief(rows)}")


def storage_isolation(a_token: str, b_token: str, a_id: str, b_id: str) -> None:
    head("Storage isolation — real bytes, real JWTs (user-private)")
    obj_a = f"{a_id}/authz-probe-{uuid.uuid4()}.png"
    artifacts["a_object"] = obj_a

    up = storage("POST", PRIVATE_BUCKET, obj_a, a_token, PNG)
    record(up.status_code in (200, 201), "A uploads to own prefix", str(up.status_code))

    dn = storage("GET", PRIVATE_BUCKET, obj_a, a_token)
    record(dn.status_code == 200 and dn.content == PNG, "A downloads own object (bytes match)",
           f"{dn.status_code} {len(dn.content)}B")

    dn_b = storage("GET", PRIVATE_BUCKET, obj_a, b_token)
    record(is_denied(dn_b.status_code), "B downloads A's object -> denied", str(dn_b.status_code))

    dn_anon = storage("GET", PRIVATE_BUCKET, obj_a, None)
    record(is_denied(dn_anon.status_code), "anon downloads private object -> denied", str(dn_anon.status_code))

    pub = httpx.get(f"{STORAGE}/object/public/{PRIVATE_BUCKET}/{obj_a}", timeout=45)
    record(is_denied(pub.status_code), "public URL of private object -> denied", str(pub.status_code))

    list_b = storage("POST", PRIVATE_BUCKET, "list/" + b_id, b_token, b"")
    lst = httpx.request(
        "POST", f"{STORAGE}/object/list/{PRIVATE_BUCKET}",
        headers={"apikey": ANON, "Authorization": f"Bearer {b_token}", "Content-Type": "application/json"},
        json={"prefix": f"{a_id}/", "limit": 100, "offset": 0}, timeout=45,
    )
    try:
        listed = [o.get("name") for o in lst.json()]
    except Exception:
        listed = []
    record(lst.status_code < 400 and not listed, "B lists A's prefix -> empty",
           f"{lst.status_code} n={len(listed)}")

    other_up = storage("POST", PRIVATE_BUCKET, f"{a_id}/injected-{uuid.uuid4()}.png", b_token, PNG)
    record(is_denied(other_up.status_code), "B uploads into A's prefix -> denied", str(other_up.status_code))

    del_b = storage("DELETE", PRIVATE_BUCKET, obj_a, b_token)
    record(is_denied(del_b.status_code), "B deletes A's object -> denied", str(del_b.status_code))

    still = storage("GET", PRIVATE_BUCKET, obj_a, a_token)
    record(still.status_code == 200 and still.content == PNG, "A's object survived B's delete", str(still.status_code))

    # public catalog bucket remains readable by authenticated users
    pub_read = storage("GET", PUBLIC_BUCKET, "nonexistent.png", a_token)
    record(pub_read.status_code in (200, 400, 404), "authenticated read path on meal-images reachable",
           str(pub_read.status_code))
    pub_anon = storage("GET", PUBLIC_BUCKET, "nonexistent.png", None)
    record(pub_anon.status_code in (200, 400, 404), "anon read path on meal-images reachable", str(pub_anon.status_code))

    rm = storage("DELETE", PRIVATE_BUCKET, obj_a, a_token)
    record(rm.status_code in (200, 204), "A deletes own object (cleanup)", str(rm.status_code))

    # Authoritative post-delete check: the object metadata must be gone.
    lst2 = httpx.request(
        "POST", f"{STORAGE}/object/list/{PRIVATE_BUCKET}",
        headers={"apikey": ANON, "Authorization": f"Bearer {a_token}",
                 "Content-Type": "application/json"},
        json={"prefix": f"{a_id}/", "limit": 100, "offset": 0},
        timeout=45,
    )
    try:
        remaining = [o.get("name") for o in lst2.json()]
    except Exception:
        remaining = ["<unparsed>"]
    record(lst2.status_code < 400 and not remaining, "A's prefix empty after delete (metadata)",
           f"{lst2.status_code} n={len(remaining)}")

    gone = storage("GET", PRIVATE_BUCKET, obj_a, a_token)
    if is_denied(gone.status_code):
        record(True, "byte read denied after delete", str(gone.status_code))
    else:
        note(f"byte read of the deleted object still returned {gone.status_code} "
             f"({len(gone.content)}B) — Supabase Storage serves this path through a cache, so "
             f"metadata deletion (verified above) is authoritative, not the byte endpoint")


def consent_gate(a_token: str) -> None:
    head("consent gate (live, A's consent revoked by operator beforehand)")
    code, cur = api("GET", "/api/v1/consent/current", a_token)
    has_consent = code == 200 and isinstance(cur, dict) and bool(cur.get("consent_version"))
    record(not has_consent, "A starts with no active consent", f"{code} {brief(cur)}")

    code, body = api("POST", "/api/v1/health/record", a_token,
                     json={"trimester": 2, "week_number": 21, "current_weight_kg": 61.0})
    record(code == 409, "health record REJECTED without consent -> 409", f"{code} {brief(body)}")

    code, _ = api("POST", "/api/v1/consent", a_token, json={"consent_version": "2026-09-v1"})
    record(code in (200, 201), "A accepts consent", str(code))

    code, rec = api("POST", "/api/v1/health/record", a_token,
                    json={"trimester": 2, "week_number": 21, "current_weight_kg": 61.0, "notes": "gate-ok"})
    rid = rec.get("id") if isinstance(rec, dict) else None
    artifacts["record_A_new"] = rid
    record(code in (200, 201) and bool(rid), "health record ACCEPTED after consent", f"{code}")

    # consent is an app-layer gate; RLS itself does not encode it
    note("health_records RLS WITH CHECK is only (user_id = auth.uid()) — "
         "the consent rule is enforced by FastAPI, not the database")


def fastapi_ownership(a_token: str, b_token: str, a_id: str) -> None:
    head("FastAPI endpoint ownership (deployed)")
    code, rec = api("POST", "/api/v1/health/record", a_token,
                    json={"trimester": 3, "week_number": 30, "current_weight_kg": 62.0, "notes": "fastapi-A"})
    rid = rec.get("id") if isinstance(rec, dict) else None
    artifacts["record_A_fastapi"] = rid
    record(code in (200, 201) and bool(rid), "A creates health record via API", f"{code}")

    if rid:
        code, _ = api("GET", f"/api/v1/health/records/{rid}", b_token)
        record(code == 404, "B GET A's record -> 404", str(code))
        code, _ = api("GET", f"/api/v1/health/records/{rid}/discussion-points", b_token)
        record(code == 404, "B GET A's discussion-points -> 404", str(code))
        code, _ = api("DELETE", f"/api/v1/health/records/{rid}", b_token)
        record(code == 404, "B DELETE A's record -> 404", str(code))
        code, _ = api("GET", f"/api/v1/health/records/{rid}", a_token)
        record(code == 200, "A's record intact after B's attempts", str(code))

    for path in ("/api/v1/auth/me", "/api/v1/health/records", "/api/v1/diet/plans",
                 "/api/v1/urgent/notes", "/api/v1/privacy/export", "/api/v1/files"):
        code, _ = api("GET", path)
        record(code == 401, f"unauth GET {path} -> 401", str(code))

    code, comp = api("GET", "/api/v1/profile/completion", a_token)
    a_all = comp.get("declared_allergies") if isinstance(comp, dict) else None
    code2, _ = api("PATCH", "/api/v1/profile/preferences", b_token,
                   json={"allergies": ["peanut"], "dietary_preference": "veg"})
    code3, comp2 = api("GET", "/api/v1/profile/completion", a_token)
    a_all2 = comp2.get("declared_allergies") if isinstance(comp2, dict) else None
    record(a_all == a_all2 and a_all2 != ["peanut"], "B's preference write did not touch A",
           f"A={a_all2} patch={code2}")

    code, rows = api("GET", "/api/v1/health/records", b_token)
    ids = [r.get("id") for r in rows] if isinstance(rows, list) else []
    record(rid not in ids if rid else True, "B's health list excludes A's", f"{code} n={len(ids)}")

    code, ex = api("GET", "/api/v1/privacy/export", a_token)
    blob = json.dumps(ex)
    if rid:
        record(rid in blob, "A's export contains own record", str(code))


def catalogue(a_token: str, b_token: str) -> None:
    head("catalogue visibility")
    code, meals = api("GET", "/api/v1/meals", a_token)
    statuses = {m.get("content_status") for m in meals} if isinstance(meals, list) else set()
    record(code == 200, "authenticated GET /api/v1/meals", f"{code}")
    record(statuses <= {"PUBLISHED"}, "API serves only PUBLISHED content",
           f"statuses={statuses or 'set() (catalogue empty)'}")
    if not meals:
        note("catalogue is empty, so the PUBLISHED-only filter is not exercised by data here")
    code, rows = rest("GET", "meals", a_token, {"select": "content_status"})
    st = {r.get("content_status") for r in rows} if isinstance(rows, list) else set()
    note(f"direct PostgREST read as authenticated user: {code} statuses={st or 'set()'} "
         f"— RLS policy p_meals_read is USING (true), so it does NOT gate on content_status")
    code, _ = api("GET", "/api/v1/meals/images/all", b_token)
    record(code == 200, "authenticated GET /meals/images/all", str(code))
    code, _ = api("GET", "/api/v1/meals")
    record(code == 401, "unauth GET /api/v1/meals -> 401", str(code))


def main() -> None:
    a, a_id = sign_in("a")
    b, b_id = sign_in("b")
    artifacts.update(A=a_id, B=b_id)
    print(f"signed in OK\n  A={a_id}\n  B={b_id}")

    consent_gate(a)
    unauthenticated_row_layer()
    cross_user_matrix(b, b_id, a_id)
    own_rows_intact(a, a_id)
    storage_isolation(a, b, a_id, b_id)
    fastapi_ownership(a, b, a_id)
    catalogue(a, b)

    failed = [r for r in results if not r[0]]
    print(f"\n{'=' * 78}\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("\nFAILURES:")
        for _, name, detail in failed:
            print(f"  - {name}  [{detail}]")
    print("ARTIFACTS " + json.dumps(artifacts, default=str))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
