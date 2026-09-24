"""Who may see which content state over the public meal API.

Regression cover for a real production leak found after the review workflow
shipped: ``GET /api/v1/meals`` was configured by ``CONTENT_INCLUDE_STATUSES``
alone, and ``GET /api/v1/meals/{id}`` and ``/{id}/image`` had no visibility
check at all — an unauthenticated caller could read a ``REVIEW_REQUIRED``
meal, including its claims and cautions, straight out of the catalog.

The rule pinned here:

* anonymous and ordinary signed-in callers see ``PUBLISHED`` content only;
* unreviewed content is a 404 to them (a 403 would confirm the id exists);
* content staff (database-granted role) see their working set;
* production configuration can only ever tighten to ``PUBLISHED``.
"""

from __future__ import annotations

import uuid

from app.domain.content_roles import ContentRole
from app.domain.content_state import DEFAULT_INCLUDE_STATUSES, statuses_from_config
from app.domain.content_visibility import is_readable, readable_statuses
from app.models.meal_image import MealImage

from .conftest import register_and_login
from .test_config_security import _make_settings
from .test_content_review_workflow import _add_meal, _grant, _maker

# asyncio_mode = auto (pytest.ini); async tests need no explicit mark, which
# keeps the policy unit tests below warning-free.
LIST = "/api/v1/meals"
IMAGES = "/api/v1/meals/images/all"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _add_image(db_engine, meal_id: str, url: str = "https://img.example/x.png") -> None:
    async with _maker(db_engine)() as session:
        session.add(MealImage(meal_id=uuid.UUID(meal_id), image_url=url))
        await session.commit()


async def _visible_names(client, headers: dict[str, str] | None = None) -> set[str]:
    resp = await client.get(LIST, headers=headers or {})
    assert resp.status_code == 200, resp.text
    return {m["name"] for m in resp.json()}


# ── policy unit level ─────────────────────────────────────────────────────


def test_ordinary_callers_are_pinned_to_published():
    assert readable_statuses(["REVIEW_REQUIRED", "REVIEWED", "PUBLISHED"], False) == ["PUBLISHED"]
    assert readable_statuses(None, False) == ["PUBLISHED"]


def test_content_staff_get_the_configured_working_set():
    assert readable_statuses(["REVIEWED"], True) == ["REVIEWED"]
    assert readable_statuses(None, True) == ["PUBLISHED"]


def test_single_row_visibility():
    assert is_readable("PUBLISHED", False) is True
    assert is_readable("REVIEW_REQUIRED", False) is False
    assert is_readable("REVIEWED", False) is False
    assert is_readable(None, False) is False
    assert is_readable("REVIEW_REQUIRED", True) is True


def test_production_configuration_can_only_tighten(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "z" * 48)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com")

    for requested in ("REVIEW_REQUIRED,REVIEWED", "REVIEWED,PUBLISHED", "PUBLISHED", ""):
        monkeypatch.setenv("CONTENT_INCLUDE_STATUSES", requested)
        assert _make_settings(monkeypatch).CONTENT_INCLUDE_STATUSES == ["PUBLISHED"]


def test_development_configuration_may_widen(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("CONTENT_INCLUDE_STATUSES", "REVIEWED")
    assert _make_settings(monkeypatch).CONTENT_INCLUDE_STATUSES == ["REVIEWED"]

    monkeypatch.delenv("CONTENT_INCLUDE_STATUSES")
    assert _make_settings(monkeypatch).CONTENT_INCLUDE_STATUSES is None


def test_production_recommendation_states_are_published_only():
    for requested in ("REVIEWED,PUBLISHED", "REVIEW_REQUIRED", ""):
        assert statuses_from_config(requested, production=True) == {"PUBLISHED"}


def test_development_recommendation_states_still_widen():
    assert statuses_from_config("", production=False) == DEFAULT_INCLUDE_STATUSES
    assert statuses_from_config("REVIEW_REQUIRED", production=False) == {"REVIEW_REQUIRED"}


# ── API level: catalogue listing ──────────────────────────────────────────


class TestCatalogueListing:
    async def test_anonymous_listing_hides_unreviewed(self, client, seeded_db, db_engine):
        await _add_meal(db_engine, name="Pending Dish", content_status="REVIEW_REQUIRED")
        await _add_meal(db_engine, name="Approved Dish", content_status="PUBLISHED")

        assert await _visible_names(client) == {"Approved Dish"}

    async def test_ordinary_user_listing_hides_unreviewed(self, client, seeded_db, db_engine):
        await _add_meal(db_engine, name="Pending Dish", content_status="REVIEW_REQUIRED")
        await _add_meal(db_engine, name="Approved Dish", content_status="PUBLISHED")
        token, _, _ = await register_and_login(client, "plain.list@test.com")

        assert await _visible_names(client, _auth(token)) == {"Approved Dish"}

    async def test_content_staff_listing_includes_the_working_set(
        self, client, seeded_db, db_engine, monkeypatch
    ):
        from app.config import settings

        monkeypatch.setattr(
            settings, "CONTENT_INCLUDE_STATUSES", ["REVIEW_REQUIRED", "PUBLISHED"]
        )
        await _add_meal(db_engine, name="Pending Dish", content_status="REVIEW_REQUIRED")
        await _add_meal(db_engine, name="Approved Dish", content_status="PUBLISHED")

        token, _, uid = await register_and_login(client, "rev.list@test.com")
        await _grant(db_engine, uid, ContentRole.REVIEWER)

        assert await _visible_names(client, _auth(token)) == {"Pending Dish", "Approved Dish"}

    async def test_a_revoked_role_stops_widening(self, client, seeded_db, db_engine, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(
            settings, "CONTENT_INCLUDE_STATUSES", ["REVIEW_REQUIRED", "PUBLISHED"]
        )
        await _add_meal(db_engine, name="Pending Dish", content_status="REVIEW_REQUIRED")

        token, _, uid = await register_and_login(client, "revoked.list@test.com")
        await _grant(db_engine, uid, ContentRole.REVIEWER)
        assert await _visible_names(client, _auth(token)) == {"Pending Dish"}

        from app.services import content_review_service

        async with _maker(db_engine)() as session:
            await content_review_service.revoke_role(
                session, user_id=uuid.UUID(uid), role=ContentRole.REVIEWER
            )
            await session.commit()

        assert await _visible_names(client, _auth(token)) == set()


# ── API level: single meal ────────────────────────────────────────────────


class TestSingleMealVisibility:
    async def test_anonymous_cannot_read_unreviewed_meal(self, client, seeded_db, db_engine):
        meal_id = await _add_meal(db_engine, name="Pending Dish", content_status="REVIEW_REQUIRED")

        resp = await client.get(f"{LIST}/{meal_id}")
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_ordinary_user_cannot_read_unreviewed_meal(self, client, seeded_db, db_engine):
        meal_id = await _add_meal(db_engine, name="Pending Dish", content_status="REVIEW_REQUIRED")
        token, _, _ = await register_and_login(client, "plain.get@test.com")

        resp = await client.get(f"{LIST}/{meal_id}", headers=_auth(token))
        assert resp.status_code == 404, resp.text

    async def test_reviewed_but_unpublished_is_still_hidden(self, client, seeded_db, db_engine):
        """REVIEWED is a working state, not a public one."""
        meal_id = await _add_meal(db_engine, name="Reviewed Dish", content_status="REVIEWED")

        assert (await client.get(f"{LIST}/{meal_id}")).status_code == 404

    async def test_anonymous_can_read_published_meal(self, client, seeded_db, db_engine):
        meal_id = await _add_meal(db_engine, name="Approved Dish", content_status="PUBLISHED")

        resp = await client.get(f"{LIST}/{meal_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Approved Dish"

    async def test_content_staff_can_read_unreviewed_meal(self, client, seeded_db, db_engine):
        meal_id = await _add_meal(db_engine, name="Pending Dish", content_status="REVIEW_REQUIRED")
        token, _, uid = await register_and_login(client, "rev.get@test.com")
        await _grant(db_engine, uid, ContentRole.REVIEWER)

        resp = await client.get(f"{LIST}/{meal_id}", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        assert resp.json()["content_status"] == "REVIEW_REQUIRED"

    async def test_image_url_route_hides_unreviewed_meal(self, client, seeded_db, db_engine):
        """The image URL embeds the meal name, so it discloses content too."""
        meal_id = await _add_meal(db_engine, name="Pending Dish", content_status="REVIEW_REQUIRED")

        assert (await client.get(f"{LIST}/{meal_id}/image")).status_code == 404

        token, _, _ = await register_and_login(client, "plain.img@test.com")
        assert (
            await client.get(f"{LIST}/{meal_id}/image", headers=_auth(token))
        ).status_code == 404


# ── API level: cached image listing ───────────────────────────────────────


class TestImageListing:
    async def test_anonymous_still_requires_authentication(self, client, seeded_db):
        assert (await client.get(IMAGES)).status_code == 401

    async def test_ordinary_user_cannot_enumerate_unreviewed_images(
        self, client, seeded_db, db_engine
    ):
        pending = await _add_meal(db_engine, name="Pending Dish", content_status="REVIEW_REQUIRED")
        approved = await _add_meal(db_engine, name="Approved Dish", content_status="PUBLISHED")
        await _add_image(db_engine, pending, "https://img.example/pending.png")
        await _add_image(db_engine, approved, "https://img.example/approved.png")

        token, _, _ = await register_and_login(client, "plain.imgs@test.com")
        resp = await client.get(IMAGES, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        urls = {row["image_url"] for row in resp.json()}
        assert urls == {"https://img.example/approved.png"}

    async def test_content_staff_see_all_cached_images(self, client, seeded_db, db_engine):
        pending = await _add_meal(db_engine, name="Pending Dish", content_status="REVIEW_REQUIRED")
        await _add_image(db_engine, pending, "https://img.example/pending.png")

        token, _, uid = await register_and_login(client, "rev.imgs@test.com")
        await _grant(db_engine, uid, ContentRole.REVIEWER)

        resp = await client.get(IMAGES, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        assert {row["image_url"] for row in resp.json()} == {"https://img.example/pending.png"}


# ── API level: an invalid token is not an anonymous caller ────────────────


async def test_invalid_token_is_rejected_not_downgraded(client, seeded_db):
    resp = await client.get(LIST, headers=_auth("not-a-real-token"))
    assert resp.status_code == 401
