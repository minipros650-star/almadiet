"""CRITICAL TESTS 10 & 11 — 7-day plan structure and universal safety
validation, plus meal swap. Uses the full API stack with SQLite."""

from __future__ import annotations

import uuid

import pytest

from sqlalchemy import select

from .conftest import make_meal, register_and_login

pytestmark = pytest.mark.asyncio

PEANUT_INGREDIENTS = [{"name": "Peanut butter", "quantity": "2 tbsp"}]
SAFE_INGREDIENTS = [{"name": "Rice", "quantity": "1 cup"}, {"name": "Moong dal"}]


async def _setup_user_with_allergy(client, email):
    """Register, consent, health record with peanut allergy, return (token, record_id)."""
    token, _, _ = await register_and_login(client, email)
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
            "trimester": 2,
            "week_number": 20,
            "current_weight_kg": 62,
            "dietary_preference": "nonveg",
            "allergies": ["peanut", "groundnut"],  # synonyms both accepted
        },
    )
    assert resp.status_code == 201, resp.text

    # Personalized path requires the server-side pregnancy profile.
    from datetime import date, timedelta as td

    prof = await client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "height_cm": 162,
            "pre_pregnancy_weight_kg": 58,
            "lmp_date": (date.today() - td(days=140)).isoformat(),
        },
    )
    assert prof.status_code == 200, prof.text
    prefs = await client.patch(
        "/api/v1/profile/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"allergies": ["peanut"], "dietary_preference": "nonveg"},
    )
    assert prefs.status_code == 200, prefs.text
    return token, resp.json()["id"]


async def _seed_catalog(peanut_meal_name="Peanut Chikki"):
    from app.database import async_session_maker
    from app.models.meal import Meal

    async with async_session_maker() as session:
        # Peanut breakfast meal — must NEVER be selectable for our user.
        session.add(
            make_meal(
                name=peanut_meal_name,
                ingredients=PEANUT_INGREDIENTS,
                meal_type="Breakfast",
            )
        )
        # Safe meals across slots (enough for 7 days × 4 slots × 2).
        for i in range(12):
            session.add(
                make_meal(
                    name=f"Safe Breakfast {i}",
                    ingredients=SAFE_INGREDIENTS,
                    meal_type="Breakfast",
                    calories=200 + i,
                )
            )
            session.add(
                make_meal(
                    name=f"Safe Lunch {i}",
                    ingredients=SAFE_INGREDIENTS,
                    meal_type="Lunch",
                    calories=350 + i,
                )
            )
            session.add(
                make_meal(
                    name=f"Safe Dinner {i}",
                    ingredients=SAFE_INGREDIENTS,
                    meal_type="Lunch / Dinner",
                    calories=400 + i,
                )
            )
            session.add(
                make_meal(
                    name=f"Safe Snack {i}",
                    ingredients=SAFE_INGREDIENTS,
                    meal_type="Snack",
                    calories=150 + i,
                )
            )
        from app.services import meal_service

        result = await session.execute(select(Meal))
        for m in result.scalars().all():
            await meal_service.approve_meal(session, m.id, reviewer="test-reviewer")
        await session.commit()


async def _generate_plan(client, token, record_id):
    resp = await client.post(
        "/api/v1/diet/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"health_record_id": record_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_plan_has_exactly_seven_days(client, seeded_db, active_policy):
    """TEST 10."""
    await _seed_catalog()
    token, record_id = await _setup_user_with_allergy(client, "planuser@test.com")
    plan = await _generate_plan(client, token, record_id)
    assert len(plan["days"]) == 7
    assert [d["day_index"] for d in plan["days"]] == [1, 2, 3, 4, 5, 6, 7]
    for day in plan["days"]:
        assert set(day["meals"].keys()) == {"breakfast", "lunch", "snack", "dinner"}


async def test_peanut_allergy_never_leaks(client, seeded_db, active_policy):
    """TEST 1 (API, full stack): peanut meals never appear for allergic user."""
    await _seed_catalog(peanut_meal_name="Peanut Chikki")
    token, record_id = await _setup_user_with_allergy(client, "peanutuser@test.com")
    plan = await _generate_plan(client, token, record_id)

    def all_meals(p):
        for day in p["days"]:
            for slot_meals in day["meals"].values():
                for m in slot_meals:
                    yield m

    names = [m["name"] for m in all_meals(plan)]
    assert "Peanut Chikki" not in names
    for m in all_meals(plan):
        assert "peanut" not in [a.lower() for a in (m.get("allergens") or [])]
        # ingredient-level re-check
        for ing in (m.get("ingredients") or []):
            assert "peanut" not in str(ing.get("name", "")).lower()


async def test_every_selected_meal_passes_final_validation(client, seeded_db, active_policy):
    """TEST 11: every returned meal is validated safe for this user."""
    await _seed_catalog()
    token, record_id = await _setup_user_with_allergy(client, "safeuser@test.com")
    plan = await _generate_plan(client, token, record_id)
    assert plan["exclusions_applied"]["filters_applied"], "exclusions documented"
    for day in plan["days"]:
        for slot_meals in day["meals"].values():
            for m in slot_meals:
                assert m["why_suggested"], "every meal carries an explanation"
                assert m["source"], "provenance present"
                assert m["content_status"] in ("REVIEWED", "PUBLISHED")


async def test_swap_preserves_safety_and_slot(client, seeded_db, active_policy):
    await _seed_catalog()
    token, record_id = await _setup_user_with_allergy(client, "swapuser@test.com")
    plan = await _generate_plan(client, token, record_id)

    day1 = plan["days"][0]
    breakfast = day1["meals"]["breakfast"][0]

    resp = await client.post(
        f"/api/v1/diet/plans/{plan['id']}/swap",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "day_index": 1,
            "slot": "breakfast",
            "current_meal_id": breakfast["id"],
        },
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    new_breakfast = updated["days"][0]["meals"]["breakfast"]

    # Slot preserved, still safe, still has explanation.
    assert len(new_breakfast) == len(day1["meals"]["breakfast"])
    original_ids = {m["id"] for m in day1["meals"]["breakfast"]}
    new_meals = [m for m in new_breakfast if m["id"] not in original_ids]
    assert len(new_meals) == 1, "exactly the target card was replaced"
    for m in new_meals:
        assert "peanut" not in [a.lower() for a in (m.get("allergens") or [])]
        assert "swap" in " ".join(m["why_suggested"]).lower()
    # The swapped-out meal is gone.
    assert breakfast["id"] not in {m["id"] for m in new_breakfast}


async def test_contradictory_record_cannot_generate(client, seeded_db, active_policy):
    """A contradictory record cannot be created in the first place (TEST 3 API)."""
    token, _, _ = await register_and_login(client, "badrecord@test.com")
    await client.post(
        "/api/v1/consent",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_version": "2026-09-v1"},
    )
    resp = await client.post(
        "/api/v1/health/record",
        headers={"Authorization": f"Bearer {token}"},
        json={"trimester": 1, "week_number": 30, "current_weight_kg": 60},
    )
    assert resp.status_code == 422
    assert "week 30" in resp.json()["error"]["message"]


async def test_consent_required_before_health_record(client, seeded_db, active_policy):
    token, _, _ = await register_and_login(client, "noconsent@test.com")
    resp = await client.post(
        "/api/v1/health/record",
        headers={"Authorization": f"Bearer {token}"},
        json={"trimester": 2, "week_number": 20, "current_weight_kg": 60},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONSENT_REQUIRED"


async def test_consent_required_before_plan_generation(client, seeded_db, active_policy):
    """A complete profile WITHOUT consent must still be blocked (409)."""
    token, _, _ = await register_and_login(client, "noconsent2@test.com")
    from datetime import date as d, timedelta as td

    prof = await client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "height_cm": 162,
            "pre_pregnancy_weight_kg": 58,
            "lmp_date": (d.today() - td(days=140)).isoformat(),
        },
    )
    assert prof.status_code == 200
    prefs = await client.patch(
        "/api/v1/profile/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"allergies": [], "dietary_preference": "veg"},
    )
    assert prefs.status_code == 200

    resp = await client.post(
        "/api/v1/diet/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] in ("CONSENT_REQUIRED", "INVALID_INPUT")
    assert body["error"]["details"]["blocking_code"] == "CONSENT_REQUIRED"
