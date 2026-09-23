"""AlmaDiet — User service: registration, authentication, profile updates."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password, needs_rehash, verify_password
from app.core.rate_limit import LoginLockout
from app.domain import profile as profile_domain
from app.models.user import User
from app.schemas.user import UserRegister, UserUpdate

# Process-level lockout tracker (see core/rate_limit for swap-in backend).
login_lockout = LoginLockout(max_attempts=5, lockout_minutes=15)


def _compute_due_date(lmp_date: date) -> date:
    """Naegele's Rule: due date = LMP + 280 days."""
    return lmp_date + timedelta(days=280)


def _sync_derived_profile(user: User) -> None:
    """Recompute the server-authoritative profile fields on the user row.

    BMI, gestational week, and trimester are ALWAYS derived server-side —
    from height + pre-pregnancy weight and LMP/due date respectively — and
    persisted so that no API consumer ever supplies them. Invalid
    combinations (e.g. contradictory dates) raise ProfileDataError from the
    domain layer BEFORE any field is persisted; incomplete data simply
    clears the derived fields and marks the profile incomplete.
    """
    completion = profile_domain.profile_completion_status(
        height_cm=user.height_cm,
        pre_pregnancy_weight_kg=user.pre_pregnancy_weight_kg,
        lmp_date=user.lmp_date,
        due_date=user.due_date,
        region=user.region,
        dietary_preference=user.dietary_preference,
        allergies=user.declared_allergies,
    )
    # Validate pregnancy dates eagerly — contradictory/invalid data must
    # be rejected rather than silently persisted.
    derived = {"week": None, "trimester": None}
    if user.lmp_date is not None or user.due_date is not None:
        derived = profile_domain.derive_gestational_age(
            lmp_date=user.lmp_date, due_date=user.due_date
        )
    user.pre_pregnancy_bmi = completion["pre_pregnancy_bmi"]
    user.gestational_week = derived["week"]
    user.trimester = derived["trimester"]
    user.profile_complete = completion["complete"]


async def ensure_user_for_supabase(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    email: str,
    name: str = "",
) -> User:
    """Auto-provision the local ``users`` mirror row for a Supabase Auth user.

    Supabase remains the identity provider: the id/email come from the
    validated JWT, never from a request body. Password login is disabled for
    these rows (unusable random hash) — password accounts, if any, would be
    migrated through Supabase's own import path, not here.
    """
    user = await db.get(User, user_id)
    if user is not None:
        return user
    user = User(
        id=user_id,
        email=(email or f"{user_id}@supabase.invalid").lower(),
        # Not a real credential: Supabase owns authentication for this row.
        password_hash="!supabase-managed:no-local-login",
        name=name.strip(),
    )
    db.add(user)
    await db.flush()
    return user


async def register_user(db: AsyncSession, data: UserRegister) -> User:
    result = await db.execute(select(User).where(User.email == data.email.lower()))
    existing = result.scalar_one_or_none()
    if existing:
        raise ValueError("Email already registered")

    due_date = _compute_due_date(data.lmp_date) if data.lmp_date else None

    user = User(
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        name=data.name.strip(),
        phone=data.phone,
        region=data.region,
        language=data.language,
        lmp_date=data.lmp_date,
        due_date=due_date,
        age=data.age,
        height_cm=data.height_cm,
        pre_pregnancy_weight_kg=data.pre_pregnancy_weight_kg,
    )
    db.add(user)
    await db.flush()
    _sync_derived_profile(user)
    await db.flush()
    await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> tuple[Optional[User], str]:
    """Authenticate with lockout awareness.

    Returns (user, status) where status is one of:
      "ok" · "invalid" · "locked".
    The error message for invalid vs unknown email is IDENTICAL (no user
    enumeration).
    """
    key = email.strip().lower()
    if login_lockout.is_locked(key):
        return None, "locked"

    result = await db.execute(select(User).where(User.email == key))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        # Count failed attempts against the account (lockout after 5).
        login_lockout.record_failure(key)
        return None, "invalid"

    # Transparent hash upgrade for legacy bcrypt rows.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        await db.flush()

    login_lockout.record_success(key)
    return user, "ok"


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    return await db.get(User, user_id)


async def update_user(db: AsyncSession, user_id: uuid.UUID, data: UserUpdate) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    if "lmp_date" in update_data and user.lmp_date:
        user.due_date = _compute_due_date(user.lmp_date)

    # Re-derive BMI/week/trimester/completeness server-side. Runs BEFORE
    # flush so a ProfileDataError (contradictory dates) aborts the whole
    # update transaction.
    _sync_derived_profile(user)

    await db.flush()
    await db.refresh(user)
    return user
