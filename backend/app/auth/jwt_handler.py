"""AlmaDiet — Token management.

Access tokens: short-lived JWTs (HS256, 15 min default).
Refresh tokens: opaque 384-bit random tokens; only a SHA-256 hash is stored;
issued in a rotation family so reuse revokes the family (T3/T19 in
docs/THREAT_MODEL.md).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError as JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User

security = HTTPBearer(auto_error=False)


# ── Access tokens ────────────────────────────────────────────────────────


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def verify_access_token(token: str) -> str | None:
    """Return user_id string if valid, else None (never raises)."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        if payload.get("typ") != "access":
            return None
        return payload.get("sub")
    except JWTError:
        return None


# ── Refresh tokens (opaque, hashed at rest, rotating) ────────────────────


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_utc(dt: datetime) -> datetime:
    """Normalize DB datetimes: SQLite returns naive UTC values."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def generate_refresh_token() -> tuple[str, str]:
    """Returns (raw_token, token_hash). The raw token is shown once."""
    raw = secrets.token_urlsafe(48)
    return raw, _hash_token(raw)


async def issue_refresh_token(
    db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID | None = None
) -> str:
    family_id = family_id or uuid.uuid4()
    raw, token_hash = generate_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        family_id=family_id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(row)
    await db.flush()
    return raw


async def rotate_refresh_token(
    db: AsyncSession, raw_token: str
) -> tuple[User, str] | None:
    """Validate + rotate. On reuse of a rotated/revoked token the whole
    family is revoked (theft detection). Returns (user, new_raw) or None."""
    token_hash = _hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    now = datetime.now(timezone.utc)
    if row.revoked_at is not None or _as_utc(row.expires_at) <= now:
        # Replay of an already-rotated/revoked token → revoke the family.
        await revoke_family(db, row.family_id)
        return None

    user = await db.get(User, row.user_id)
    if user is None:
        return None

    # Revoke the used token, issue a sibling in the same family.
    row.revoked_at = now
    new_raw = await issue_refresh_token(db, user.id, family_id=row.family_id)
    return user, new_raw


async def revoke_token(db: AsyncSession, raw_token: str) -> bool:
    token_hash = _hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    row = result.scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    return True


def _utcnow_naive_safe(dt):
    return _as_utc(dt) if dt is not None else None


async def revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
        )
    )
    now = datetime.now(timezone.utc)
    for row in result.scalars():
        row.revoked_at = now
    await db.flush()
    # The revocation MUST persist even though the caller (refresh endpoint)
    # immediately raises a 401 — get_db rolls back sessions whose request
    # ends in an exception, which would silently undo theft detection.
    await db.commit()


async def revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    )
    now = datetime.now(timezone.utc)
    count = 0
    for row in result.scalars():
        row.revoked_at = now
        count += 1
    await db.flush()
    return count


# ── FastAPI dependency ───────────────────────────────────────────────────


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dual-mode authentication dependency.

    AUTH_MODE=supabase (production/preview): the Bearer token is a Supabase
    Auth JWT. It is validated server-side and the user identity is derived
    ONLY from the token's ``sub`` — a user ID in a request body is never
    trusted. The matching ``users`` row is auto-provisioned on first sight
    (profiles live in Supabase; this row mirrors the id for FK integrity).

    AUTH_MODE=local (development/tests): legacy first-party JWTs.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials

    if settings.AUTH_MODE == "supabase":
        from app.auth.identity import _decode_supabase_token

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
        # Auto-provision the local mirror row keyed by the Supabase user id.
        user = await db.get(User, user_id)
        if user is None:
            from app.services.user_service import ensure_user_for_supabase

            user = await ensure_user_for_supabase(
                db,
                user_id=user_id,
                email=str(payload.get("email") or ""),
                name=str(
                    (payload.get("user_metadata") or {}).get("full_name")
                    or (payload.get("user_metadata") or {}).get("name")
                    or ""
                ),
            )
        return user

    # ── local mode ────────────────────────────────────────────────
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

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        )
    return user
