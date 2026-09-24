"""Schema-parity guard — the models must not drift from the live database.

The diff logic is covered unconditionally. The live check runs only when
DATABASE_URL names a real PostgreSQL instance (CI / release), and skips under
the hermetic SQLite test database.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from scripts.check_schema_parity import diff_schema, expected_columns


def test_expected_columns_cover_the_tables_that_broke():
    """Regression: these are the tables whose drift 500'd production."""
    expected = expected_columns()
    for table in (
        "users",
        "meals",
        "allergens",
        "meal_allergens",
        "health_records",
        "consents",
        "audit_logs",
    ):
        assert table in expected, f"{table} missing from model metadata"
    assert "dataset_id" in expected["meals"]
    assert "category" in expected["allergens"]
    assert "matched_term" in expected["meal_allergens"]
    assert "trimester" in expected["health_records"]
    assert "event_code" in expected["audit_logs"]


def test_expected_columns_is_non_trivial():
    expected = expected_columns()
    assert len(expected) >= 15
    assert sum(len(cols) for cols in expected.values()) >= 100


def test_diff_schema_reports_missing_table():
    drift, notices = diff_schema({"meals": {"id"}}, {})
    assert drift == ["missing table: meals"]
    assert notices == []


def test_diff_schema_reports_missing_column():
    drift, _ = diff_schema({"meals": {"id", "dataset_id"}}, {"meals": {"id"}})
    assert drift == ["missing columns on meals: dataset_id"]


def test_diff_schema_treats_undeclared_columns_as_notices():
    """Legacy extras must not fail the check — only missing model columns do."""
    drift, notices = diff_schema(
        {"meals": {"id"}}, {"meals": {"id", "description"}, "legacy_meals": {"id"}}
    )
    assert drift == []
    assert any("description" in n for n in notices)
    assert any("legacy_meals" in n for n in notices)


def test_diff_schema_clean_when_identical():
    drift, notices = diff_schema({"meals": {"id", "name"}}, {"meals": {"name", "id"}})
    assert drift == []
    assert notices == []


def _live_postgres_url() -> str | None:
    url = os.environ.get("DATABASE_URL", "")
    return url if url.startswith("postgresql") else None


@pytest.mark.skipif(
    _live_postgres_url() is None,
    reason="needs a PostgreSQL DATABASE_URL (set one to check a real database)",
)
def test_live_database_matches_models():
    from scripts.check_schema_parity import fetch_actual_columns

    actual = asyncio.run(fetch_actual_columns())
    drift, _ = diff_schema(expected_columns(), actual)
    assert drift == [], "schema drift:\n" + "\n".join(drift)
