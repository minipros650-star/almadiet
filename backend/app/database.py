"""
AlmaDiet — Async PostgreSQL Database Connection
Uses SQLAlchemy 2.0 async engine with asyncpg driver.
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator

from app.config import settings

# ── Async Engine with Connection Pooling ──────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
)

# ── Async Session Factory ─────────────────────────────────────
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Declarative Base ──────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dependency: Get DB Session ────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Create All Tables ─────────────────────────────────────────
async def create_tables():
    """Create all database tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine():
    """Dispose of the engine on shutdown."""
    await engine.dispose()
