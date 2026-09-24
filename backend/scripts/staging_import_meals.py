"""AlmaDiet — STAGING-ONLY meal catalog import (fail-closed).

This is the deliberate, guarded entry point for importing the meal dataset
into a NON-production database. It refuses to run against the production
Supabase project unless the operator sets an explicit, unambiguous override.

The import itself is the project's own ``meal_service.seed_meals`` — never
hand-written SQL — so the real allergen matching and clinical-claim stripping
run exactly as they do in the application. Every imported row lands in
``REVIEW_REQUIRED``; nothing is auto-published.

After importing it verifies the four governance invariants and exits non-zero
if any of them fails:

  1. every imported meal is REVIEW_REQUIRED (never PUBLISHED/REVIEWED);
  2. allergen links are complete with respect to the safety matcher used by
     ``meal_safety_service`` (a missing link would serve an allergen to a
     user who declared it) and every link resolves to a real catalog row;
  3. no unsourced clinical claim survives in any free-text field;
  4. the imported content is invisible to ordinary users (PUBLISHED-only
     queries return nothing).

Usage (staging only):

    STAGING_IMPORT_CONFIRM=yes \
    DATABASE_URL="postgresql+asyncpg://...staging..." \
        python -m scripts.staging_import_meals

    python -m scripts.staging_import_meals --verify-only   # re-check existing data
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import normalize_database_url, settings  # noqa: E402
from app.database import async_session_maker  # noqa: E402

# The production Supabase project ref. Importing diet content into production
# requires an explicit human decision, never an accident of environment.
PRODUCTION_PROJECT_REFS = ("ipquqyzlqugalmhfhfbt",)
PRODUCTION_OVERRIDE = "I-ACCEPT-PRODUCTION-IMPORT"


class ProductionImportRefused(RuntimeError):
    """Raised when an import would touch the production database."""


def assert_target_is_staging(database_url: str, override: str | None = None) -> None:
    """Fail closed unless the target is clearly NOT production."""
    url = (database_url or "").lower()
    if not url:
        raise ProductionImportRefused("DATABASE_URL is not set — refusing to guess a target.")
    if any(ref in url for ref in PRODUCTION_PROJECT_REFS):
        if override != PRODUCTION_OVERRIDE:
            raise ProductionImportRefused(
                "Refusing to import meal content into the PRODUCTION database. "
                f"Target a staging database, or set IMPORT_OVERRIDE={PRODUCTION_OVERRIDE} "
                "if you have explicitly approved a production import."
            )
    if override and override != PRODUCTION_OVERRIDE:            raise ProductionImportRefused("Unrecognized IMPORT_OVERRIDE value.")


async def fetch_import_state(db) -> dict:
    """Collect everything the invariant checks need, in one pass."""
    from sqlalchemy import select

    from app.domain.allergens import AllergenCategory, allergens_for_ingredients
    from app.models.allergen import Allergen, MealAllergen
    from app.models.meal import Meal

    meals = (await db.execute(select(Meal))).scalars().all()
    links = (await db.execute(select(MealAllergen))).scalars().all()
    allergens = (await db.execute(select(Allergen))).scalars().all()

    catalog = {a.id: a.category for a in allergens}
    valid_categories = {c.value for c in AllergenCategory}
    by_meal: dict[str, list] = {}
    for link in links:
        by_meal.setdefault(str(link.meal_id), []).append(link)

    return {
        "meals": meals,
        "links": links,
        "catalog": catalog,
        "valid_categories": valid_categories,
        "by_meal": by_meal,
        "detect": allergens_for_ingredients,
    }


def check_import_state(state: dict) -> tuple[bool, list[str], dict]:
    """Run the four governance invariants against collected state."""
    meals, links = state["meals"], state["links"]
    catalog, valid_categories, by_meal = state["catalog"], state["valid_categories"], state["by_meal"]
    detect = state["detect"]

    from app.services.meal_service import BANNED_CLAIMS

    problems: list[str] = []
    report: dict = {"meals": len(meals), "allergen_links": len(links)}

    # 1 ── nothing imported may be beyond REVIEW_REQUIRED
    statuses: dict[str, int] = {}
    for m in meals:
        statuses[str(m.content_status)] = statuses.get(str(m.content_status), 0) + 1
    report["statuses"] = statuses
    if set(statuses) - {"REVIEW_REQUIRED"}:
        problems.append(f"imported meals are not all REVIEW_REQUIRED: {statuses}")
    if meals and statuses.get("REVIEW_REQUIRED", 0) != len(meals):
        problems.append("some imported meals skipped the review queue")

    # 2 ── allergen links: valid rows AND complete vs. the safety matcher
    dangling, bad_term, bad_category = [], [], []
    incomplete: list[str] = []
    for link in links:
        if link.allergen_id not in catalog:
            dangling.append(str(link.meal_id))
            continue
        if not (link.matched_term or "").strip():
            bad_term.append(str(link.meal_id))
        if catalog[link.allergen_id] not in valid_categories:
            bad_category.append(str(link.meal_id))

    for m in meals:
        expected = set(detect(m.ingredients or []))
        expected |= set(detect([{"name": m.name}]))
        present = {catalog.get(l.allergen_id) for l in by_meal.get(str(m.id), [])}
        missing = {c for c in expected if c not in present}
        if missing:
            incomplete.append(f"{m.name}: {sorted(missing)}")

    report.update(dangling=dangling, incomplete=incomplete,
                  bad_term=bad_term, bad_category=bad_category)
    if dangling:
        problems.append(f"{len(dangling)} allergen link(s) reference a missing catalog row")
    if bad_term:
        problems.append(f"{len(bad_term)} allergen link(s) have an empty matched_term")
    if bad_category:
        problems.append(f"{len(bad_category)} allergen link(s) use an unknown category")
    if incomplete:
        problems.append(
            f"{len(incomplete)} meal(s) are MISSING allergen links for allergens the "
            f"safety matcher detects — e.g. {incomplete[:3]}"
        )

    # 3 ── no unsourced clinical claims anywhere in free text
    claims: list[str] = []
    for m in meals:
        for field in ("cautions", "best_time_to_eat", "name"):
            text = str(getattr(m, field, "") or "").lower()
            for claim in BANNED_CLAIMS:
                if claim in text:
                    claims.append(f"{m.name}.{field}:{claim}")
        for benefit in (m.benefits or []):
            for claim in BANNED_CLAIMS:
                if claim in str(benefit).lower():
                    claims.append(f"{m.name}.benefits:{claim}")
    report["banned_claims"] = claims
    if claims:
        problems.append(f"{len(claims)} unsourced clinical claim(s) survived the import")

    return (not problems), problems, report


async def count_visible_to_ordinary_users(db) -> int:
    """How many imported rows a normal user can see (must be 0 pre-approval)."""
    from app.services.meal_service import get_meals

    visible = await get_meals(db, include_statuses=["PUBLISHED"], limit=1000)
    return len(visible)


async def main() -> int:
    verify_only = "--verify-only" in sys.argv

    if os.getenv("DATABASE_URL"):
        settings.DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", ""))
        import importlib

        import app.database as database_module

        importlib.reload(database_module)
        global async_session_maker
        async_session_maker = database_module.async_session_maker

    try:
        assert_target_is_staging(
            settings.DATABASE_URL,
            override=os.getenv("IMPORT_OVERRIDE"),
        )
    except ProductionImportRefused as exc:
        print(f"REFUSED: {exc}")
        return 3

    if not verify_only and os.getenv("STAGING_IMPORT_CONFIRM") != "yes":
        print("REFUSED: set STAGING_IMPORT_CONFIRM=yes to confirm a staging import.")
        return 3

    async with async_session_maker() as db:
        if not verify_only:
            from app.services.meal_service import get_meal_count, seed_meals

            existing = await get_meal_count(db)
            if existing:
                print(f"Target already holds {existing} meals — nothing imported.")
            else:
                seeded = await seed_meals(db)
                await db.commit()
                print(f"Imported {seeded} meals (all REVIEW_REQUIRED).")

        state = await fetch_import_state(db)
        ok, problems, report = check_import_state(state)
        visible = await count_visible_to_ordinary_users(db)

    print("\n== import verification " + "=" * 30)
    print(f"  meals                     : {report['meals']}")
    print(f"  allergen links            : {report['allergen_links']}")
    print(f"  statuses                  : {report['statuses']}")
    print(f"  incomplete allergen links : {len(report['incomplete'])}")
    print(f"  dangling links            : {len(report['dangling'])}")
    print(f"  unsourced claims          : {len(report['banned_claims'])}")
    print(f"  visible to a normal user  : {visible}")
    if visible:
        problems.append(f"{visible} imported meal(s) are already visible to ordinary users")
        ok = False
    print("  result                    : " + ("PASS" if ok else "FAIL"))
    for problem in problems:
        print(f"    - {problem}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
