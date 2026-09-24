"""AlmaDiet — Controlled schema migration command.

Run in a release/CI step against the target database:
    DATABASE_URL="postgresql+asyncpg://..." python -m scripts.migrate

NEVER invoked from request handling or FastAPI startup. Uses Alembic
(backend/alembic) — create_all is NOT used in production.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL is required to run migrations.", file=sys.stderr)
        sys.exit(2)

    from alembic import command
    from alembic.config import Config

    from app.config import normalize_database_url

    # backend/alembic/env.py builds the engine with async_engine_from_config, so
    # the URL must name an ASYNC driver. A stock Supabase/provider URI says
    # `postgresql://`, which SQLAlchemy resolves to the sync psycopg2 driver
    # this project deliberately does not ship; the shared normalizer rewrites it
    # to asyncpg and drops the pooler-only query parameters (e.g.
    # `?pgbouncer=true`) that asyncpg rejects. This step previously rewrote the
    # URL the other way, to `postgresql://`, for a "sync psycopg driver" that is
    # not a dependency — so `python -m scripts.migrate` could never work.
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", normalize_database_url(database_url))

    # env.py drives the migration through asyncio.run() itself, so this must
    # stay a plain synchronous call. Wrapping it in asyncio.run() here raised
    # "asyncio.run() cannot be called from a running event loop".
    command.upgrade(cfg, "head")
    print("Migrations applied: head")


if __name__ == "__main__":
    main()
