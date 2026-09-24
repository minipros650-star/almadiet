"""Consent idempotency and clinical-claim policy coverage.

Consent: acceptance is a fact per (user, version) — repeating it must not append
a duplicate record, and the user always comes from the token.

Claims: the policy must cover every text field the meal response exposes, strip
claims on the import path, and detect (not silently rewrite) claims in fields
that identify the content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.database as database_module
from app.config import settings
from app.domain.clinical_claims import (
    INSPECTED_LIST_FIELDS,
    find_claim_violations,
    patient_visible_text_paths,
    sanitize_patient_fields,
)
from app.models.consent import Consent

from .conftest import register_and_login


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _maker(db_engine):
    return async_sessionmaker(db_engine, class_=database_module.AsyncSession, expire_on_commit=False)


# ── consent ───────────────────────────────────────────────────────────────


class TestConsentIdempotency:
    async def test_repeat_acceptance_does_not_append(self, client, db_engine):
        token, _, user_id = await register_and_login(client, "consent1@test.com")

        first = await client.post(
            "/api/v1/consent", headers=_auth(token), json={"consent_version": "2026-09-v1"}
        )
        assert first.status_code == 201, first.text
        assert first.json()["created"] is True

        second = await client.post(
            "/api/v1/consent", headers=_auth(token), json={"consent_version": "2026-09-v1"}
        )
        assert second.status_code == 201, second.text
        assert second.json()["created"] is False
        # Same record, not a new one.
        assert second.json()["accepted_at"] == first.json()["accepted_at"]

        async with _maker(db_engine)() as session:
            rows = (
                await session.execute(
                    select(func.count(Consent.id)).where(Consent.user_id == user_id)
                )
            ).scalar_one()
        assert rows == 1, "repeat acceptance appended a duplicate consent record"

    async def test_distinct_versions_are_distinct_rows(self, client, db_engine):
        token, _, user_id = await register_and_login(client, "consent2@test.com")
        for version in ("2026-09-v1", "2026-10-v1"):
            resp = await client.post(
                "/api/v1/consent", headers=_auth(token), json={"consent_version": version}
            )
            assert resp.status_code == 201, resp.text
        async with _maker(db_engine)() as session:
            count = (
                await session.execute(
                    select(func.count(Consent.id)).where(Consent.user_id == user_id)
                )
            ).scalar_one()
        assert count == 2

    @pytest.mark.parametrize(
        "payload",
        [
            {"consent_version": "2026-09-v1", "user_id": "00000000-0000-4000-8000-000000000000"},
            {"consent_version": "2026-09-v1", "email": "someone@example.com"},
        ],
    )
    async def test_consent_body_cannot_name_another_user(self, client, db_engine, payload):
        token, _, _ = await register_and_login(client, "consent3@test.com")
        resp = await client.post("/api/v1/consent", headers=_auth(token), json=payload)
        assert resp.status_code == 422, resp.text

    async def test_consent_rows_are_ownership_scoped(self, client, db_engine):
        tok_a, _, _ = await register_and_login(client, "consentA@test.com")
        tok_b, _, _ = await register_and_login(client, "consentB@test.com")

        await client.post("/api/v1/consent", headers=_auth(tok_a), json={"consent_version": "2026-09-v1"})

        a_state = await client.get("/api/v1/consent/current", headers=_auth(tok_a))
        b_state = await client.get("/api/v1/consent/current", headers=_auth(tok_b))
        assert a_state.json()["accepted"] is True
        assert b_state.json()["accepted"] is False, "one user's consent leaked to another"

    async def test_consent_requires_authentication(self, client, db_engine):
        resp = await client.post("/api/v1/consent", json={"consent_version": "2026-09-v1"})
        assert resp.status_code == 401, resp.text


# ── claim policy coverage ─────────────────────────────────────────────────


def _text_paths(model: Any, prefix: str = "") -> set[str]:
    """Every plain-text / list-of-text path the response model exposes."""
    paths: set[str] = set()
    for name, field in model.model_fields.items():
        annotation = field.annotation
        args = [a for a in get_args(annotation) if a is not type(None)]
        target = args[0] if args else annotation
        if target is str:
            paths.add(prefix + name)
        elif get_origin(target) is list:
            inner = get_args(target)
            if inner and inner[0] is str:
                paths.add(f"{prefix}{name}[]")
            elif inner and hasattr(inner[0], "model_fields"):
                paths |= _text_paths(inner[0], f"{prefix}{name}[].")
    return paths


class TestClaimPolicyCoverage:
    def test_every_response_text_field_is_covered(self):
        """The policy must have no blind spot in the response schema.

        Every text field the API returns is either sanitized/inspected by the
        policy or an explicitly justified derived value.
        """
        from app.domain.clinical_claims import DERIVED_PATIENT_PATHS
        from app.schemas.diet import MealResponse

        exposed = _text_paths(MealResponse)
        covered = patient_visible_text_paths()
        uncovered = exposed - covered - set(DERIVED_PATIENT_PATHS)
        assert not uncovered, f"patient-visible fields outside the claim policy: {sorted(uncovered)}"

    def test_derived_exemptions_are_only_non_text_catalog_values(self):
        """Anything exempted from the claim policy must be a catalog value."""
        from app.domain.clinical_claims import DERIVED_PATIENT_PATHS

        assert DERIVED_PATIENT_PATHS == {"allergens[]"}

    def test_key_patient_fields_are_covered(self):
        covered = patient_visible_text_paths()
        for field in (
            "name",
            "benefits[]",
            "cautions",
            "food_safety_notes",
            "best_time_to_eat",
            "substitutions[]",
            "trimester_suitability[]",
            "serving_size",
            "serving_basis",
            "ingredients[].name",
            "ingredients[].quantity",
        ):
            assert field in covered, f"{field} is not policed for clinical claims"

    def test_allergen_list_is_not_scanned(self):
        """Scanning it would lazily load the allergen relationship."""
        assert "allergens" not in INSPECTED_LIST_FIELDS
        assert "trimester_suitability" in INSPECTED_LIST_FIELDS


class TestClaimSanitization:
    def _meal(self, **overrides):
        from app.models.meal import Meal

        base = dict(
            name="Plain Rice",
            region="Kerala",
            meal_type="Lunch",
            calories=200,
            protein_g=6,
            carbs_g=30,
            fat_g=5,
            ingredients=[{"name": "Rice", "quantity": "1 cup"}],
            benefits=["Gentle on the stomach"],
            cautions=None,
            content_status="REVIEW_REQUIRED",
            source="Test source",
            evidence_version="1",
        )
        base.update(overrides)
        return Meal(**base)

    def test_benefits_are_sanitized(self):
        meal = self._meal(
            benefits=["Good source of energy", "Clinically proven to prevent anaemia"]
        )
        removed = sanitize_patient_fields(meal)
        assert meal.benefits == ["Good source of energy"]
        assert removed["benefits"] == ["Clinically proven to prevent anaemia"]

    def test_prose_cautions_are_sanitized(self):
        meal = self._meal(cautions="Eat fresh. Medically approved for daily use.")
        sanitize_patient_fields(meal)
        assert meal.cautions == "Eat fresh"

    def test_clean_content_is_untouched(self):
        meal = self._meal(benefits=["Good source of energy"], cautions="Eat fresh.")
        assert sanitize_patient_fields(meal) == {}
        assert meal.benefits == ["Good source of energy"]

    def test_claim_in_name_is_detected_not_rewritten(self):
        """Names identify the content: a claim there must block, not be edited."""
        meal = self._meal(name="Clinically Approved Rice")
        sanitize_patient_fields(meal)
        assert meal.name == "Clinically Approved Rice"
        violations = find_claim_violations(meal)
        assert any(v["field"] == "name" for v in violations)

    def test_claim_in_ingredients_is_detected(self):
        meal = self._meal(ingredients=[{"name": "Medically Validated Honey", "quantity": "1 tsp"}])
        violations = find_claim_violations(meal)
        assert any(v["field"] == "ingredients[].name" for v in violations)

    def test_sanitized_meal_has_no_remaining_violations(self):
        meal = self._meal(
            name="Plain Rice",
            benefits=["Clinically proven", "Good source of energy"],
            cautions="Doctor approved.",
            food_safety_notes="Cook thoroughly",
        )
        sanitize_patient_fields(meal)
        assert find_claim_violations(meal) == []


class TestImportAppliesClaimPolicy:
    async def test_import_strips_claims_from_benefits_and_cautions(
        self, db_session, tmp_path, monkeypatch
    ):
        from app.services.meal_service import seed_meals

        dataset = [
            {
                "id": "T1",
                "name": {"english": "Claim Test Rice"},
                "region": "Kerala",
                "meal_type": "Lunch",
                "trimester": ["First"],
                "nutrition_per_serving": {
                    "calories": 200,
                    "protein_g": 5,
                    "carbohydrates_g": 30,
                    "fat_g": 4,
                },
                "ingredients": [{"name": "Rice", "quantity": "1 cup"}],
                "benefits": ["Good source of energy", "Clinically proven to prevent anaemia"],
                "cautions": "Eat fresh. Medically approved for daily use.",
            }
        ]
        path = Path(tmp_path) / "dataset.json"
        path.write_text(json.dumps(dataset), encoding="utf-8")
        monkeypatch.setattr(settings, "MEALS_DATASET_PATH", str(path))

        seeded = await seed_meals(db_session)
        await db_session.commit()
        assert seeded == 1

        from app.models.meal import Meal

        meal = (await db_session.execute(select(Meal))).scalars().one()
        assert meal.benefits == ["Good source of energy"]
        assert meal.cautions == "Eat fresh"
        assert find_claim_violations(meal) == []
        # And it still lands in the review queue, never published.
        assert meal.content_status == "REVIEW_REQUIRED"

    async def test_import_cannot_bypass_the_claim_gate(self, db_session, tmp_path, monkeypatch):
        """Even a hostile dataset cannot import a claim into a patient field."""
        from app.services.meal_service import seed_meals

        dataset = [
            {
                "id": "T2",
                "name": {"english": "Innocent Rice"},
                "region": "Kerala",
                "meal_type": "Lunch",
                "trimester": ["First"],
                "nutrition_per_serving": {"calories": 150, "protein_g": 4},
                "ingredients": [{"name": "Rice", "quantity": "1 cup"}],
                "benefits": ["Medically validated", "Clinical AI approved"],
                "best_time_to_eat": "Clinically approved timing",
            }
        ]
        path = Path(tmp_path) / "hostile.json"
        path.write_text(json.dumps(dataset), encoding="utf-8")
        monkeypatch.setattr(settings, "MEALS_DATASET_PATH", str(path))

        await seed_meals(db_session)
        await db_session.commit()

        from app.models.meal import Meal

        meal = (await db_session.execute(select(Meal))).scalars().one()
        assert meal.benefits in ([], None)
        assert find_claim_violations(meal) == []
