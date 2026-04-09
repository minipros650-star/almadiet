"""
AlmaDiet — FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import create_tables, close_engine, async_session_maker
from app.models import *  # noqa: Register all models with Base
from app.services.meal_service import get_meal_count, seed_meals

logger = logging.getLogger("almadiet")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # ── Startup ──
    logger.info("🚀 Starting AlmaDiet Backend...")
    await create_tables()
    logger.info("✅ Database tables created/verified")

    # Seed meals if database is empty
    async with async_session_maker() as db:
        count = await get_meal_count(db)
        if count == 0:
            try:
                seeded = await seed_meals(db)
                await db.commit()
                logger.info(f"🍛 Seeded {seeded} meals into database")
            except FileNotFoundError as e:
                logger.warning(f"⚠️ Meal dataset not found: {e}")
        else:
            logger.info(f"🍛 {count} meals already in database")

    yield

    # ── Shutdown ──
    await close_engine()
    logger.info("👋 AlmaDiet Backend shut down")


app = FastAPI(
    title="AlmaDiet API",
    description="Pregnancy Diet Recommendation System — Personalized, trimester-specific, South Indian meal planning powered by ML.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
import os
_cors_origins = os.getenv("ALLOWED_ORIGINS", "*")
_origins = ["*"] if _cors_origins == "*" else [o.strip() for o in _cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include Routers ───────────────────────────────────────────
from app.routers.auth_router import router as auth_router
from app.routers.health_router import router as health_router
from app.routers.diet_router import router as diet_router
from app.routers.emergency_router import router as emergency_router
from app.routers.meal_router import router as meal_router
from app.routers.image_router import router as image_router

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(diet_router)
app.include_router(emergency_router)
app.include_router(meal_router)
app.include_router(image_router)

# ── Static Files (serve generated meal images) ────────────────
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _Path
_img_dir = _Path(settings.IMAGE_STORAGE_DIR)
_img_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/meal_images", StaticFiles(directory=str(_img_dir)), name="meal_images")


@app.get("/", tags=["Root"])
async def root():
    return {
        "app": "AlmaDiet",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Root"])
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
