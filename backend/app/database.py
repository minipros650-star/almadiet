"""
AlmaDiet — Async database connection.

Supports PostgreSQL (production) and SQLite (tests) via the asyncpg/aiosqlite
drivers. The engine is created lazily so importing config never opens sockets.
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import CHAR, TypeDecorator

from app.config import settings


class GUID(TypeDecorator):
    """Platform-independent UUID type: PG UUID, CHAR(32) elsewhere."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return str(value).replace("-", "")

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, __import__("uuid").UUID):
            return value
        return __import__("uuid").UUID(value)


# JSONB on PostgreSQL, JSON on SQLite (tests).
JSONType = JSONB().with_variant(JSON(), "sqlite")


def _anonymous_statement_name() -> str:
    """Return the empty statement name — i.e. request an UNNAMED statement.

    asyncpg names statements in ``Connection._get_statement``::

        if isinstance(named, str):
            stmt_name = named
        elif use_cache or named:
            stmt_name = self._get_unique_id('stmt')   # __asyncpg_stmt_N__
        else:
            stmt_name = ''

    SQLAlchemy's asyncpg dialect executes every statement through ``await
    connection.prepare(operation, name=self._prepared_statement_name_func())``,
    and its default function returns ``None``, which asyncpg converts to
    ``named=True`` — so every statement is NAMED, unconditionally.
    ``statement_cache_size=0`` only disables asyncpg's *internal* cache, which
    the dialect bypasses by calling ``prepare()`` directly, so it never
    prevented this.

    Named statements live in one PostgreSQL backend's memory. PgBouncer in
    transaction mode hands the client a different backend after each
    transaction, so a name is either missing or already taken — surfacing as
    intermittent ``DuplicatePreparedStatementError`` (the production failure)
    or ``InvalidSQLStatementNameError``. Because a fresh process restarts
    asyncpg's name counter, every serverless cold start re-issues
    ``__asyncpg_stmt_1__`` and collides again immediately.

    ``''`` takes the ``isinstance(named, str)`` branch above, producing a
    genuinely anonymous statement: no name to collide, and nothing accumulates
    server-side. SQLAlchemy's documented alternative — ``NullPool`` plus unique
    names such as ``f"__asyncpg_{uuid4()}__"`` — also stops the collisions, but
    its own docs warn it "buildup[s] useless prepared statements", cleaned up
    only by ``DISCARD ALL`` on the pooler. Supabase manages that PgBouncer, so
    anonymous statements are the fix we can actually guarantee.
    """
    return ""


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {}
    # Supabase PgBouncer / transaction pooling. All three are needed:
    # statement_cache_size=0 silences asyncpg's cache, and
    # _anonymous_statement_name stops the dialect from creating NAMED
    # statements that PgBouncer cannot keep coherent (see its docstring).
    return {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": _anonymous_statement_name,
    }


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # never echo SQL in prod logs (may contain bound values)
    pool_pre_ping=True,
    connect_args=_connect_args(settings.DATABASE_URL),
)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency providing an async session with commit/rollback."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Dev/test-only schema creation. Production MUST use Alembic
    (`alembic upgrade head`) — enforced in main.py startup."""
    # Register all models with Base before creating tables.
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine() -> None:
    await engine.dispose()
