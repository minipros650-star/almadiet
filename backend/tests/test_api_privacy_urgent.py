"""Privacy (export/deletion) and urgent-help wording tests (CRITICAL TEST 12)."""

from __future__ import annotations

import pytest

from .conftest import register_and_login

pytestmark = pytest.mark.asyncio


async def test_data_export_contains_profile_and_records(client, seeded_db):
    token, _, _ = await register_and_login(client, "exportuser@test.com")
    await client.post(
        "/api/v1/consent",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_version": "2026-09-v1"},
    )
    await client.post(
        "/api/v1/health/record",
        headers={"Authorization": f"Bearer {token}"},
        json={"trimester": 2, "week_number": 20, "current_weight_kg": 61},
    )
    resp = await client.get(
        "/api/v1/privacy/export", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    bundle = resp.json()
    assert bundle["profile"]["email"] == "exportuser@test.com"
    assert len(bundle["health_records"]) == 1


async def test_account_deletion_cascades(client, seeded_db):
    token, refresh, _ = await register_and_login(client, "deleteuser@test.com")
    resp = await client.delete(
        "/api/v1/privacy/account", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 204
    # Old token no longer works (user gone).
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    # Login fails (user gone).
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "deleteuser@test.com", "password": "Password123"},
    )
    assert resp.status_code == 401


# ── CRITICAL TEST 12: urgent help never generates treatment instructions ─

BANNED_URGENT_WORDS = ("treatment", "diagnos", "resolved", "cured", "prescrib")


async def test_urgent_info_is_information_only(client, seeded_db):
    token, _, _ = await register_and_login(client, "urgentuser@test.com")
    resp = await client.get(
        "/api/v1/urgent/info", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    info = resp.json()

    assert "cannot assess emergencies" in info["disclaimer"].lower()
    all_text = (
        info["disclaimer"]
        + " ".join(info["warning_signs"])
        + " ".join(info["contact_guidance"])
        + " ".join(info["clinician_checklist"])
    ).lower()
    for word in BANNED_URGENT_WORDS:
        assert word not in all_text, f"banned word in urgent content: {word}"
    # Emergency guidance present.
    assert any("112" in g for g in info["contact_guidance"])


async def test_urgent_notes_have_no_resolution(client, seeded_db):
    token, _, _ = await register_and_login(client, "urgentnote@test.com")
    resp = await client.post(
        "/api/v1/urgent/notes",
        headers={"Authorization": f"Bearer {token}"},
        json={"observed_symptoms": ["mild headache"], "note_text": "since morning"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["observed_symptoms"] == ["mild headache"]
    assert "resolved" not in body and "is_active" not in body


async def test_urgent_info_requires_auth(client):
    resp = await client.get("/api/v1/urgent/info")
    assert resp.status_code == 401
