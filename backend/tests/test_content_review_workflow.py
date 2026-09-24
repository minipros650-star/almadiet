"""Content review & publication workflow — allowed and denied transitions.

Every gate is exercised through the deployed API (httpx ASGI client), so the
tests cover routing, the token-derived actor, the database-granted role, the
state machine, the content blockers, separation of duties and the ledger.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.database as database_module
from app.domain.content_roles import ContentRole
from app.services import content_review_service

from .conftest import register_and_login
from .test_governance_architecture import _auth, _complete_profile, json_names

REVIEW = "/api/v1/content-governance/meals/{}/review"
PUBLISH = "/api/v1/content-governance/meals/{}/publish"
RETIRE = "/api/v1/content-governance/meals/{}/retire"
PENDING = "/api/v1/content-governance/meals/pending"
HISTORY = "/api/v1/content-governance/meals/{}/history"


# ── helpers ───────────────────────────────────────────────────────────────


def _maker(db_engine):
    return async_sessionmaker(db_engine, class_=database_module.AsyncSession, expire_on_commit=False)


async def _grant(db_engine, user_id: str, role: ContentRole) -> None:
    async with _maker(db_engine)() as session:
        await content_review_service.grant_role(session, user_id=uuid.UUID(user_id), role=role)
        await session.commit()


async def _revoke(db_engine, user_id: str, role: ContentRole) -> None:
    async with _maker(db_engine)() as session:
        await content_review_service.revoke_role(session, user_id=uuid.UUID(user_id), role=role)
        await session.commit()


def _valid_meal(**overrides):
    from app.models.meal import Meal

    base = dict(
        name="Plain Rice",
        region="Kerala",
        meal_type="Lunch",
        trimester_suitability=["First", "Second", "Third"],
        cuisine="South Indian",
        calories=200,
        protein_g=6,
        carbs_g=30,
        fat_g=5,
        fiber_g=3,
        iron_mg=2,
        calcium_mg=80,
        folate_mcg=40,
        vitamin_c_mg=5,
        sodium_mg=120,
        sugar_g=3,
        ingredients=[{"name": "Rice", "quantity": "1 cup"}],
        serving_size="1 bowl",
        serving_basis="per serving as listed in source dataset",
        benefits=["Gentle on the stomach"],
        cautions=None,
        best_time_to_eat="Lunch",
        is_vegetarian=True,
        content_status="REVIEW_REQUIRED",
        source="AlmaDiet test dataset",
        evidence_version="1",
    )
    base.update(overrides)
    return Meal(**base)


async def _add_meal(db_engine, **overrides) -> str:
    async with _maker(db_engine)() as session:
        meal = _valid_meal(**overrides)
        session.add(meal)
        await session.flush()
        meal_id = str(meal.id)
        await session.commit()
    return meal_id


async def _link_allergen(db_engine, meal_id: str, category: str, matched_term: str) -> None:
    from app.models.allergen import Allergen, MealAllergen

    async with _maker(db_engine)() as session:
        allergen = (
            await session.execute(select(Allergen).where(Allergen.category == category))
        ).scalar_one()
        session.add(
            MealAllergen(
                meal_id=uuid.UUID(meal_id),
                allergen_id=allergen.id,
                matched_term=matched_term,
                match_type="synonym",
            )
        )
        await session.commit()


async def _meal_status(db_engine, meal_id: str) -> str:
    from app.models.meal import Meal

    async with _maker(db_engine)() as session:
        return (await session.get(Meal, uuid.UUID(meal_id))).content_status


async def _reviewer_and_publisher(client, db_engine):
    """Two distinct staff accounts: one REVIEWER, one PUBLISHER."""
    r_token, _, r_id = await register_and_login(client, "rev@test.com")
    p_token, _, p_id = await register_and_login(client, "pub@test.com")
    await _grant(db_engine, r_id, ContentRole.REVIEWER)
    await _grant(db_engine, p_id, ContentRole.PUBLISHER)
    return (r_token, r_id), (p_token, p_id)


# ── 1/2. role authorization ───────────────────────────────────────────────


class TestRoleAuthorization:
    async def test_ordinary_user_cannot_review(self, client, seeded_db, db_engine):
        token, _, _ = await register_and_login(client, "plain1@test.com")
        meal_id = await _add_meal(db_engine)
        resp = await client.post(REVIEW.format(meal_id), headers=_auth(token), json={})
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["details"]["required_roles"] == ["REVIEWER"]
        assert await _meal_status(db_engine, meal_id) == "REVIEW_REQUIRED"

    async def test_ordinary_user_cannot_publish(self, client, seeded_db, db_engine):
        token, _, _ = await register_and_login(client, "plain2@test.com")
        meal_id = await _add_meal(db_engine)
        resp = await client.post(PUBLISH.format(meal_id), headers=_auth(token), json={})
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["details"]["required_roles"] == ["PUBLISHER"]

    async def test_reviewer_can_review_but_not_publish(self, client, seeded_db, db_engine):
        ((r_token, _), _) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine)

        resp = await client.post(
            REVIEW.format(meal_id), headers=_auth(r_token), json={"rationale": "looks accurate"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["content_status"] == "REVIEWED"
        assert await _meal_status(db_engine, meal_id) == "REVIEWED"

        resp = await client.post(PUBLISH.format(meal_id), headers=_auth(r_token), json={})
        assert resp.status_code == 403, resp.text
        assert await _meal_status(db_engine, meal_id) == "REVIEWED"

    async def test_publisher_cannot_review(self, client, seeded_db, db_engine):
        (_, (p_token, _)) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine)
        resp = await client.post(REVIEW.format(meal_id), headers=_auth(p_token), json={})
        assert resp.status_code == 403, resp.text
        assert await _meal_status(db_engine, meal_id) == "REVIEW_REQUIRED"

    async def test_revoked_role_confers_nothing(self, client, seeded_db, db_engine):
        ((r_token, r_id), _) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine)
        await _revoke(db_engine, r_id, ContentRole.REVIEWER)

        resp = await client.post(REVIEW.format(meal_id), headers=_auth(r_token), json={})
        assert resp.status_code == 403, resp.text
        assert await _meal_status(db_engine, meal_id) == "REVIEW_REQUIRED"

    async def test_reviewer_grant_does_not_grant_publisher(self, client, seeded_db, db_engine):
        token, _, user_id = await register_and_login(client, "revonly@test.com")
        await _grant(db_engine, user_id, ContentRole.REVIEWER)
        async with _maker(db_engine)() as session:
            roles = await content_review_service.active_roles(session, uuid.UUID(user_id))
        assert roles == {"REVIEWER"}

    async def test_pending_queue_requires_staff(self, client, seeded_db, db_engine):
        token, _, _ = await register_and_login(client, "plain3@test.com")
        resp = await client.get(PENDING, headers=_auth(token))
        assert resp.status_code == 403, resp.text

        ((r_token, _), _) = await _reviewer_and_publisher(client, db_engine)
        await _add_meal(db_engine)
        resp = await client.get(PENDING, headers=_auth(r_token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["count"] >= 1

    async def test_history_requires_staff(self, client, seeded_db, db_engine):
        token, _, _ = await register_and_login(client, "plain4@test.com")
        meal_id = await _add_meal(db_engine)
        resp = await client.get(HISTORY.format(meal_id), headers=_auth(token))
        assert resp.status_code == 403, resp.text


# ── 5. identity is never taken from the body ──────────────────────────────


class TestIdentityNotTrusted:
    """A submitted email/user id/role must be rejected, not ignored.

    Run as an AUTHORISED reviewer: the point is that even a legitimate reviewer
    cannot smuggle a different actor or a role they do not hold into the
    request. (An unauthorised caller is refused with 403 before the body is
    even parsed.)
    """

    @pytest.mark.parametrize(
        "payload",
        [
            {"email": "pub@test.com"},
            {"user_id": "00000000-0000-4000-8000-000000000000"},
            {"role": "PUBLISHER"},
            {"actor_role": "PUBLISHER"},
            {"approved_by": "someone@example.com"},
        ],
    )
    async def test_extra_identity_fields_rejected(
        self, client, seeded_db, db_engine, payload
    ):
        ((r_token, _), _) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine)
        resp = await client.post(REVIEW.format(meal_id), headers=_auth(r_token), json=payload)
        assert resp.status_code == 422, resp.text
        assert await _meal_status(db_engine, meal_id) == "REVIEW_REQUIRED"

    async def test_unauthorised_caller_is_refused_before_body_parsing(
        self, client, seeded_db, db_engine
    ):
        token, _, _ = await register_and_login(client, "plain5@test.com")
        meal_id = await _add_meal(db_engine)
        resp = await client.post(
            REVIEW.format(meal_id), headers=_auth(token), json={"role": "PUBLISHER"}
        )
        assert resp.status_code == 403, resp.text
        assert await _meal_status(db_engine, meal_id) == "REVIEW_REQUIRED"

    async def test_recorded_actor_is_the_token_holder_not_the_body(
        self, client, seeded_db, db_engine
    ):
        ((r_token, r_id), _) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine)
        ok = await client.post(
            REVIEW.format(meal_id), headers=_auth(r_token), json={"rationale": "checked"}
        )
        assert ok.status_code == 200, ok.text
        history = await client.get(HISTORY.format(meal_id), headers=_auth(r_token))
        assert history.json()["transitions"][-1]["actor_id"] == r_id

    async def test_anonymous_cannot_review(self, client, seeded_db, db_engine):
        meal_id = await _add_meal(db_engine)
        resp = await client.post(REVIEW.format(meal_id), json={})
        assert resp.status_code == 401, resp.text


# ── 4. invalid transitions ────────────────────────────────────────────────


class TestInvalidTransitions:
    async def test_publish_without_review_is_refused(self, client, seeded_db, db_engine):
        (_, (p_token, _)) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine)
        resp = await client.post(PUBLISH.format(meal_id), headers=_auth(p_token), json={})
        assert resp.status_code == 409, resp.text
        assert resp.json()["error"]["details"]["blocking_code"] == "INVALID_TRANSITION"
        assert await _meal_status(db_engine, meal_id) == "REVIEW_REQUIRED"

    async def test_review_twice_is_refused(self, client, seeded_db, db_engine):
        ((r_token, _), _) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine)
        first = await client.post(REVIEW.format(meal_id), headers=_auth(r_token), json={})
        assert first.status_code == 200, first.text
        second = await client.post(REVIEW.format(meal_id), headers=_auth(r_token), json={})
        assert second.status_code == 409, second.text
        assert second.json()["error"]["details"]["from_status"] == "REVIEWED"

    async def test_retired_meal_cannot_be_published(self, client, seeded_db, db_engine):
        ((r_token, _), (p_token, _)) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine)
        await client.post(REVIEW.format(meal_id), headers=_auth(r_token), json={})
        retired = await client.post(RETIRE.format(meal_id), headers=_auth(r_token), json={})
        assert retired.status_code == 200, retired.text
        assert await _meal_status(db_engine, meal_id) == "RETIRED"

        resp = await client.post(PUBLISH.format(meal_id), headers=_auth(p_token), json={})
        assert resp.status_code == 409, resp.text

    async def test_unknown_meal_is_404(self, client, seeded_db, db_engine):
        ((r_token, _), _) = await _reviewer_and_publisher(client, db_engine)
        resp = await client.post(
            REVIEW.format("00000000-0000-4000-8000-000000000000"),
            headers=_auth(r_token),
            json={},
        )
        assert resp.status_code == 404, resp.text

    async def test_malformed_meal_id_is_404(self, client, seeded_db, db_engine):
        ((r_token, _), _) = await _reviewer_and_publisher(client, db_engine)
        resp = await client.post(REVIEW.format("not-a-uuid"), headers=_auth(r_token), json={})
        assert resp.status_code == 404, resp.text


# ── 4. content blockers ───────────────────────────────────────────────────


class TestContentBlockers:
    async def _attempt_review(self, client, db_engine, meal_id):
        ((r_token, _), _) = await _reviewer_and_publisher(client, db_engine)
        return await client.post(REVIEW.format(meal_id), headers=_auth(r_token), json={})

    async def test_missing_ingredients_blocks(self, client, seeded_db, db_engine):
        meal_id = await _add_meal(db_engine, ingredients=None)
        resp = await self._attempt_review(client, db_engine, meal_id)
        assert resp.status_code == 422, resp.text
        assert "MISSING_INGREDIENTS" in resp.json()["error"]["details"]["blocking_codes"]
        assert await _meal_status(db_engine, meal_id) == "REVIEW_REQUIRED"

    async def test_missing_nutrition_blocks(self, client, seeded_db, db_engine):
        meal_id = await _add_meal(db_engine, calories=0, protein_g=0, carbs_g=0, fat_g=0)
        resp = await self._attempt_review(client, db_engine, meal_id)
        assert resp.status_code == 422, resp.text
        assert "MISSING_NUTRITION_DATA" in resp.json()["error"]["details"]["blocking_codes"]

    async def test_missing_evidence_blocks(self, client, seeded_db, db_engine):
        meal_id = await _add_meal(db_engine, source=None, source_url=None)
        resp = await self._attempt_review(client, db_engine, meal_id)
        assert resp.status_code == 422, resp.text
        assert "MISSING_EVIDENCE" in resp.json()["error"]["details"]["blocking_codes"]

    async def test_missing_allergen_links_blocks(self, client, seeded_db, db_engine):
        # Peanut is detected from the ingredient but never linked: this is the
        # case that would otherwise serve an allergen to a user who declared it.
        meal_id = await _add_meal(
            db_engine,
            name="Peanut Rice",
            ingredients=[{"name": "Peanut", "quantity": "2 tbsp"}],
        )
        resp = await self._attempt_review(client, db_engine, meal_id)
        assert resp.status_code == 422, resp.text
        details = resp.json()["error"]["details"]
        assert "MISSING_ALLERGEN_LINKS" in details["blocking_codes"]
        blocker = next(b for b in details["blockers"] if b["code"] == "MISSING_ALLERGEN_LINKS")
        assert "peanut" in blocker["missing_categories"]

    async def test_linked_allergen_passes(self, client, seeded_db, db_engine):
        meal_id = await _add_meal(
            db_engine,
            name="Peanut Rice",
            ingredients=[{"name": "Peanut", "quantity": "2 tbsp"}],
        )
        await _link_allergen(db_engine, meal_id, "peanut", "Peanut")
        resp = await self._attempt_review(client, db_engine, meal_id)
        assert resp.status_code == 200, resp.text

    async def test_claim_in_benefits_blocks(self, client, seeded_db, db_engine):
        meal_id = await _add_meal(
            db_engine, benefits=["Clinically proven to prevent anaemia"]
        )
        resp = await self._attempt_review(client, db_engine, meal_id)
        assert resp.status_code == 422, resp.text
        details = resp.json()["error"]["details"]
        assert "UNSOURCED_CLINICAL_CLAIM" in details["blocking_codes"]
        blocker = next(b for b in details["blockers"] if b["code"] == "UNSOURCED_CLINICAL_CLAIM")
        assert blocker["violations"][0]["field"] == "benefits[]"

    async def test_claim_in_name_blocks(self, client, seeded_db, db_engine):
        meal_id = await _add_meal(db_engine, name="Clinically Approved Rice")
        resp = await self._attempt_review(client, db_engine, meal_id)
        assert resp.status_code == 422, resp.text
        assert "UNSOURCED_CLINICAL_CLAIM" in resp.json()["error"]["details"]["blocking_codes"]

    async def test_blocked_content_never_reaches_published(self, client, seeded_db, db_engine):
        ((r_token, _), (p_token, _)) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine, source=None)
        await client.post(REVIEW.format(meal_id), headers=_auth(r_token), json={})
        resp = await client.post(PUBLISH.format(meal_id), headers=_auth(p_token), json={})
        assert resp.status_code == 409  # REVIEW_REQUIRED -> PUBLISHED is illegal
        assert await _meal_status(db_engine, meal_id) == "REVIEW_REQUIRED"


# ── 4. separation of duties ───────────────────────────────────────────────


class TestSeparationOfDuties:
    async def test_same_actor_cannot_publish_what_they_reviewed(
        self, client, seeded_db, db_engine
    ):
        token, _, user_id = await register_and_login(client, "both@test.com")
        await _grant(db_engine, user_id, ContentRole.REVIEWER)
        await _grant(db_engine, user_id, ContentRole.PUBLISHER)
        meal_id = await _add_meal(db_engine)

        reviewed = await client.post(REVIEW.format(meal_id), headers=_auth(token), json={})
        assert reviewed.status_code == 200, reviewed.text

        resp = await client.post(PUBLISH.format(meal_id), headers=_auth(token), json={})
        assert resp.status_code == 409, resp.text
        assert resp.json()["error"]["details"]["blocking_code"] == "SELF_APPROVAL_FORBIDDEN"
        assert await _meal_status(db_engine, meal_id) == "REVIEWED"

    async def test_two_people_can_complete_the_workflow(self, client, seeded_db, db_engine):
        ((r_token, r_id), (p_token, p_id)) = await _reviewer_and_publisher(client, db_engine)
        assert r_id != p_id
        meal_id = await _add_meal(db_engine)

        reviewed = await client.post(
            REVIEW.format(meal_id), headers=_auth(r_token), json={"rationale": "checked"}
        )
        assert reviewed.status_code == 200, reviewed.text
        published = await client.post(
            PUBLISH.format(meal_id), headers=_auth(p_token), json={"rationale": "clinically ok"}
        )
        assert published.status_code == 200, published.text
        assert published.json()["content_status"] == "PUBLISHED"
        assert await _meal_status(db_engine, meal_id) == "PUBLISHED"

    async def test_policy_can_be_relaxed_in_development(
        self, client, seeded_db, db_engine, monkeypatch
    ):
        from app.config import settings

        monkeypatch.setattr(settings, "CONTENT_REQUIRE_SEPARATION_OF_DUTIES", False)
        token, _, user_id = await register_and_login(client, "solo@test.com")
        await _grant(db_engine, user_id, ContentRole.REVIEWER)
        await _grant(db_engine, user_id, ContentRole.PUBLISHER)
        meal_id = await _add_meal(db_engine)
        await client.post(REVIEW.format(meal_id), headers=_auth(token), json={})
        resp = await client.post(PUBLISH.format(meal_id), headers=_auth(token), json={})
        assert resp.status_code == 200, resp.text


# ── 3. transition ledger ──────────────────────────────────────────────────


class TestTransitionLedger:
    async def test_every_transition_records_actor_states_source_and_rationale(
        self, client, seeded_db, db_engine
    ):
        ((r_token, r_id), (p_token, p_id)) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine, source_url="https://www.who.int/meal", source=None)

        await client.post(
            REVIEW.format(meal_id), headers=_auth(r_token), json={"rationale": "ingredients verified"}
        )
        await client.post(
            PUBLISH.format(meal_id), headers=_auth(p_token), json={"rationale": "clinically appropriate"}
        )

        async with _maker(db_engine)() as session:
            records = await content_review_service.transitions_for_meal(session, uuid.UUID(meal_id))

        assert [r.to_status for r in records] == ["REVIEWED", "PUBLISHED"]
        assert [r.from_status for r in records] == ["REVIEW_REQUIRED", "REVIEWED"]

        review, publish = records
        assert str(review.actor_id) == r_id
        assert review.actor_role == "REVIEWER"
        assert review.rationale == "ingredients verified"
        assert str(publish.actor_id) == p_id
        assert publish.actor_role == "PUBLISHER"
        assert publish.rationale == "clinically appropriate"
        # source/version snapshot taken at decision time
        assert review.source_snapshot == "https://www.who.int/meal"
        assert review.evidence_version == "1"
        assert review.created_at is not None and publish.created_at is not None

    async def test_history_endpoint_exposes_the_ledger(self, client, seeded_db, db_engine):
        ((r_token, _), (p_token, _)) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine)
        await client.post(REVIEW.format(meal_id), headers=_auth(r_token), json={"rationale": "r"})
        await client.post(PUBLISH.format(meal_id), headers=_auth(p_token), json={"rationale": "p"})

        resp = await client.get(HISTORY.format(meal_id), headers=_auth(r_token))
        assert resp.status_code == 200, resp.text
        states = [t["to_status"] for t in resp.json()["transitions"]]
        assert states == ["REVIEWED", "PUBLISHED"]

    async def test_retire_records_from_and_to(self, client, seeded_db, db_engine):
        ((r_token, _), _) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine)
        await client.post(RETIRE.format(meal_id), headers=_auth(r_token), json={"rationale": "withdrawn"})

        resp = await client.get(HISTORY.format(meal_id), headers=_auth(r_token))
        record = resp.json()["transitions"][-1]
        assert record["from_status"] == "REVIEW_REQUIRED"
        assert record["to_status"] == "RETIRED"
        assert record["rationale"] == "withdrawn"


# ── visibility through the public/authenticated API ───────────────────────


class TestCatalogVisibility:
    async def test_only_published_content_is_served(self, client, seeded_db, db_engine):
        published_id = await _add_meal(db_engine, name="Published Rice", content_status="PUBLISHED")
        reviewed_id = await _add_meal(db_engine, name="Reviewed Rice", content_status="REVIEWED")
        await _add_meal(db_engine, name="Pending Rice")

        anon = await client.get("/api/v1/meals")
        assert anon.status_code == 200, anon.text
        names = {m["name"] for m in anon.json()}
        assert names == {"Published Rice"}
        assert all(m["content_status"] == "PUBLISHED" for m in anon.json())

        token, _, _ = await register_and_login(client, "reader@test.com")
        authorised = await client.get("/api/v1/meals", headers=_auth(token))
        assert {m["name"] for m in authorised.json()} == {"Published Rice"}

        assert published_id != reviewed_id

    async def test_content_becomes_visible_only_after_publication(self, client, seeded_db, db_engine):
        ((r_token, _), (p_token, _)) = await _reviewer_and_publisher(client, db_engine)
        meal_id = await _add_meal(db_engine, name="Workflow Rice")

        before = await client.get("/api/v1/meals")
        assert "Workflow Rice" not in {m["name"] for m in before.json()}

        await client.post(REVIEW.format(meal_id), headers=_auth(r_token), json={})
        still_hidden = await client.get("/api/v1/meals")
        assert "Workflow Rice" not in {m["name"] for m in still_hidden.json()}

        await client.post(PUBLISH.format(meal_id), headers=_auth(p_token), json={})
        after = await client.get("/api/v1/meals")
        assert "Workflow Rice" in {m["name"] for m in after.json()}


# ── safety order is preserved end to end ─────────────────────────────────


class TestSafetyPrecedesRanking:
    async def test_allergen_exclusion_still_runs_for_workflow_published_content(
        self, client, seeded_db, active_policy, db_engine
    ):
        """A meal published through the new workflow is still filtered by the
        server-side allergen exclusion before ranking."""
        ((r_token, _), (p_token, _)) = await _reviewer_and_publisher(client, db_engine)

        peanut_id = await _add_meal(
            db_engine,
            name="Peanut Curry",
            ingredients=[{"name": "Peanut", "quantity": "50 g"}],
        )
        await _link_allergen(db_engine, peanut_id, "peanut", "Peanut")
        safe_id = await _add_meal(db_engine, name="Plain Rice Bowl")

        for meal_id in (peanut_id, safe_id):
            reviewed = await client.post(REVIEW.format(meal_id), headers=_auth(r_token), json={})
            assert reviewed.status_code == 200, reviewed.text
            published = await client.post(PUBLISH.format(meal_id), headers=_auth(p_token), json={})
            assert published.status_code == 200, published.text

        token, _, _ = await register_and_login(client, "allergic@test.com")
        await _complete_profile(client, token)  # declares a peanut allergy

        resp = await client.post("/api/v1/diet/generate", headers=_auth(token), json={})
        assert resp.status_code == 201, resp.text
        names = json_names(resp.json())
        assert "Peanut Curry" not in names
        assert "Plain Rice Bowl" in names
