"""Auth unit tests — hashing, lockout, access-token verification."""

from __future__ import annotations

import pytest

from app.auth.password import hash_password, needs_rehash, validate_password_strength, verify_password


def test_argon2_hash_and_verify():
    h = hash_password("Password123")
    assert h.startswith("$argon2")
    assert verify_password("Password123", h)
    assert not verify_password("wrong", h)
    assert "Password123" not in h  # never plaintext


def test_password_policy():
    with pytest.raises(Exception):
        validate_password_strength("short1")
    with pytest.raises(Exception):
        validate_password_strength("nodigitshere")
    with pytest.raises(Exception):
        validate_password_strength("12345678")
    validate_password_strength("GoodPass1")


def test_access_token_roundtrip():
    from app.auth.jwt_handler import create_access_token, verify_access_token
    import uuid

    uid = uuid.uuid4()
    token = create_access_token(uid)
    assert verify_access_token(token) == str(uid)


def test_expired_token_rejected():
    """TEST 6 (unit): expired tokens are never accepted."""
    from jose import jwt as jose_jwt
    from app.config import settings
    from app.auth.jwt_handler import verify_access_token
    from datetime import datetime, timedelta, timezone
    import uuid

    expired = jose_jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert verify_access_token(expired) is None


def test_garbage_token_rejected():
    from app.auth.jwt_handler import verify_access_token

    assert verify_access_token("not.a.token") is None


def test_lockout_after_five_failures():
    from app.core.rate_limit import LoginLockout

    lock = LoginLockout(max_attempts=5, lockout_minutes=15)
    assert not lock.is_locked("a@b.com")
    for _ in range(4):
        assert lock.record_failure("a@b.com") is False
    assert lock.record_failure("a@b.com") is True  # 5th locks
    assert lock.is_locked("a@b.com")
    lock.record_success("a@b.com")
    assert not lock.is_locked("a@b.com")
