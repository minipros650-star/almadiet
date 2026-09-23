"""AlmaDiet — Controlled schema migration command.

Run in a release/CI step against the target database:
    DATABASE_URL="postgresql+asyncpg://..." python -m scripts.migrate

NEVER invoked from request handling or FastAPI startup. Uses Alembic
(backend/alembic) — create_all is NOT used in production.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


async def _run_upgrade() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL is required to run migrations.", file=sys.stderr)
        sys.exit(2)

    # Normalize Supabase connection strings for Alembic's sync psycopg driver.
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
    print("Migrations applied: head")


if __name__ == "__main__":
    asyncio.run(_run_upgrade())
