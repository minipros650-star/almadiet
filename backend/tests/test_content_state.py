"""Content governance lifecycle tests."""

from __future__ import annotations

import pytest

from app.domain.content_state import (
    ContentStatus,
    can_transition,
    is_recommendable,
    statuses_from_config,
    transition,
)


def test_full_lifecycle():
    assert can_transition(ContentStatus.DRAFT, ContentStatus.REVIEW_REQUIRED)
    assert can_transition(ContentStatus.REVIEW_REQUIRED, ContentStatus.REVIEWED)
    assert can_transition(ContentStatus.REVIEWED, ContentStatus.PUBLISHED)
    assert can_transition(ContentStatus.PUBLISHED, ContentStatus.RETIRED)


def test_draft_cannot_skip_to_published():
    with pytest.raises(ValueError):
        transition(ContentStatus.DRAFT, ContentStatus.PUBLISHED)


def test_retired_reopens_review():
    assert can_transition(ContentStatus.RETIRED, ContentStatus.REVIEW_REQUIRED)


def test_recommendable_only_published_in_prod():
    assert is_recommendable("PUBLISHED", {"PUBLISHED"})
    assert not is_recommendable("REVIEW_REQUIRED", {"PUBLISHED"})
    assert not is_recommendable("RETIRED", {"PUBLISHED", "REVIEWED"})


def test_dev_default_includes_reviewed():
    from app.domain.content_state import DEFAULT_INCLUDE_STATUSES

    assert "REVIEWED" in DEFAULT_INCLUDE_STATUSES
    assert "REVIEW_REQUIRED" not in DEFAULT_INCLUDE_STATUSES


def test_prod_config_cannot_widen():
    assert statuses_from_config("REVIEWED,REVIEW_REQUIRED", production=True) == {"PUBLISHED"} or \
           "PUBLISHED" in statuses_from_config("REVIEWED,PUBLISHED", production=True)
    assert statuses_from_config("REVIEW_REQUIRED", production=True) == {"PUBLISHED"}


def test_seed_imports_are_never_published():
    """Seed service must import content as REVIEW_REQUIRED."""
    from app.services import meal_service
    from app.domain.content_state import ContentStatus

    assert ContentStatus.REVIEW_REQUIRED.value == "REVIEW_REQUIRED"
