"""CRITICAL TEST 3 — contradictory trimester/week must be rejected."""

from __future__ import annotations

import pytest

from app.domain.gestational import (
    GestationalValidationError,
    trimester_for_week,
    validate_gestational_age,
)


@pytest.mark.parametrize("trimester,week", [
    (1, 1), (1, 13), (2, 14), (2, 26), (3, 27), (3, 42),
])
def test_valid_pairs_pass(trimester, week):
    validate_gestational_age(trimester, week)


@pytest.mark.parametrize("trimester,week", [
    (1, 14), (1, 30), (1, 0), (2, 13), (2, 27), (3, 26), (3, 43), (0, 10), (4, 30),
])
def test_contradictions_rejected(trimester, week):
    with pytest.raises(GestationalValidationError):
        validate_gestational_age(trimester, week)


def test_trimester_for_week():
    assert trimester_for_week(5) == 1
    assert trimester_for_week(20) == 2
    assert trimester_for_week(35) == 3
    with pytest.raises(GestationalValidationError):
        trimester_for_week(45)


def test_schema_allows_ranges_service_rejects_contradictions():
    """The Pydantic schema checks ranges; the service layer (and DB CHECK)
    enforce trimester↔week consistency. API-level rejection is covered in
    test_api_diet.py::test_contradictory_record_cannot_generate."""
    from app.schemas.health import HealthRecordCreate

    rec = HealthRecordCreate(trimester=1, week_number=30, current_weight_kg=60)
    assert rec.trimester == 1 and rec.week_number == 30
