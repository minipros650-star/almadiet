"""AlmaDiet — Authentication dependency (dual-mode).

AUTH_MODE=supabase (production / Vercel preview):
    Flutter authenticates via Supabase Auth (Google OAuth) and sends its
    access token as ``Authorization: Bearer <token>``. This module validates
    that JWT server-side using **Supabase's supported asymmetric JWKS
    endpoint** (``{SUPABASE_URL}/auth/v1/.well-known/jwks.json``) — signature,
    issuer, audience, expiry, algorithm allowlist and subject are all
    verified. The identity comes ONLY from the validated token ``sub``; a
    user ID in a request body is never trusted.

    Key caching: JWKS keys are cached in-process for
    ``SUPABASE_JWKS_CACHE_SECONDS``. An unknown key id triggers one
    refresh-and-retry, so Supabase key rotation takes effect without a
    redeploy. A failed refresh backs off so JWKS outages cannot hammer the
    endpoint.

    Legacy symmetric fallback: projects that have not migrated to asymmetric
    JWT signing keys may set ``SUPABASE_JWT_SECRET``. That path is only
    honored when explicitly configured and NEVER in production — the
    supported verification method is the JWKS endpoint above.

AUTH_MODE=local (development / tests):
    Legacy first-party email+password JWTs (see jwt_handler.py) — kept so
    the existing local workflow and test suite keep working unchanged.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientError
from jwt.algorithms import has_crypto

from app.config import settings

security = HTTPBearer(auto_error=False)

# Supabase signs access tokens with the asymmetric keys published at the
# JWKS endpoint. This allowlist is the only set of algorithms ever accepted;
# anything else (including "none" and legacy HS variants) is rejected.
ASYMMETRIC_ALGORITHMS = ("ES256", "ES384", "RS256", "PS256")
LEGACY_SYMMETRIC_ALGORITHM = "HS256"


@dataclass(frozen=True)
class AuthIdentity:
    """Identity derived exclusively from a validated access token."""

    id: uuid.UUID
    email: str
    provider: str  # 'supabase' | 'local'


# ─────────────────────────────────────────────────────────────────────────
# Asymmetric ring: Supabase JWKS (supported path)
# ─────────────────────────────────────────────────────────────────────────
class _JwksRing:
    """Caches the project's published signing keys and verifies tokens.

    Rotation handling: ``get_signing_key_from_jwt`` re-fetches when the key
    id is not cached; if verification still fails on an unknown key we
    rebuild the client once (fresh fetch) before giving up.
    """

    def __init__(self, jwks_url: str, cache_seconds: int) -> None:
        if not has_crypto:  # pragma: no cover - guarded by requirements.txt
            raise RuntimeError(
                "PyJWT cryptography extras are required for JWKS validation. "
                "Install PyJWT[crypto]."
            )
        self._url = jwks_url
        self._cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._client = self._make_client()
        # Backoff after a failed refresh so a JWKS outage doesn't cause a
        # fetch storm per request.
        self._next_refresh_ok_at = 0.0

    def _make_client(self) -> PyJWKClient:
        return PyJWKClient(
            self._url,
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=self._cache_seconds,
            timeout=10,
        )

    def refresh(self) -> None:
        """Force a fresh JWKS fetch (rotation / unknown kid)."""
        now = time.monotonic()
        if now < self._next_refresh_ok_at:
            return
        with self._lock:
            if time.monotonic() < self._next_refresh_ok_at:
                return
            try:
                self._client = self._make_client()
            finally:
                # Allow the next refresh after 30s even if this one failed.
                self._next_refresh_ok_at = time.monotonic() + 30

    def verify(self, token: str, header_alg: str) -> dict | None:
        """Verify signature + claims. Returns the payload or None."""
        try:
            signing_key = self._client.get_signing_key_from_jwt(token)
        except PyJWKClientError:
            # Unknown kid (rotated key?) → refresh once and retry.
            self.refresh()
            try:
                signing_key = self._client.get_signing_key_from_jwt(token)
            except PyJWKClientError:
                return None
        except pyjwt.DecodeError:
            return None
        try:
            return pyjwt.decode(
                token,
                signing_key.key,
                algorithms=[header_alg],
                audience="authenticated",
                issuer=f"{settings.SUPABASE_URL}/auth/v1",
                options={"require": ["exp", "sub", "aud"]},
            )
        except pyjwt.PyJWTError:
            return None


# ─────────────────────────────────────────────────────────────────────────
# Legacy symmetric ring: explicit shared-secret compatibility path
# ─────────────────────────────────────────────────────────────────────────
class _SecretRing:
    """Verifies legacy HS256 tokens when a JWT secret is EXPLICITLY set.

    This exists only for projects that have not migrated to asymmetric
    signing keys. It is never used in production and never activates by
    default.
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret

    def verify(self, token: str, header_alg: str) -> dict | None:
        if header_alg != LEGACY_SYMMETRIC_ALGORITHM:
            return None  # never accept asymmetric tokens against a secret
        try:
            return pyjwt.decode(
                token,
                self._secret,
                algorithms=[LEGACY_SYMMETRIC_ALGORITHM],
                audience="authenticated",
                issuer=f"{settings.SUPABASE_URL}/auth/v1",
                options={"require": ["exp", "sub", "aud"]},
            )
        except pyjwt.PyJWTError:
            return None


_ring: _JwksRing | _SecretRing | None = None
_ring_sig: tuple[str, str, int] | None = None


def _get_ring() -> _JwksRing | _SecretRing | None:
    """Build/rebuild the verification ring when configuration changes.

    Mode is explicit (``SUPABASE_AUTH_VERIFY_MODE``):
      * ``jwks`` (default, supported): verify against the project's
        asymmetric keys at ``{SUPABASE_URL}/auth/v1/.well-known/jwks.json``.
        The legacy JWT secret is NOT needed.
      * ``legacy_secret``: verify HS256 with ``SUPABASE_JWT_SECRET``.
        Documented compatibility fallback for projects not yet on
        asymmetric signing keys — never permitted in production.
    """
    global _ring, _ring_sig
    sig = (
        settings.SUPABASE_URL,
        settings.SUPABASE_JWKS_URL,
        settings.SUPABASE_AUTH_VERIFY_MODE,
        settings.SUPABASE_JWT_SECRET,
        settings.SUPABASE_JWKS_CACHE_SECONDS,
    )
    if _ring is not None and _ring_sig == sig:
        return _ring

    if not settings.SUPABASE_URL:
        return None

    ring: _JwksRing | _SecretRing
    if settings.SUPABASE_AUTH_VERIFY_MODE == "jwks":
        ring = _JwksRing(
            settings.SUPABASE_JWKS_URL, settings.SUPABASE_JWKS_CACHE_SECONDS
        )
    elif (
        settings.SUPABASE_AUTH_VERIFY_MODE == "legacy_secret"
        and settings.SUPABASE_JWT_SECRET
        and not settings.IS_PRODUCTION
    ):
        ring = _SecretRing(settings.SUPABASE_JWT_SECRET)
    else:
        # Unknown mode, missing secret, or legacy mode in production.
        return None
    _ring, _ring_sig = ring, sig
    return _ring


def _token_alg(token: str) -> str | None:
    """Return the declared header algorithm (validated against allowlists)."""
    try:
        header = pyjwt.get_unverified_header(token)
    except pyjwt.PyJWTError:
        return None
    alg = header.get("alg")
    return alg if isinstance(alg, str) else None


def _decode_supabase_token(token: str) -> dict | None:
    """Validate a Supabase access token via JWKS (legacy secret fallback).

    Enforces: signature, issuer, audience, expiry, algorithm allowlist and a
    parseable subject. Returns the payload, or None for ANY failure.
    """
    alg = _token_alg(token)
    if alg is None or alg not in ASYMMETRIC_ALGORITHMS + (LEGACY_SYMMETRIC_ALGORITHM,):
        return None

    ring = _get_ring()
    if ring is None:
        return None
    payload = ring.verify(token, alg)
    if payload is None:
        return None

    # Subject must be a UUID (Supabase auth user id) — this is the ONLY
    # source of identity downstream.
    try:
        uuid.UUID(str(payload.get("sub")))
    except (ValueError, AttributeError, TypeError):
        return None
    return payload


async def get_auth_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthIdentity:
    """FastAPI dependency: validate the Bearer token per AUTH_MODE."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials

    if settings.AUTH_MODE == "supabase":
        payload = _decode_supabase_token(token)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            user_id = uuid.UUID(str(payload.get("sub")))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
            )
        email = str(payload.get("email") or "")
        return AuthIdentity(id=user_id, email=email, provider="supabase")

    # ── local mode: legacy first-party JWT ──────────────────────────
    from app.auth.jwt_handler import verify_access_token

    user_id_str = verify_access_token(token)
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        )
    return AuthIdentity(id=user_id, email="", provider="local")


async def get_current_user_dep(identity: AuthIdentity = Depends(get_auth_identity)):
    """Backwards-compatible dependency returning the identity.

    User-owned tables key on the validated token's subject; handlers scope
    every query with ``identity.id``.
    """
    return identity
