"""API auth integration tests — register, login, rotation, logout-all, PATCH profile."""

from __future__ import annotations

import pytest

from .conftest import register_and_login

pytestmark = pytest.mark.asyncio


async def test_register_login_flow(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@test.com",
            "password": "Password123",
            "name": "Alice",
            "region": "kerala",
            "language": "en",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email"] == "alice@test.com"

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@test.com", "password": "Password123"},
    )
    assert resp.status_code == 200
    assert "refresh_token" in resp.json()


async def test_duplicate_email_conflict(client):
    await register_and_login(client, "dup@test.com")
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "dup@test.com", "password": "Password123", "name": "Dup"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_login_wrong_password_generic_error(client):
    await register_and_login(client, "bob@test.com")
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@test.com", "password": "WrongPass1"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert body["error"]["message"] == "Invalid email or password"


async def test_login_lockout(client):
    await register_and_login(client, "carol@test.com")
    for _ in range(5):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "carol@test.com", "password": "WrongPass1"},
        )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "carol@test.com", "password": "Password123"},
    )
    assert resp.status_code == 423  # even correct password is locked


async def test_refresh_rotation_and_reuse_revocation(client):
    """Rotating a refresh token invalidates the old one; reuse revokes family."""
    access, refresh, _ = await register_and_login(client, "dave@test.com")

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["refresh_token"] != refresh

    # Reusing the OLD token must now fail (and revoke the family).
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 401

    # The rotated token is dead too (family revoked).
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert resp.status_code == 401


async def test_logout_all_revokes_sessions(client):
    access, refresh, _ = await register_and_login(client, "erin@test.com")
    resp = await client.post(
        "/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {access}"}
    )
    assert resp.status_code == 204
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 401


async def test_patch_profile_updates_fields(client):
    """Profile update via authenticated PATCH (no password involved)."""
    access, _, _ = await register_and_login(client, "frida@test.com")
    resp = await client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
        json={"name": "Frida K.", "phone": "9876543210"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Frida K."
    assert body["phone"] == "9876543210"

    # GET reflects the change.
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert resp.json()["name"] == "Frida K."


async def test_patch_profile_rejects_unknown_fields(client):
    access, _, _ = await register_and_login(client, "gita@test.com")
    resp = await client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
        json={"password_hash": "hacked"},
    )
    assert resp.status_code == 422


async def test_unauthenticated_me_rejected(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
