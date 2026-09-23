"""AlmaDiet — Password hashing (Argon2id) and password policy.

Argon2id is the recommended password-hashing scheme (OWASP Password Storage
Cheat Sheet). bcrypt remains able to VERIFY legacy hashes so existing
accounts keep working; new hashes are always Argon2id.
"""

from __future__ import annotations

import re

from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],  # argon2 preferred; bcrypt verifies legacy rows
    deprecated="bcrypt",
)

_MIN_LENGTH = 8


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        # Malformed hash in DB — treat as failed verification, never leak.
        return False


def needs_rehash(hashed_password: str) -> bool:
    """True if the hash uses a deprecated scheme and should be upgraded on
    next successful login."""
    return pwd_context.needs_update(hashed_password)


class PasswordPolicyError(ValueError):
    pass


def validate_password_strength(password: str) -> None:
    """Registration-time policy. Raises PasswordPolicyError."""
    if len(password) < _MIN_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {_MIN_LENGTH} characters.")
    if not re.search(r"[A-Za-z]", password):
        raise PasswordPolicyError("Password must contain a letter.")
    if not re.search(r"\d", password):
        raise PasswordPolicyError("Password must contain a digit.")
    if password.lower() in {"password", "password1", "12345678", "qwerty123"}:
        raise PasswordPolicyError("That password is too common.")
