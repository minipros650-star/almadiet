"""Regression guards for the release-step migration runner.

`python -m scripts.migrate` had two independent bugs that made it impossible to
run anywhere: it rewrote the URL to the sync `postgresql://` scheme for a
psycopg2 driver that is not a dependency (while alembic/env.py builds an async
engine), and it wrapped the Alembic call in `asyncio.run()` even though env.py
calls `asyncio.run()` itself.
"""

from __future__ import annotations

import asyncio

import pytest

import scripts.migrate as migrate


def test_migrate_hands_alembic_an_async_driver_url(monkeypatch):
    captured: dict[str, str] = {}

    def fake_upgrade(cfg, revision):  # noqa: ANN001
        captured["url"] = cfg.get_main_option("sqlalchemy.url")
        captured["revision"] = revision

    monkeypatch.setattr("alembic.command.upgrade", fake_upgrade)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://u:p@host:6543/postgres?pgbouncer=true"
    )

    migrate.main()

    # asyncpg scheme (env.py builds an async engine) and the pooler-only
    # parameter dropped, since asyncpg.connect() would reject it.
    assert captured["url"] == "postgresql+asyncpg://u:p@host:6543/postgres"
    assert captured["revision"] == "head"


def test_migrate_keeps_sqlite_urls_untouched(monkeypatch):
    captured: dict[str, str] = {}

    def fake_upgrade(cfg, revision):  # noqa: ANN001
        captured["url"] = cfg.get_main_option("sqlalchemy.url")

    monkeypatch.setattr("alembic.command.upgrade", fake_upgrade)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    migrate.main()

    assert captured["url"] == "sqlite+aiosqlite:///:memory:"


def test_migrate_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as exc:
        migrate.main()
    assert exc.value.code == 2


def test_migrate_is_not_wrapped_in_an_event_loop():
    """env.py calls asyncio.run(); nesting it raised a RuntimeError."""
    assert not asyncio.iscoroutinefunction(migrate.main)
