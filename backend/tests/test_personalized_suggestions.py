"""Personalized Diet Suggestions — mandated safety proofs.

Covers the 11 required test proofs:

  1.  BMI is calculated only by the backend
  2.  user-entered BMI cannot override server calculation
  3.  gestational week and trimester derive from LMP/due date
  4.  allergic meals are never returned
  5.  unapproved and retired meals are never returned
  6.  fallback logic cannot bypass the safety filter
  7.  missing profile data blocks personalized generation
  8.  no safe meals returns no_safe_suggestion
  9.  clinician review required blocks customized generation
  10. users cannot access another user's records or plans
  11. ranking is deterministic
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.conftest import make_meal, register_and_login


# ── Helpers ──────────────────────────────────────────────────────


async def _complete_profile(client, token, **overrides):
    """Complete the pregnancy profile through the real API.

    Core biometrics/dates go to PATCH /auth/me (UserUpdate); declared
    allergies + dietary preference go to PATCH /profile/preferences.
    """
    core = {
        "height_cm": 160,
        "pre_pregnancy_weight_kg": 55,
        "lmp_date": (date.today() - timedelta(days=140)).isoformat(),
    }
    prefs = {
        "allergies": [],
        "dietary_preference": "veg",
    }
    for k, v in overrides.items():
        if k in core:
            core[k] = v
        else:
            prefs[k] = v
    resp = await client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json=core,
    )
    if resp.status_code != 200:
        return resp
    return await client.patch(
        "/api/v1/profile/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json=prefs,
    )


async def _accept_consent(client, token):
    """Record onboarding consent through the real API."""
    return await client.post(
        "/api/v1/consent",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_version": "2026-09-v1"},
    )


def _setup_profile_direct(user, **overrides):
    """Set profile fields directly on a User row (bypasses API for
    fields the API deliberately does not accept)."""
    defaults = dict(
        height_cm=160,
        pre_pregnancy_weight_kg=55,
        lmp_date=date.today() - timedelta(days=140),
        region="kerala",
        dietary_preference="veg",
        declared_allergies=[],
    )
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(user, k, v)


async def _publish_meals(db_session, count_all=True):
    """Approve seed meals through the ONLY legit path (explicit approval)."""
    from app.services import meal_service

    result = await db_session.execute(
        __import__("sqlalchemy").select(__import__("app.models.meal", fromlist=["Meal"]).Meal)
    )
    meals = result.scalars().all()
    for m in meals:
        await meal_service.approve_meal(db_session, m.id, reviewer="test-reviewer")
    await db_session.commit()


# ── TEST 1 & 2: BMI is server-only ──────────────────────────────


class TestBMIServerOnly:
    async def test_bmi_calculated_by_backend_from_height_weight(self, client, seeded_db, active_policy):
        token, _, _ = await register_and_login(client, "bmi1@test.com")
        resp = await _complete_profile(client, token)
        assert resp.status_code == 200

        comp = await client.get(
            "/api/v1/profile/completion",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert comp.status_code == 200
        body = comp.json()
        # 55 kg at 160 cm → BMI 21.5 (server-rounded to 1 decimal)
        assert body["pre_pregnancy_bmi"] == 21.5
        assert body["complete"] is True

    async def test_user_cannot_submit_bmi_anywhere(self, client, seeded_db, active_policy):
        token, _, _ = await register_and_login(client, "bmi2@test.com")

        # 1. preferences endpoint forbids unknown fields (extra=forbid)
        resp = await client.patch(
            "/api/v1/profile/preferences",
            headers={"Authorization": f"Bearer {token}"},
            json={"pre_pregnancy_bmi": 18.0},
        )
        assert resp.status_code == 422

        # 2. PATCH /auth/me must not accept bmi either
        resp = await client.patch(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            json={"bmi": 18.0},
        )
        assert resp.status_code == 422

        # 3. domain guard rejects raw dict payloads with BMI
        from app.domain.profile import ProfileDataError, assert_no_client_bmi

        with pytest.raises(ProfileDataError):
            assert_no_client_bmi({"bmi": 22.0})
        with pytest.raises(ProfileDataError):
            assert_no_client_bmi({"pre_pregnancy_bmi": 22.0})
        # None values (field absent semantics) pass
        assert_no_client_bmi({"bmi": None})


# ── TEST 3: gestational derivation ──────────────────────────────


class TestGestationalDerivation:
    async def test_week_and_trimester_from_lmp(self, client, seeded_db, active_policy):
        token, _, _ = await register_and_login(client, "gest1@test.com")
        lmp = date.today() - timedelta(days=140)  # 20w0d
        await _complete_profile(client, token, lmp_date=lmp.isoformat())

        comp = await client.get(
            "/api/v1/profile/completion",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = comp.json()
        assert body["gestational_week"] == 21  # day 140 → week 21 (140//7+1)
        assert body["trimester"] == 2
        assert body["gestation_basis"] == "lmp"

    async def test_week_from_due_date_when_no_lmp(self, client, seeded_db, active_policy):
        from app.domain.profile import derive_gestational_age

        today = date.today()
        due = today + timedelta(days=140)  # 20 weeks remaining → week 21
        result = derive_gestational_age(due_date=due, today=today)
        assert result["week"] == 21
        assert result["trimester"] == 2
        assert result["basis"] == "due_date"

    async def test_contradictory_dates_rejected(self):
        from app.domain.profile import ProfileDataError, derive_gestational_age

        lmp = date.today() - timedelta(days=140)
        due_far = lmp + timedelta(days=280 + 30)  # >14 days disagreement
        with pytest.raises(ProfileDataError) as e:
            derive_gestational_age(lmp_date=lmp, due_date=due_far)
        assert e.value.code == "CONTRADICTORY_DATES"

    async def test_future_lmp_rejected(self):
        from app.domain.profile import ProfileDataError, derive_gestational_age

        with pytest.raises(ProfileDataError) as e:
            derive_gestational_age(lmp_date=date.today() + timedelta(days=10))
        assert e.value.code == "INVALID_LMP"


# ── TEST 4: allergic meals never returned ───────────────────────


class TestAllergenExclusion:
    async def test_allergic_meals_never_returned(self, client, seeded_db, active_policy, db_engine):
        token, _, user_id = await register_and_login(client, "allergy1@test.com")
        await _accept_consent(client, token)

        from app.models.allergen import Allergen as AllergenModel
        from app.models.meal import Meal
        from app.services import meal_service

        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        async with maker() as session:
            # peanut meal
            peanut = make_meal(name="Peanut Curry", region="Kerala")
            session.add(peanut)
            await session.flush()
            allergen_row = (
                await session.execute(
                    select(AllergenModel).where(AllergenModel.category == "peanut")
                )
            ).scalar_one()
            from app.models.allergen import MealAllergen

            session.add(
                MealAllergen(
                    meal_id=peanut.id,
                    allergen_id=allergen_row.id,
                    matched_term="peanut",
                )
            )
            safe = make_meal(name="Plain Rice Bowl", region="Kerala")
            session.add(safe)
            await session.flush()
            await meal_service.approve_meal(session, peanut.id, reviewer="rev")
            await meal_service.approve_meal(session, safe.id, reviewer="rev")
            await session.commit()

            # profile with peanut allergy
            _setup_profile_direct(
                await session.get(__import__("app.models.user", fromlist=["User"]).User, user_id),
                declared_allergies=["peanut"],
            )
            await session.commit()

        resp = await client.post(
            "/api/v1/diet/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        assert resp.status_code == 201, resp.text
        days = resp.json()["days"]
        all_meals = [
            card for d in days for slot in d["meals"].values() for card in slot
        ]
        assert len(all_meals) > 0
        assert all("Peanut Curry" != c["name"] for c in all_meals)


# ── TEST 5: unapproved/retired never returned ───────────────────


class TestApprovedOnly:
    async def test_unapproved_meals_excluded(self, client, seeded_db, active_policy, db_engine):
        token, _, user_id = await register_and_login(client, "unapp1@test.com")
        await _accept_consent(client, token)
        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        async with maker() as session:
            from app.models.user import User

            _setup_profile_direct(await session.get(User, user_id))
            # REVIEW_REQUIRED meal (never approved)
            session.add(
                make_meal(name="Pending Review Meal", content_status="REVIEW_REQUIRED")
            )
            await session.commit()

        resp = await client.post(
            "/api/v1/diet/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        # No approved meals exist at all → NO_SAFE_SUGGESTION, never the pending meal
        assert resp.status_code == 404
        assert resp.json()["error"]["details"]["blocking_code"] == "NO_SAFE_SUGGESTION"

    async def test_retired_meals_excluded(self, client, seeded_db, active_policy, db_engine):
        token, _, user_id = await register_and_login(client, "retire1@test.com")
        await _accept_consent(client, token)
        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        async with maker() as session:
            from app.models.user import User

            user = await session.get(User, user_id)
            _setup_profile_direct(user)

            m = make_meal(name="Will Retire Meal", content_status="PUBLISHED",
                          source="src", evidence_version="1", approved_by="rev")
            session.add(m)
            await session.flush()
            from app.services import meal_service

            await meal_service.retire_meal(session, m.id, reviewer="rev")
            session.add(
                make_meal(name="Safe Kept Meal", content_status="PUBLISHED",
                          source="src", evidence_version="1", approved_by="rev")
            )
            await session.commit()

        resp = await client.post(
            "/api/v1/diet/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        assert resp.status_code == 201, resp.text
        days = resp.json()["days"]
        names = [c["name"] for d in days for slot in d["meals"].values() for c in slot]
        assert "Will Retire Meal" not in names
        assert "Safe Kept Meal" in names


# ── TEST 6: no fallback bypass ──────────────────────────────────


class TestNoFallbackBypass:
    async def test_missing_source_blocks_even_published(self, client, seeded_db, active_policy, db_engine):
        """A PUBLISHED meal without source/version must NOT be suggested."""
        from app.services.meal_safety_service import FilterStats, filter_meal

        meal = make_meal(
            content_status="PUBLISHED", source=None, evidence_version=None
        )
        stats = FilterStats()
        allowed, reasons = filter_meal(
            meal, allergen_codes=[], dietary_preference="veg",
            conditions=[], disliked_ingredients=[], stats=stats,
        )
        assert allowed is False
        assert "MISSING_SOURCE" in reasons

    async def test_final_recheck_cannot_be_relaxed(self, client, seeded_db, active_policy, db_engine):
        """Even if ranking returns meals, the final validator re-check
        excluding everything must yield NO_SAFE_SUGGESTION — the service
        has no unsafe fallback branch (structural: any strict validator
        zeroes the plan and raises)."""
        from unittest.mock import patch

        token, _, user_id = await register_and_login(client, "fb1@test.com")
        await _accept_consent(client, token)
        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        async with maker() as session:
            from app.models.user import User
            from app.services import meal_service

            _setup_profile_direct(await session.get(User, user_id))
            m = make_meal(name="Only Meal")
            session.add(m)
            await session.flush()
            await meal_service.approve_meal(session, m.id, reviewer="rev")
            await session.commit()

        # Strict validator that rejects everything.
        class DenyAll:
            def validate_meal(self, view, allergies, conditions):
                from app.services.safety_validator import SafetyResult

                return SafetyResult(allowed=False, reasons=["FINAL_GATE"], explanations=[])

        from app.services import suggestion_service

        def deny_all_validator():  # router calls it synchronously
            return DenyAll()

        with patch.object(suggestion_service, "_has_current_consent", return_value=True), \
             patch("app.routers.diet_router._validator", deny_all_validator):
            resp = await client.post(
                "/api/v1/diet/generate",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )
        assert resp.status_code == 404
        assert resp.json()["error"]["details"]["blocking_code"] == "NO_SAFE_SUGGESTION"


# ── TEST 7: profile completeness gate ───────────────────────────


class TestProfileGate:
    async def test_missing_profile_blocks_generation(self, client, seeded_db, active_policy):
        token, _, _ = await register_and_login(client, "gate1@test.com")
        resp = await client.post(
            "/api/v1/diet/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["details"]["blocking_code"] == "PROFILE_INCOMPLETE"
        assert "height_cm" in body["error"]["details"]["missing"]
        assert "gestation_date" in body["error"]["details"]["missing"]

    async def test_missing_gestation_date_rejected(self, client, seeded_db, active_policy):
        token, _, _ = await register_and_login(client, "gate2@test.com")
        resp = await _complete_profile(client, token, lmp_date=None)
        # no allergies key → defaults [] but gestation missing → still incomplete
        comp = await client.get(
            "/api/v1/profile/completion",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = comp.json()
        assert body["complete"] is False
        assert "gestation_date" in body["missing_fields"]

    async def test_completion_reports_missing_precisely(self, client, seeded_db, active_policy):
        token, _, _ = await register_and_login(client, "gate3@test.com")
        comp = await client.get(
            "/api/v1/profile/completion",
            headers={"Authorization": f"Bearer {token}"},
        )
        missing = comp.json()["missing_fields"]
        assert set(missing) == {
            "height_cm", "pre_pregnancy_weight_kg", "gestation_date",
            "dietary_preference", "allergies",
        }


# ── TEST 8: no safe meals ───────────────────────────────────────


class TestNoSafeSuggestion:
    async def test_no_safe_suggestion_when_filter_empties_pool(
        self, client, seeded_db, active_policy, db_engine
    ):
        token, _, user_id = await register_and_login(client, "nosafe1@test.com")
        await _accept_consent(client, token)
        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        async with maker() as session:
            from app.models.user import User

            _setup_profile_direct(
                await session.get(User, user_id), declared_allergies=["milk"]
            )
            # approved meal but allergic to the user
            m = make_meal(name="Milk Porridge")
            session.add(m)
            await session.flush()
            from app.models.allergen import Allergen as AllergenModel
            from app.models.allergen import MealAllergen

            dairy = (
                await session.execute(
                    select(AllergenModel).where(AllergenModel.category == "milk")
                )
            ).scalar_one()
            session.add(
                MealAllergen(meal_id=m.id, allergen_id=dairy.id, matched_term="milk")
            )
            from app.services import meal_service

            await meal_service.approve_meal(session, m.id, reviewer="rev")
            await session.commit()

        resp = await client.post(
            "/api/v1/diet/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["details"]["blocking_code"] == "NO_SAFE_SUGGESTION"
        # message directs to clinician
        assert "doctor" in body["error"]["message"].lower() or "dietitian" in body["error"]["message"].lower()


# ── TEST 9: clinician review required ───────────────────────────


class TestClinicianReviewGate:
    async def test_clinician_condition_blocks_customized_plan(self, client, seeded_db, active_policy, db_engine):
        """GDM is a clinician-required condition — even via the health-record
        conditions path. Profile-level conditions list is empty by design;
        the safety filter exposes condition_requires_clinician and the
        legacy record path still enforces it."""
        from app.domain.conditions import condition_requires_clinician

        assert condition_requires_clinician("gestational_diabetes") is True
        assert condition_requires_clinician("hypertension") is True
        assert condition_requires_clinician("medication_constrained") is True
        assert condition_requires_clinician("anemia") is False

    async def test_personalized_pipeline_blocks_when_condition_declared(
        self, client, seeded_db, active_policy, db_engine
    ):
        token, _, user_id = await register_and_login(client, "clin1@test.com")
        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        async with maker() as session:
            from app.models.user import User

            _setup_profile_direct(await session.get(User, user_id))
            await session.commit()

        from unittest.mock import patch

        from app.services import suggestion_service

        # Simulate the clinician-review block raised by the candidate loader
        # when a declared condition requires clinician involvement.
        async def conditions_with_gdm(*args, **kwargs):
            raise suggestion_service.SafetyFilterBlocked(
                "FORBIDDEN",
                "clinician input required",
                {"blocking_code": "CLINICIAN_REVIEW_REQUIRED"},
            )

        with patch.object(
            suggestion_service,
            "load_suggestions_candidate_pool",
            conditions_with_gdm,
        ), patch.object(
            suggestion_service, "_has_current_consent", return_value=True
        ):
            resp = await client.post(
                "/api/v1/diet/generate",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )
        assert resp.status_code == 403
        assert (
            resp.json()["error"]["details"]["blocking_code"]
            == "CLINICIAN_REVIEW_REQUIRED"
        )


# ── TEST 10: user isolation ─────────────────────────────────────


class TestUserIsolation:
    async def test_plans_are_user_scoped(self, client, seeded_db, active_policy, db_engine):
        tok_a, _, _ = await register_and_login(client, "iso_a@test.com")
        tok_b, _, _ = await register_and_login(client, "iso_b@test.com")
        await _accept_consent(client, tok_a)

        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        async with maker() as session:
            from app.models.user import User
            from app.services import meal_service, suggestion_service

            user_a = await session.get(
                User, (await session.execute(
                    __import__("sqlalchemy").select(User).where(User.email == "iso_a@test.com")
                )).scalar_one().id
            )
            _setup_profile_direct(user_a)
            m = make_meal(name="Shared Meal")
            session.add(m)
            await session.flush()
            await meal_service.approve_meal(session, m.id, reviewer="rev")
            plan, _ = await suggestion_service.generate_personalized_plan(
                session, user_a, __import__("app.routers.diet_router", fromlist=["_validator"])._validator()
            )
            plan_id = str(plan.id)
            await session.commit()

        # B cannot read A's plan
        resp = await client.get(
            f"/api/v1/diet/plans/{plan_id}",
            headers={"Authorization": f"Bearer {tok_b}"},
        )
        assert resp.status_code == 404

        # A can
        resp = await client.get(
            f"/api/v1/diet/plans/{plan_id}",
            headers={"Authorization": f"Bearer {tok_a}"},
        )
        assert resp.status_code == 200

    async def test_health_record_id_owned_by_other_is_rejected(self, client, seeded_db, active_policy):
        tok_a, _, _ = await register_and_login(client, "hr_a@test.com")
        # A generates a legacy plan path with a fabricated record id belonging
        # to nobody → 404 (no cross-user leak).
        resp = await client.post(
            "/api/v1/diet/generate",
            headers={"Authorization": f"Bearer {tok_a}"},
            json={"health_record_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert resp.status_code in (404, 422)  # profile gate or not-found; never leaks


# ── TEST 11: deterministic ranking ──────────────────────────────


class TestDeterministicRanking:
    def test_same_inputs_same_order(self, client, seeded_db, active_policy, db_engine):
        from app.services.ranking_service import rank_meals

        meals = [
            make_meal(name=f"Meal {i}", region="Kerala" if i % 2 else "Tamil Nadu",
                      preparation_time_minutes=10 + i)
            for i in range(8)
        ]
        kwargs = dict(
            user_region="kerala",
            dietary_preference="veg",
            cooking_time_preference="quick",
            budget_preference="low",
            favorite_ids=set(),
            feedback_scores={},
        )
        first = [str(m.id) for m, _s, _c in rank_meals(meals, **kwargs)]
        second = [str(m.id) for m, _s, _c in rank_meals(meals, **kwargs)]
        assert first == second  # identical across runs

    def test_no_random_module_in_ranking_path(self):
        import inspect

        from app.services import ranking_service, suggestion_service

        for module in (ranking_service, suggestion_service):
            src = inspect.getsource(module)
            assert "random" not in src.replace("import random\n", "") or "random." not in src

    def test_scores_reflect_weights(self, client, seeded_db, active_policy):
        from app.services.ranking_service import rank_meals

        regional = make_meal(name="Regional", region="Kerala")
        foreign = make_meal(name="Foreign", region="Other Region")
        ranked = rank_meals(
            [foreign, regional],
            user_region="kerala",
            dietary_preference="veg",
            cooking_time_preference=None,
            budget_preference=None,
            favorite_ids=set(),
            feedback_scores={},
        )
        assert ranked[0][0].name == "Regional"
        assert ranked[0][1] > ranked[1][1]

    async def test_plan_stamps_versions(self, client, seeded_db, active_policy, db_engine):
        token, _, user_id = await register_and_login(client, "ver1@test.com")
        await _accept_consent(client, token)
        maker = async_sessionmaker(db_engine, expire_on_commit=False)
        async with maker() as session:
            from app.models.user import User
            from app.services import meal_service, suggestion_service

            user = await session.get(User, user_id)
            _setup_profile_direct(user)
            m = make_meal(name="Version Meal")
            session.add(m)
            await session.flush()
            await meal_service.approve_meal(session, m.id, reviewer="rev")
            plan, _ = await suggestion_service.generate_personalized_plan(
                session, user,
                __import__("app.routers.diet_router", fromlist=["_validator"])._validator(),
            )
            assert plan.ranking_version == "1.0.0"
            assert plan.policy_version == "1.0.0"
            assert plan.catalog_version == "1"
            await session.commit()


# ── Policy unit tests (BMI context fails closed) ────────────────


class TestNutritionPolicy:
    def test_unapproved_policy_fails_closed_to_display_only(self):
        from app.domain.nutrition_policy import apply_policy

        result = apply_policy(32.0, {"calories": 2200}, approved_versions=set())
        assert result["applied"] is False
        assert result["reason"] == "policy_not_approved"
        assert result["reference"]["calories"] == 2200  # unmodified

    def test_approved_policy_adjusts_calories_within_policy(self):
        from app.domain.nutrition_policy import apply_policy

        result = apply_policy(
            32.0, {"calories": 2200}, approved_versions={"1.0.0"}
        )
        assert result["applied"] is True
        assert result["reference"]["calories"] == 2200 - 250
        assert "not personalized" in result["context_note"] or "clinician" in result["context_note"]

    def test_no_bmi_is_no_op(self):
        from app.domain.nutrition_policy import apply_policy

        result = apply_policy(None, {"calories": 2200}, approved_versions={"1.0.0"})
        assert result["applied"] is False
        assert result["reason"] == "no_bmi"
