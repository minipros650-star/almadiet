"""AlmaDiet — authorization dependencies for content governance.

Identity comes from the validated session token (``get_current_user``); the
role comes from the database. A request body can never supply, influence or
override either — the request models used by these routes additionally forbid
extra fields, so a submitted ``email`` or ``role`` is rejected outright.

Production authority is the ``content_role_grants`` table alone. A development
bootstrap allowlist exists purely so local/test flows work without a database
grant step; it is never consulted when ENVIRONMENT is production.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import get_current_user
from app.config import settings
from app.database import get_db
from app.domain.content_roles import CONTENT_STAFF_ROLES, ContentRole
from app.models.user import User
from app.schemas.errors import ErrorCode, envelope
from app.services import content_review_service
from app.services.content_review_service import ReviewActor


@dataclass(frozen=True)
class ContentActor:
    """A caller proven to hold one of the required content roles."""

    user: User
    role: ContentRole

    @property
    def label(self) -> str:
        return self.user.email or str(self.user.id)

    def to_review_actor(self) -> ReviewActor:
        return ReviewActor(user_id=self.user.id, label=self.label, role=self.role)


def _dev_bootstrap_emails() -> set[str]:
    """Development-only convenience allowlist (never used in production)."""
    if settings.ENVIRONMENT != "development":
        return set()
    raw = os.getenv("BOOTSTRAP_ADMIN_EMAILS", "admin@example.com")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def require_content_role(*allowed: ContentRole):
    """Dependency factory: caller must hold one of ``allowed`` in the database."""
    if not allowed:
        raise ValueError("require_content_role needs at least one role")
    allowed_values = {role.value for role in allowed}

    async def dependency(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> ContentActor:
        granted = await content_review_service.active_roles(db, user.id)
        for role in allowed:
            if role.value in granted:
                return ContentActor(user=user, role=role)

        if (user.email or "").strip().lower() in _dev_bootstrap_emails():
            # Development/test only — production never reaches this branch.
            return ContentActor(user=user, role=allowed[0])

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=envelope(
                ErrorCode.FORBIDDEN,
                "Content governance privileges required.",
                {
                    "blocking_code": "ROLE_REQUIRED",
                    "required_roles": sorted(allowed_values),
                },
            ),
        )

    return dependency


#: Any content staff member (reviewer or publisher). Used by the governance and
#: evidence surfaces, which are staff-only rather than duty-specific.
require_reviewer = require_content_role(*sorted(CONTENT_STAFF_ROLES, key=lambda r: r.value))

# Concrete, explicit dependencies for the meal workflow, so each duty is
# declared at the route that needs it.
require_meal_reviewer = require_content_role(ContentRole.REVIEWER)
require_meal_publisher = require_content_role(ContentRole.PUBLISHER)
