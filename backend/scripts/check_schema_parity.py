"""Fail loudly when the live database drifts from the SQLAlchemy models.

backend/app/models is the contract every query is built from, and it maps 1:1
onto the tables in Supabase. Nothing verified that, so the catalog and identity
tables quietly fell out of step and production answered 500 with
`column meals.dataset_id does not exist` on /api/v1/meals — while the database
was missing the `users` table entirely, which broke every authenticated route.

Run after any schema change, or as a release/CI gate:

    DATABASE_URL=... python -m scripts.check_schema_parity

Exit codes: 0 = every model column exists, 1 = drift, 2 = misconfigured.

A *missing* model column is the failure that breaks queries. Undeclared
database columns/tables are reported as notices only — they are inert, and
flagging them as errors would make intentional extras (legacy_* rollback
artifacts) impossible to coexist with.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def expected_columns() -> dict[str, set[str]]:
    """Every table -> column pair declared by the SQLAlchemy models."""
    import app.models  # noqa: F401 — register every model with Base
    from app.database import Base

    return {t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables}


def diff_schema(
    expected: dict[str, set[str]], actual: dict[str, set[str]]
) -> tuple[list[str], list[str]]:
    """Compare model metadata against live introspection.

    Returns (drift, notices). `drift` is anything that would break a query.
    """
    drift: list[str] = []
    notices: list[str] = []

    for table in sorted(expected):
        if table not in actual:
            drift.append(f"missing table: {table}")
            continue
        missing = expected[table] - actual[table]
        if missing:
            drift.append(f"missing columns on {table}: {', '.join(sorted(missing))}")
        extra = actual[table] - expected[table]
        if extra:
            notices.append(f"undeclared columns on {table}: {', '.join(sorted(extra))}")

    for table in sorted(set(actual) - set(expected)):
        notices.append(f"undeclared table: {table}")

    return drift, notices


async def fetch_actual_columns(schema: str = "public") -> dict[str, set[str]]:
    """Introspect live columns, using the app's own engine and URL handling."""
    from sqlalchemy import text

    from app.database import engine

    query = text(
        "select table_name, column_name from information_schema.columns "
        "where table_schema = :schema"
    )
    actual: dict[str, set[str]] = {}
    async with engine.connect() as conn:
        rows = (await conn.execute(query, {"schema": schema})).all()
    for table_name, column_name in rows:
        actual.setdefault(table_name, set()).add(column_name)
    return actual


async def _run() -> int:
    from app.config import settings

    if not settings.DATABASE_URL.startswith("postgresql"):
        print(
            "ERROR: schema parity check needs a PostgreSQL DATABASE_URL "
            f"(got {settings.DATABASE_URL.split('://')[0]}://...).",
            file=sys.stderr,
        )
        return 2

    from app.database import close_engine

    expected = expected_columns()
    try:
        actual = await fetch_actual_columns()
    except Exception as exc:  # noqa: BLE001 — surfaced as a config error
        print(
            f"ERROR: could not read the schema from {settings.DATABASE_URL.split('@')[-1]}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    finally:
        await close_engine()

    drift, notices = diff_schema(expected, actual)

    checked = sum(len(cols) for cols in expected.values())
    print(f"checked {checked} model columns across {len(expected)} tables")

    for notice in notices:
        print(f"  notice: {notice}")

    if drift:
        print("\nSCHEMA DRIFT — the models expect columns the database lacks:")
        for problem in drift:
            print(f"  - {problem}")
        print("\nApply the missing migration before deploying.")
        return 1

    print("OK: every model column exists in the database")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
