"""AlmaDiet — Idempotent meal catalog seeding (explicit admin command).

Run manually against a target database:
    DATABASE_URL="postgresql+asyncpg://..." python -m scripts.seed_meals

Safe to re-run: existing meals are left untouched; only an EMPTY catalog is
populated (mirroring the dev lifespan guard). Seeded meals are REVIEW_REQUIRED
— they never bypass clinician approval.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.database import async_session_maker  # noqa: E402
from app.services.meal_service import get_meal_count, seed_meals  # noqa: E402


async def main() -> None:
    # Allow DATABASE_URL override without touching config defaults.
    if os.getenv("DATABASE_URL"):
        settings.DATABASE_URL = os.getenv("DATABASE_URL")  # type: ignore[attr-defined]
        import importlib

        import app.database as database_module

        importlib.reload(database_module)
        global async_session_maker  # noqa: F823
        async_session_maker = database_module.async_session_maker  # type: ignore[name-defined]

    async with async_session_maker() as db:
        count = await get_meal_count(db)
        if count > 0:
            print(f"Catalog not empty ({count} meals) — nothing seeded.")
            return
        seeded = await seed_meals(db)
        await db.commit()
        print(f"Seeded {seeded} meals (REVIEW_REQUIRED — approval required before use).")


if __name__ == "__main__":
    asyncio.run(main())
