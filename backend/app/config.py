"""AlmaDiet — Application configuration.

All secrets come from environment variables. When ENVIRONMENT=production the
application REFUSES TO START on:
  - missing/default JWT secret
  - wildcard CORS
  - DEBUG=true

Never silently generate insecure production secrets.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class ConfigError(RuntimeError):
    """Raised when configuration is unsafe for the target environment."""


def resolve_supabase_keys(getenv=os.getenv) -> tuple[str, str]:
    """Resolve (publishable_key, secret_key) with legacy-name fallback.

    Preferred current names: ``SUPABASE_PUBLISHABLE_KEY`` / ``SUPABASE_SECRET_KEY``.
    Legacy names ``SUPABASE_ANON_KEY`` / ``SUPABASE_SERVICE_ROLE_KEY`` are
    accepted as a documented compatibility fallback (publishable/anon are
    public; secret/service-role must stay server-side only).
    """
    publishable = getenv("SUPABASE_PUBLISHABLE_KEY") or getenv("SUPABASE_ANON_KEY", "")
    secret = getenv("SUPABASE_SECRET_KEY") or getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    return publishable, secret


# Secrets known to be shipped as defaults in code/history — never acceptable
# in production. (Keeping the legacy default listed here lets us detect an
# unrotated deployment.)
KNOWN_INSECURE_SECRETS = {
    "almadiet-super-secret-key-change-in-production",
    "almadiet-super-secret-jwt-key-2026",
    "your-super-secret-key-change-in-production",
    "changeme",
    "secret",
}


class Settings:
    def __init__(self) -> None:
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()
        self.DEBUG: bool = os.getenv("DEBUG", "true" if self.ENVIRONMENT == "development" else "false").lower() == "true"
        self.IS_PRODUCTION: bool = self.ENVIRONMENT == "production"

        # ── Database ──────────────────────────────────────────
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/almadiet",
        )

        # ── JWT / auth ────────────────────────────────────────
        # AUTH_MODE selects the authentication provider:
        #   supabase — production/preview: Flutter signs in via Supabase
        #              Auth (Google OAuth) and sends its access token as a
        #              Bearer header; this backend validates the Supabase JWT.
        #   local    — development/tests: legacy first-party email+password
        #              flow (Argon2id + rotating refresh tokens).
        self.AUTH_MODE: str = os.getenv("AUTH_MODE", "local").lower()
        if self.AUTH_MODE not in ("local", "supabase"):
            raise ConfigError("AUTH_MODE must be 'local' or 'supabase'.")

        # ── Supabase ──────────────────────────────────────────
        # URL is public (project ref). Tokens are verified against the
        # project's ASYMMETRIC keys published at the JWKS endpoint —
        # the legacy symmetric JWT secret is NOT required.
        self.SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").rstrip("/")
        # Preferred current key names; legacy anon/service-role names are
        # accepted as a documented compatibility fallback.
        self.SUPABASE_PUBLISHABLE_KEY, self.SUPABASE_SECRET_KEY = resolve_supabase_keys()
        # Token verification mode: 'jwks' (supported, default) verifies via
        # the asymmetric JWKS endpoint; 'legacy_secret' verifies HS256 with
        # SUPABASE_JWT_SECRET and is REFUSED in production.
        self.SUPABASE_AUTH_VERIFY_MODE: str = os.getenv(
            "SUPABASE_AUTH_VERIFY_MODE", "jwks"
        ).lower()
        if self.SUPABASE_AUTH_VERIFY_MODE not in ("jwks", "legacy_secret"):
            raise ConfigError(
                "SUPABASE_AUTH_VERIFY_MODE must be 'jwks' or 'legacy_secret'."
            )
        self.SUPABASE_JWKS_URL: str = os.getenv(
            "SUPABASE_JWKS_URL",
            f"{self.SUPABASE_URL}/auth/v1/.well-known/jwks.json" if self.SUPABASE_URL else "",
        )
        # Only consulted for the legacy_secret compatibility mode.
        self.SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
        self.SUPABASE_JWKS_CACHE_SECONDS: int = int(
            os.getenv("SUPABASE_JWKS_CACHE_SECONDS", "600")
        )
        # Server-side uploads/signing need a secret key client; it must
        # never reach the client or the logs.
        self.USER_PRIVATE_BUCKET: str = os.getenv("USER_PRIVATE_BUCKET", "user-private")
        self.MEAL_IMAGES_BUCKET: str = os.getenv("MEAL_IMAGES_BUCKET", "meal-images")

        self.JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
        self.JWT_ALGORITHM: str = "HS256"
        self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
        self.REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
        self.LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
        self.LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

        # ── CORS ──────────────────────────────────────────────
        # Dev default covers localhost + 127.0.0.1, including the Flutter
        # web debug server on :4200. Production must set ALLOWED_ORIGINS
        # explicitly (wildcard is rejected in _validate_production).
        raw_origins = os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost,http://127.0.0.1,"
            "http://localhost:4200,http://127.0.0.1:4200"
            if not self.IS_PRODUCTION else "",
        )
        self.ALLOWED_ORIGINS: list[str] = (
            [] if raw_origins.strip() in ("", "*") and not self.IS_PRODUCTION
            else [o.strip() for o in raw_origins.split(",") if o.strip()]
        )

        # ── Content governance ────────────────────────────────
        include = os.getenv("CONTENT_INCLUDE_STATUSES", "")
        self.CONTENT_INCLUDE_STATUSES: list[str] | None = (
            [s.strip() for s in include.split(",") if s.strip()] or None
        )

        # ── Evidence research pipeline (admin-only, offline) ──
        # Retrieval may ONLY target these domains; anything else raises.
        # Applies to both the URL fetcher and (if ever configured) any
        # search-provider integration.
        raw_domains = os.getenv(
            "ALLOWED_DOMAINS",
            "who.int,cdc.gov,nih.gov,acdha.org,nice.org.uk,cochrane.org,"
            "efsa.europa.eu,fssai.gov.in,mothersafe.medicinesinpregnancy.org",
        )
        self.ALLOWED_DOMAINS: list[str] = [
            d.strip().lower() for d in raw_domains.split(",") if d.strip()
        ]
        # Feature flags — every new ML/research feature is DISABLED by
        # default. The deterministic safety-filter + ranking baseline is
        # the default production path.
        self.ENABLE_EVIDENCE_PIPELINE: bool = os.getenv(
            "ENABLE_EVIDENCE_PIPELINE", "false"
        ).lower() == "true"
        self.ENABLE_LEARNED_RANKER: bool = os.getenv(
            "ENABLE_LEARNED_RANKER", "false"
        ).lower() == "true"

        # ── Images ────────────────────────────────────────────
        self.IMAGE_STORAGE_DIR: str = str(
            Path(__file__).resolve().parent.parent / "data" / "meal_images"
        )

        # ── Paths ─────────────────────────────────────────────
        self.MEALS_DATASET_PATH: str = str(
            Path(__file__).resolve().parent.parent / "data" / "meals_dataset.json"
        )

        # ── Server ────────────────────────────────────────────
        self.HOST: str = os.getenv("HOST", "0.0.0.0")
        self.PORT: int = int(os.getenv("PORT", "8000"))

        self._validate()

    def _validate(self) -> None:
        if not self.IS_PRODUCTION:
            # Development convenience: generate an ephemeral secret rather
            # than shipping a known one, and warn loudly.
            if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY in KNOWN_INSECURE_SECRETS:
                self.JWT_SECRET_KEY = secrets.token_urlsafe(48)
            return

        # ── Production hard gates ─────────────────────────────
        if self.DEBUG:
            raise ConfigError("DEBUG must be false in production (ENVIRONMENT=production).")

        if self.AUTH_MODE == "supabase":
            if not self.SUPABASE_URL:
                raise ConfigError("SUPABASE_URL is required when AUTH_MODE=supabase.")
            if not self.SUPABASE_JWKS_URL:
                raise ConfigError(
                    "SUPABASE_JWKS_URL could not be derived from SUPABASE_URL."
                )
            if self.SUPABASE_AUTH_VERIFY_MODE == "legacy_secret":
                raise ConfigError(
                    "SUPABASE_AUTH_VERIFY_MODE=legacy_secret is not allowed in "
                    "production. Use asymmetric JWKS verification (default)."
                )

        secret = self.JWT_SECRET_KEY
        if not secret:
            raise ConfigError(
                "JWT_SECRET_KEY is required in production. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if secret in KNOWN_INSECURE_SECRETS:
            raise ConfigError(
                "JWT_SECRET_KEY matches a known insecure/default value. "
                "Rotate to a new random secret before deploying."
            )
        if len(secret) < 32:
            raise ConfigError("JWT_SECRET_KEY must be at least 32 characters in production.")

        if "*" in self.ALLOWED_ORIGINS:
            raise ConfigError(
                "Wildcard CORS ('*') is not allowed in production. "
                "Set ALLOWED_ORIGINS to an explicit comma-separated origin list."
            )


settings = Settings()
