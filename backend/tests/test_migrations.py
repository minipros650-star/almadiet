"""Migration tests — Alembic upgrades run from scratch and round-trip.

Runs against a scratch SQLite file. Uses Alembic's programmatic API so the
test works identically on Windows/Linux/macOS (python -m alembic is not a
reliable entry point on Windows Store Python).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_migrations_upgrade_from_scratch():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "scratch.db"
        url = f"sqlite+aiosqlite:///{db_path}"
        command.upgrade(_alembic_config(url), "head")
        assert db_path.exists()


def test_migrations_roundtrip_last_revision():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "scratch.db"
        url = f"sqlite+aiosqlite:///{db_path}"
        cfg = _alembic_config(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "-1")
        command.upgrade(cfg, "head")
        assert db_path.exists()
