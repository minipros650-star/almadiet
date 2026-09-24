"""CRITICAL TESTS 14 & 15 — production config rejects wildcard CORS and
fails startup when required secrets are missing."""

from __future__ import annotations

import pytest

import app.config as config_module


def _make_settings(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return config_module.Settings()


def test_production_requires_jwt_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com")
    with pytest.raises(config_module.ConfigError, match="JWT_SECRET_KEY"):
        _make_settings(monkeypatch)


def test_production_rejects_known_default_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "almadiet-super-secret-key-change-in-production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com")
    with pytest.raises(config_module.ConfigError, match="insecure"):
        _make_settings(monkeypatch)


def test_production_rejects_wildcard_cors(monkeypatch):
    """TEST 14."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    with pytest.raises(config_module.ConfigError, match="Wildcard CORS"):
        _make_settings(monkeypatch)


def test_production_rejects_debug(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    with pytest.raises(config_module.ConfigError, match="DEBUG"):
        _make_settings(monkeypatch)


def test_production_valid_config_passes(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "y" * 48)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com,https://admin.example.com")
    s = _make_settings(monkeypatch)
    assert s.ALLOWED_ORIGINS == ["https://app.example.com", "https://admin.example.com"]


def test_development_generates_ephemeral_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    s = _make_settings(monkeypatch)
    assert len(s.JWT_SECRET_KEY) >= 32


# ── DATABASE_URL driver normalization ────────────────────────
# Regression guard: a stock Supabase/provider URI uses `postgresql://`, which
# SQLAlchemy maps to the sync psycopg2 driver this app does not depend on.
# That produced `ModuleNotFoundError: No module named 'psycopg2'` inside the
# Vercel function and failed every route.


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://u:p@host:5432/db",
        "postgres://u:p@host:5432/db",
        "postgresql+psycopg2://u:p@host:5432/db",
        "postgresql+psycopg://u:p@host:5432/db",
    ],
)
def test_normalize_database_url_rewrites_sync_drivers(raw):
    assert config_module.normalize_database_url(raw) == "postgresql+asyncpg://u:p@host:5432/db"


def test_normalize_database_url_keeps_async_driver():
    url = "postgresql+asyncpg://u:p@host:6543/postgres"
    assert config_module.normalize_database_url(url) == url


def test_normalize_database_url_keeps_sqlite():
    url = "sqlite+aiosqlite:///:memory:"
    assert config_module.normalize_database_url(url) == url


def test_normalize_database_url_handles_empty():
    assert config_module.normalize_database_url("") == ""


def test_settings_normalizes_provider_database_url(monkeypatch):
    s = _make_settings(
        monkeypatch, DATABASE_URL="postgresql://postgres.abc:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
    )
    assert s.DATABASE_URL == (
        "postgresql+asyncpg://postgres.abc:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
    )


# SQLAlchemy's asyncpg dialect forwards every URL query parameter to
# asyncpg.connect(), so ORM/pooler extras such as Prisma's `pgbouncer=true` used
# to crash the first query with a TypeError.


def test_normalize_database_url_drops_pooler_only_params():
    url = "postgresql://u:p@host:6543/postgres?pgbouncer=true&connection_limit=1&schema=public"
    assert config_module.normalize_database_url(url) == (
        "postgresql+asyncpg://u:p@host:6543/postgres"
    )


def test_normalize_database_url_keeps_asyncpg_params():
    url = "postgresql://u:p@host:5432/db?statement_cache_size=0&timeout=10"
    assert config_module.normalize_database_url(url) == (
        "postgresql+asyncpg://u:p@host:5432/db?statement_cache_size=0&timeout=10"
    )


def test_normalize_database_url_translates_sslmode():
    """A TLS requirement must survive, not be dropped as an unknown param."""
    url = "postgresql://u:p@host:5432/db?sslmode=require"
    assert config_module.normalize_database_url(url) == (
        "postgresql+asyncpg://u:p@host:5432/db?ssl=require"
    )


def test_normalize_database_url_prefers_explicit_ssl_over_sslmode():
    url = "postgresql://u:p@host:5432/db?sslmode=require&ssl=verify-full"
    assert config_module.normalize_database_url(url) == (
        "postgresql+asyncpg://u:p@host:5432/db?ssl=verify-full"
    )


def test_normalize_database_url_handles_bracketed_password():
    """A real Supabase password containing ``[``/``]`` broke urllib.urlsplit."""
    url = "postgresql://u:p[a]ss@host:5432/db?pgbouncer=true"
    assert config_module.normalize_database_url(url) == (
        "postgresql+asyncpg://u:p%5Ba%5Dss@host:5432/db"
    )


def test_normalize_database_url_keeps_bracketed_password_without_query():
    url = "postgresql://u:p[a]ss@host:5432/db"
    assert config_module.normalize_database_url(url) == (
        "postgresql+asyncpg://u:p[a]ss@host:5432/db"
    )


def test_normalize_database_url_leaves_sqlite_query_untouched():
    url = "sqlite+aiosqlite:///file.db?cache=shared&mode=memory"
    assert config_module.normalize_database_url(url) == url


def test_settings_normalizes_prisma_style_pooler_url(monkeypatch):
    s = _make_settings(
        monkeypatch,
        DATABASE_URL=(
            "postgresql://postgres.abc:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
            "?pgbouncer=true&connection_limit=1"
        ),
    )
    assert s.DATABASE_URL == (
        "postgresql+asyncpg://postgres.abc:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
    )


# ── Content review policy ─────────────────────────────────────────────────


def test_separation_of_duties_is_on_by_default(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("CONTENT_REQUIRE_SEPARATION_OF_DUTIES", raising=False)
    assert _make_settings(monkeypatch).CONTENT_REQUIRE_SEPARATION_OF_DUTIES is True


def test_production_cannot_relax_separation_of_duties(monkeypatch):
    """Like CONTENT_INCLUDE_STATUSES, production may only tighten."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "z" * 48)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("CONTENT_REQUIRE_SEPARATION_OF_DUTIES", "false")
    assert _make_settings(monkeypatch).CONTENT_REQUIRE_SEPARATION_OF_DUTIES is True


def test_development_may_relax_separation_of_duties(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("CONTENT_REQUIRE_SEPARATION_OF_DUTIES", "false")
    assert _make_settings(monkeypatch).CONTENT_REQUIRE_SEPARATION_OF_DUTIES is False


def test_reviewer_bootstrap_allowlist_is_ignored_in_production(monkeypatch):
    """Production review authority must be a database grant, not an env var."""
    import app.auth.content_authz as authz

    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setattr(authz.settings, "ENVIRONMENT", "production")
    assert authz._dev_bootstrap_emails() == set()


def test_reviewer_bootstrap_allowlist_applies_in_development(monkeypatch):
    import app.auth.content_authz as authz

    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAILS", "admin@example.com,lead@example.com")
    monkeypatch.setattr(authz.settings, "ENVIRONMENT", "development")
    assert authz._dev_bootstrap_emails() == {"admin@example.com", "lead@example.com"}


def test_no_application_code_reads_reviewer_emails():
    """The email allowlist must not remain a review authority anywhere."""
    import pathlib

    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = [
        str(path.relative_to(app_dir))
        for path in app_dir.rglob("*.py")
        if "REVIEWER_EMAILS" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"REVIEWER_EMAILS is still read by: {offenders}"
