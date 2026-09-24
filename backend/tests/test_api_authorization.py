"""CRITICAL TESTS 4 & 5 — authorization and user isolation (IDOR)."""

from __future__ import annotations

import pytest

from .conftest import register_and_login

pytestmark = pytest.mark.asyncio


async def _create_record(client, token, week=20, trimester=2, weight=60):
    resp = await client.post(
        "/api/v1/consent",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_version": "2026-09-v1"},
    )
    assert resp.status_code == 201
    resp = await client.post(
        "/api/v1/health/record",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "trimester": trimester,
            "week_number": week,
            "current_weight_kg": weight,
            "dietary_preference": "veg",
            "allergies": ["peanut"],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_unauthenticated_cannot_access_health_records(client):
    """TEST 4."""
    resp = await client.get("/api/v1/health/records")
    assert resp.status_code == 401
    resp = await client.post(
        "/api/v1/health/record",
        json={"trimester": 2, "week_number": 20, "current_weight_kg": 60},
    )
    assert resp.status_code == 401


async def test_user_a_cannot_read_user_b_records(client):
    """TEST 5."""
    token_a, _, _ = await register_and_login(client, "usera@test.com")
    token_b, _, _ = await register_and_login(client, "userb@test.com")
    record_id = await _create_record(client, token_a)

    resp = await client.get(
        f"/api/v1/health/records/{record_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404  # not visible — ownership enforced

    resp = await client.get(
        f"/api/v1/health/records/{record_id}/discussion-points",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404


async def test_user_a_cannot_delete_user_b_records(client):
    token_a, _, _ = await register_and_login(client, "userc@test.com")
    token_b, _, _ = await register_and_login(client, "userd@test.com")
    record_id = await _create_record(client, token_a)

    resp = await client.delete(
        f"/api/v1/health/records/{record_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404

    # Owner can delete.
    resp = await client.delete(
        f"/api/v1/health/records/{record_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 204


async def test_expired_token_rejected_at_api(client):
    """TEST 6 (API): a tampered/expired bearer is rejected."""
    token, _, _ = await register_and_login(client, "usere@test.com")
    resp = await client.get(
        "/api/v1/health/records",
        headers={"Authorization": f"Bearer {token}x"},
    )
    assert resp.status_code == 401
