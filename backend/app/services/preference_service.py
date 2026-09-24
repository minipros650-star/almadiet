"""AlmaDiet — User preference service (allergies, dislikes, favourites).

Declared allergies are stored on the user profile (validated against the
allergen taxonomy) and reused by the suggestion filter. Favourites are a
non-clinical ranking signal only.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.allergens import AllergenCategory, match_ingredient
from app.models.meal_favorite import MealFavorite
from app.models.user import User

VALID_COOKING_TIME = {"quick", "moderate", "relaxed"}
VALID_BUDGET = {"low", "medium", "high"}
VALID_DIETARY_PREFERENCE = {"veg", "nonveg", "eggetarian"}


class PreferenceValidationError(ValueError):
    def __init__(self, message: str, code: str = "INVALID_PREFERENCE"):
        self.code = code
        super().__init__(message)


def normalize_allergy_codes(raw: Optional[list[str]]) -> list[str]:
    """Free-text allergies → taxonomy codes (mirrors health_service)."""
    valid = {c.value for c in AllergenCategory}
    normalized: list[str] = []
    for item in raw or []:
        token = str(item).strip().lower()
        if not token:
            continue
        if token in valid:
            if token not in normalized:
                normalized.append(token)
            continue
        matched = match_ingredient(token)
        for code in matched:
            if code not in normalized:
                normalized.append(code)
    return normalized


def normalize_dislikes(raw: Optional[list[str]]) -> list[str]:
    out: list[str] = []
    for item in (raw or [])[:50]:
        token = str(item).strip().lower()[:100]
        if token and token not in out:
            out.append(token)
    return out


async def update_preferences(
    db: AsyncSession,
    user: User,
    *,
    allergies: Optional[list[str]] = None,
    dietary_preference: Optional[str] = None,
    disliked_ingredients: Optional[list[str]] = None,
    cooking_time_preference: Optional[str] = None,
    budget_preference: Optional[str] = None,
) -> User:
    """Apply preference updates. None = leave unchanged (PATCH semantics)."""
    if allergies is not None:
        user.declared_allergies = normalize_allergy_codes(allergies)
    if dietary_preference is not None:
        if dietary_preference not in VALID_DIETARY_PREFERENCE:
            raise PreferenceValidationError(
                f"dietary_preference must be one of {sorted(VALID_DIETARY_PREFERENCE)}",
                "INVALID_DIETARY_PREFERENCE",
            )
        user.dietary_preference = dietary_preference
    if disliked_ingredients is not None:
        user.disliked_ingredients = normalize_dislikes(disliked_ingredients)
    if cooking_time_preference is not None:
        if cooking_time_preference not in VALID_COOKING_TIME:
            raise PreferenceValidationError(
                f"cooking_time_preference must be one of {sorted(VALID_COOKING_TIME)}",
                "INVALID_COOKING_TIME",
            )
        user.cooking_time_preference = cooking_time_preference
    if budget_preference is not None:
        if budget_preference not in VALID_BUDGET:
            raise PreferenceValidationError(
                f"budget_preference must be one of {sorted(VALID_BUDGET)}",
                "INVALID_BUDGET",
            )
        user.budget_preference = budget_preference
    await db.flush()
    await db.refresh(user)
    return user


async def list_favorites(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(MealFavorite.meal_id).where(MealFavorite.user_id == user_id)
    )
    return list(result.scalars().all())


async def toggle_favorite(
    db: AsyncSession, user_id: uuid.UUID, meal_id: uuid.UUID
) -> bool:
    """Add/remove a favourite. Returns True if now a favourite."""
    result = await db.execute(
        select(MealFavorite).where(
            MealFavorite.user_id == user_id, MealFavorite.meal_id == meal_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.flush()
        return False
    db.add(MealFavorite(user_id=user_id, meal_id=meal_id))
    await db.flush()
    return True
