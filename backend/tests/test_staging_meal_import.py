"""Staging meal import — governance invariants.

Proves, without touching production, that an import through the project's own
``seed_meals`` path lands every meal in the review queue, produces allergen
links that are complete with respect to the safety matcher, carries no
unsourced clinical claims, and stays invisible until a clinician approves it.
"""

from __future__ import annotations

import pytest

from scripts.staging_import_meals import (
    PRODUCTION_OVERRIDE,
    ProductionImportRefused,
    assert_target_is_staging,
    check_import_state,
    count_visible_to_ordinary_users,
    fetch_import_state,
)

PROD_URL = "postgresql+asyncpg://postgres:pw@db.ipquqyzlqugalmhfhfbt.supabase.co:5432/postgres"
STAGING_URL = "postgresql+asyncpg://postgres:pw@db.abcdefghijklmnopqrst.supabase.co:5432/postgres"


# ── fail-closed target guard ──────────────────────────────────────────────
def test_refuses_production_target():
    with pytest.raises(ProductionImportRefused):
        assert_target_is_staging(PROD_URL)


def test_refuses_when_target_unknown():
    with pytest.raises(ProductionImportRefused):
        assert_target_is_staging("")


def test_allows_staging_target():
    assert_target_is_staging(STAGING_URL)  # must not raise


def test_production_import_requires_explicit_override():
    with pytest.raises(ProductionImportRefused):
        assert_target_is_staging(PROD_URL, override="yes please")
    assert_target_is_staging(PROD_URL, override=PRODUCTION_OVERRIDE)  # must not raise


# ── import invariants ─────────────────────────────────────────────────────
async def _import(db_session) -> int:
    from app.services.meal_service import seed_meals

    seeded = await seed_meals(db_session)
    await db_session.commit()
    return seeded


async def test_import_populates_the_catalog(db_session):
    seeded = await _import(db_session)
    assert seeded > 0, "the dataset should import at least one meal"


async def test_every_imported_meal_lands_in_review_required(db_session):
    from sqlalchemy import select

    from app.models.meal import Meal

    await _import(db_session)
    statuses = {
        m.content_status for m in (await db_session.execute(select(Meal))).scalars().all()
    }
    assert statuses == {"REVIEW_REQUIRED"}, f"imported content escaped the review queue: {statuses}"


async def test_imported_rows_are_never_attributed_to_a_reviewer(db_session):
    from sqlalchemy import select

    from app.models.meal import Meal

    await _import(db_session)
    for meal in (await db_session.execute(select(Meal))).scalars().all():
        assert not meal.approved_by, f"{meal.name} was auto-approved ({meal.approved_by})"
        assert meal.approved_at is None, f"{meal.name} carries an approval timestamp"


async def test_import_invariants_hold(db_session):
    await _import(db_session)
    state = await fetch_import_state(db_session)
    ok, problems, report = check_import_state(state)

    assert report["meals"] > 0
    assert not report["dangling"], "allergen links must resolve to the allergen catalog"
    assert not report["bad_term"], "allergen links must record what matched"
    assert not report["bad_category"], "allergen links must use known categories"
    assert not report["incomplete"], (
        "every allergen the safety matcher detects in a meal must have a link, "
        f"or the exclusion filter cannot protect that user: {report['incomplete'][:3]}"
    )
    assert not report["banned_claims"], (
        f"unsourced clinical claims must not survive import: {report['banned_claims'][:3]}"
    )
    assert ok, problems


async def test_allergen_links_point_at_the_shared_catalog(db_session):
    from sqlalchemy import select

    from app.domain.allergens import AllergenCategory
    from app.models.allergen import Allergen, MealAllergen

    await _import(db_session)
    catalog_ids = {a.id for a in (await db_session.execute(select(Allergen))).scalars().all()}
    links = (await db_session.execute(select(MealAllergen))).scalars().all()
    assert links, "an import of real recipes should produce allergen links"
    assert all(link.allergen_id in catalog_ids for link in links)
    categories = {a.category for a in (await db_session.execute(select(Allergen))).scalars().all()}
    assert categories <= {c.value for c in AllergenCategory}


# ── visibility gate ───────────────────────────────────────────────────────
async def test_imported_content_is_invisible_to_ordinary_users(db_session):
    await _import(db_session)
    assert await count_visible_to_ordinary_users(db_session) == 0


async def test_approved_content_is_the_only_thing_that_becomes_visible(db_session):
    from sqlalchemy import select

    from app.models.meal import Meal
    from app.services.meal_service import approve_meal, get_meals

    await _import(db_session)
    meal = (await db_session.execute(select(Meal))).scalars().first()

    # A reviewer's step: move the meal through the review state.
    meal.content_status = "REVIEWED"
    await db_session.commit()
    assert await get_meals(db_session, include_statuses=["PUBLISHED"]) == []

    approved = await approve_meal(db_session, meal.id, reviewer="clinician@almadiet.test")
    await db_session.commit()
    assert approved.content_status == "PUBLISHED"
    assert approved.approved_by == "clinician@almadiet.test"
    assert approved.approved_at is not None

    visible = await get_meals(db_session, include_statuses=["PUBLISHED"])
    assert [m.id for m in visible] == [meal.id]


@pytest.mark.xfail(
    strict=True,
    reason="No endpoint or service moves a meal from REVIEW_REQUIRED to REVIEWED, so "
           "approve_meal() cannot promote freshly imported content: the clinician "
           "approval path is unpassable and imported meals stay invisible forever.",
)
async def test_clinician_can_promote_a_freshly_imported_meal(db_session):
    from sqlalchemy import select

    from app.models.meal import Meal
    from app.services.meal_service import approve_meal, get_meals

    await _import(db_session)
    meal = (await db_session.execute(select(Meal))).scalars().first()

    approved = await approve_meal(db_session, meal.id, reviewer="clinician@almadiet.test")
    await db_session.commit()

    assert approved.content_status == "PUBLISHED"
    assert [m.id for m in await get_meals(db_session, include_statuses=["PUBLISHED"])] == [meal.id]
