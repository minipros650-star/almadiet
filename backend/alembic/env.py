"""Alembic environment — reads DATABASE_URL from app config."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — register all models with Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the database URL: an explicitly configured URL (CLI override or
# programmatic use in tests) wins; otherwise fall back to app settings.
_URL_PLACEHOLDER = "driver://user:pass@localhost/dbname"
_ini_url = config.get_main_option("sqlalchemy.url")
if not _ini_url or _ini_url == _URL_PLACEHOLDER:
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def _db_url() -> str:
    return config.get_main_option("sqlalchemy.url")


def _run_migrations_offline() -> None:
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_db_url().startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=_db_url().startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    _run_migrations_offline()
else:
    run_migrations_online()
