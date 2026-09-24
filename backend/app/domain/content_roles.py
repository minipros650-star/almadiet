"""AlmaDiet — content governance roles.

Review and publication authority is data, not configuration. A role is
granted in the database (``content_role_grants``) by a documented bootstrap
procedure, never inferred from a request body, an email hint, or an
environment variable in production.

Two distinct duties exist so that a single person cannot both pass a meal
through review and declare it clinically publishable on their own:

  REVIEW_REQUIRED --REVIEWER--> REVIEWED --PUBLISHER--> PUBLISHED
"""

from __future__ import annotations

from enum import Enum


class ContentRole(str, Enum):
    """Duties that may be granted on the content governance workflow."""

    # Can move a meal out of the review queue (REVIEW_REQUIRED -> REVIEWED).
    REVIEWER = "REVIEWER"
    # Can declare reviewed content clinically publishable (REVIEWED -> PUBLISHED).
    PUBLISHER = "PUBLISHER"


#: Roles trusted with governance surfaces (evidence intake, policy versions).
CONTENT_STAFF_ROLES: frozenset[ContentRole] = frozenset(
    {ContentRole.REVIEWER, ContentRole.PUBLISHER}
)


def is_content_role(value: str) -> bool:
    return value in {role.value for role in ContentRole}
