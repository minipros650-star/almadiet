"""CRITICAL TESTS 8 & 9 — route resolution: image list route not shadowed by
/{meal_id}, UUID route still works, 422 on non-UUID."""

from __future__ import annotations

import uuid

import pytest

from .conftest import make_meal, register_and_login

pytestmark = pytest.mark.asyncio


async def test_images_all_route_resolves(client, seeded_db):
    """TEST 8: /api/v1/meals/images/all must not be captured by /{meal_id}."""
    token, _, _ = await register_and_login(client, "routeuser@test.com")
    resp = await client.get(
        "/api/v1/meals/images/all", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


async def test_meal_uuid_route_works(client, seeded_db):
    """TEST 9: generic UUID route still resolves."""
    from app.database import async_session_maker

    async with async_session_maker() as session:
        meal = make_meal(name="Route Test Meal")
        session.add(meal)
        await session.commit()
        meal_id = meal.id

    resp = await client.get(f"/api/v1/meals/{meal_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Route Test Meal"


async def test_non_uuid_meal_id_is_422(client):
    resp = await client.get("/api/v1/meals/not-a-uuid")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


async def test_unknown_meal_is_404_envelope(client):
    resp = await client.get(f"/api/v1/meals/{uuid.uuid4()}")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "message" in body["error"]


async def test_error_envelope_shape_on_validation_error(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "bad"},  # missing fields
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "INVALID_INPUT"
    assert "details" in body["error"]


async def test_healthz_public(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
