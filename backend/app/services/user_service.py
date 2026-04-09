"""
AlmaDiet — User Service
Handles user registration, authentication, profile management.
"""

import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserRegister, UserUpdate
from app.auth.password import hash_password, verify_password


def _compute_due_date(lmp_date: date) -> date:
    """Naegele's Rule: Due date = LMP + 280 days."""
    return lmp_date + timedelta(days=280)


def _compute_trimester_and_week(lmp_date: date) -> tuple[int, int]:
    """Compute current trimester and week number from LMP date."""
    today = date.today()
    days_pregnant = (today - lmp_date).days
    week_number = max(1, min(42, days_pregnant // 7 + 1))

    if week_number <= 13:
        trimester = 1
    elif week_number <= 26:
        trimester = 2
    else:
        trimester = 3

    return trimester, week_number


async def register_user(db: AsyncSession, data: UserRegister) -> User:
    """Register a new user with hashed password and computed due date."""
    # Check for existing email
    result = await db.execute(select(User).where(User.email == data.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise ValueError("Email already registered")

    due_date = _compute_due_date(data.lmp_date) if data.lmp_date else None

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
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
    await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> Optional[User]:
    """Authenticate user by email and password. Returns User or None."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Fetch user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def update_user(
    db: AsyncSession, user_id: uuid.UUID, data: UserUpdate
) -> User:
    """Update user profile fields."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("User not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    # Recompute due date if LMP changed
    if "lmp_date" in update_data and user.lmp_date:
        user.due_date = _compute_due_date(user.lmp_date)

    await db.flush()
    await db.refresh(user)
    return user
