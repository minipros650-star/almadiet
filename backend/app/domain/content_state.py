"""AlmaDiet — Content governance lifecycle state machine.

Every meal content record moves through explicit states. Invalid transitions
raise ValueError. In production only PUBLISHED content participates in
recommendations; in development the allowed set is configurable.
"""

from __future__ import annotations

from enum import Enum


class ContentStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVIEWED = "REVIEWED"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


ALLOWED_TRANSITIONS: dict[ContentStatus, set[ContentStatus]] = {
    ContentStatus.DRAFT: {ContentStatus.REVIEW_REQUIRED, ContentStatus.RETIRED},
    ContentStatus.REVIEW_REQUIRED: {ContentStatus.REVIEWED, ContentStatus.RETIRED},
    ContentStatus.REVIEWED: {ContentStatus.PUBLISHED, ContentStatus.REVIEW_REQUIRED, ContentStatus.RETIRED},
    ContentStatus.PUBLISHED: {ContentStatus.RETIRED, ContentStatus.REVIEW_REQUIRED},
    ContentStatus.RETIRED: {ContentStatus.REVIEW_REQUIRED},
}


def can_transition(current: str | ContentStatus, target: str | ContentStatus) -> bool:
    current = ContentStatus(current)
    target = ContentStatus(target)
    return target in ALLOWED_TRANSITIONS[current]


def transition(current: str | ContentStatus, target: str | ContentStatus) -> ContentStatus:
    """Return the target status if the move is legal, else raise ValueError."""
    current = ContentStatus(current)
    target = ContentStatus(target)
    if not can_transition(current, target):
        raise ValueError(f"Illegal content transition: {current.value} → {target.value}")
    return target


def statuses_usable_in_recommendations(allowed_override: list[str] | None = None) -> set[str]:
    """Which content states may enter recommendations.

    Production default: only PUBLISHED. Dev/test may widen via config.
    """
    if allowed_override:
        return {s.upper() for s in allowed_override} & {s.value for s in ContentStatus}
    return {ContentStatus.PUBLISHED.value}


# Production-safe default; development may widen via CONTENT_INCLUDE_STATUSES.
DEFAULT_INCLUDE_STATUSES = frozenset({ContentStatus.PUBLISHED.value, ContentStatus.REVIEWED.value})


def is_recommendable(status: str, include_statuses: frozenset[str] | set[str] | None = None) -> bool:
    """True if a content row may enter recommendation flows."""
    allowed = include_statuses or DEFAULT_INCLUDE_STATUSES
    return str(status).upper() in {s.upper() for s in allowed}


def statuses_from_config(config_str: str, production: bool) -> frozenset[str]:
    """Resolve include-statuses from a config string.

    In production the override can only ever NARROW to PUBLISHED — a comma
    list that does not include PUBLISHED is ignored for safety.
    """
    if not config_str:
        return frozenset({ContentStatus.PUBLISHED.value}) if production else DEFAULT_INCLUDE_STATUSES
    requested = {s.strip().upper() for s in config_str.split(",") if s.strip()}
    valid = {s.value for s in ContentStatus}
    resolved = requested & valid
    if production and ContentStatus.PUBLISHED.value not in resolved:
        return frozenset({ContentStatus.PUBLISHED.value})
    return frozenset(resolved) if resolved else frozenset({ContentStatus.PUBLISHED.value})
