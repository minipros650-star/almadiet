"""AlmaDiet — who may see which content states.

One policy, used by every read path that is not already role-gated, so the
answer to "can this caller see an unreviewed meal?" cannot drift between
endpoints:

* An **ordinary** caller — anonymous, or signed in without a content role —
  may only ever see ``PUBLISHED`` content. Unreviewed content is invisible to
  them, over the API *and* over PostgREST (see the ``p_meals_read`` policy).
* A **content staff** member (reviewer/publisher) may additionally see the
  working set (``REVIEW_REQUIRED``/``REVIEWED``) so they can do their job.

The widening for staff is bounded by configuration, and configuration in
production can only ever tighten to ``PUBLISHED`` — see
``app.config`` and ``ContentStatus``.
"""

from __future__ import annotations

from app.domain.content_state import ContentStatus

PUBLISHED = ContentStatus.PUBLISHED.value


def readable_statuses(
    configured: list[str] | None,
    is_content_staff: bool,
) -> list[str]:
    """Content states a caller on this request may list.

    Ordinary callers are fixed to ``PUBLISHED`` regardless of configuration.
    Content staff get the configured working set, defaulting to ``PUBLISHED``
    when nothing is configured.
    """
    if not is_content_staff:
        return [PUBLISHED]
    resolved = [s.strip().upper() for s in (configured or []) if s.strip()]
    return resolved or [PUBLISHED]


def is_readable(status: str | None, is_content_staff: bool) -> bool:
    """True if a single content row may be returned to this caller."""
    if is_content_staff:
        return True
    return str(status or "").upper() == PUBLISHED
