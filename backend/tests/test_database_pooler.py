"""Regression guards for Supabase PgBouncer / transaction-pooling compatibility.

Production intermittently returned 500 from /api/v1/meals:

    asyncpg.exceptions.DuplicatePreparedStatementError:
    prepared statement "__asyncpg_stmt_7__" already exists

SQLAlchemy's asyncpg dialect runs every statement through
`connection.prepare(operation, name=<name func>())`, and its default name
function returns None, which asyncpg turns into `named=True` — a NAMED
server-side statement every single time. `statement_cache_size=0` only disables
asyncpg's internal cache, which the dialect bypasses, so it never prevented
this; the connection then fails whenever PgBouncer (transaction mode) reassigns
the backend that owns the name.
"""

from __future__ import annotations

import asyncpg
import pytest

from app.database import _anonymous_statement_name, _connect_args

POSTGRES_URL = "postgresql+asyncpg://u:p@aws-0.pooler.supabase.com:6543/postgres"


def test_sqlite_connect_args_are_untouched():
    assert _connect_args("sqlite+aiosqlite:///:memory:") == {}


def test_postgres_disables_statement_caches():
    args = _connect_args(POSTGRES_URL)
    assert args["statement_cache_size"] == 0
    assert args["prepared_statement_cache_size"] == 0


def test_postgres_requests_anonymous_statements():
    args = _connect_args(POSTGRES_URL)
    assert args["prepared_statement_name_func"] is _anonymous_statement_name
    assert args["prepared_statement_name_func"]() == ""


class _StopBeforeExecution(Exception):
    """Raised by the stub protocol to end the test before any real I/O."""


def _stub_connection() -> asyncpg.Connection:
    """A Connection with just enough state to exercise `_get_statement`.

    `object.__new__` skips `__init__` (no socket is ever opened), so `_aborted`
    is set explicitly — it makes `is_closed()` short-circuit and keeps asyncpg's
    `__del__` from complaining about the missing real protocol.
    """
    conn = object.__new__(asyncpg.Connection)
    conn._protocol = _RecordingProtocol()
    conn._stmt_cache = {}
    conn._stmt_cache_enabled = False
    conn._config = type("_Cfg", (), {"max_cacheable_statement_size": None})()
    conn._aborted = True
    return conn


class _RecordingProtocol:
    """Stand-in for asyncpg's protocol that records the requested stmt name."""

    def __init__(self):
        self.requested_name = "<never called>"

    def get_record_class(self):
        return None

    async def prepare(
        self, name, query, timeout, record_class=None, ignore_custom_codec=False
    ):
        self.requested_name = name
        raise _StopBeforeExecution


async def test_empty_name_selects_anonymous_statement_in_asyncpg():
    """Tripwire on the asyncpg behaviour this fix depends on.

    `_get_statement` only takes the anonymous branch when `named` is an empty
    str: `None`/`True` produce a generated named statement, and any non-empty
    str is used verbatim. If a future asyncpg changes that, this fails loudly
    rather than silently reintroducing intermittent production 500s.
    """
    conn = _stub_connection()

    with pytest.raises(_StopBeforeExecution):
        await conn._get_statement(
            "SELECT 1", None, named=_anonymous_statement_name(), use_cache=False
        )

    assert conn._protocol.requested_name == ""


async def test_named_helper_would_produce_a_generated_name():
    """Documents the failure mode: the old `None` default generates a name."""
    conn = _stub_connection()

    with pytest.raises(_StopBeforeExecution):
        # What SQLAlchemy's default _default_name_func() returned.
        await conn._get_statement("SELECT 1", None, named=True, use_cache=False)

    assert conn._protocol.requested_name.startswith("__asyncpg_stmt_")
