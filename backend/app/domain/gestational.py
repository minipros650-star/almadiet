"""AlmaDiet — Centralized gestational-age validation.

Single authoritative module for trimester/week consistency. The database
CHECK constraints, the Pydantic schemas, and the Flutter form all mirror
these boundaries — but only this module defines the logic used by code.
"""

TRIMESTER_WEEK_RANGES: dict[int, tuple[int, int]] = {
    1: (1, 13),
    2: (14, 26),
    3: (27, 42),
}

MIN_WEEK = 1
MAX_WEEK = 42

TRIMESTER_LABELS = {1: "First", 2: "Second", 3: "Third"}


class GestationalValidationError(ValueError):
    """Raised when trimester and gestational week contradict each other."""

    def __init__(self, trimester: int, week: int):
        self.trimester = trimester
        self.week = week
        low, high = TRIMESTER_WEEK_RANGES.get(trimester, (0, 0))
        self.message = (
            f"Gestational week {week} does not match trimester {trimester}. "
            f"Trimester {trimester} covers weeks {low}-{high}."
        )
        super().__init__(self.message)


def validate_gestational_age(trimester: int, week: int) -> None:
    """Raise GestationalValidationError if the pair is contradictory.

    >>> validate_gestational_age(2, 20)
    >>> validate_gestational_age(1, 30)
    Traceback (most recent call last):
        ...
    app.domain.gestational.GestationalValidationError: ...
    """
    if trimester not in TRIMESTER_WEEK_RANGES:
        raise GestationalValidationError(trimester, week)
    if not (MIN_WEEK <= week <= MAX_WEEK):
        raise GestationalValidationError(trimester, week)
    low, high = TRIMESTER_WEEK_RANGES[trimester]
    if not (low <= week <= high):
        raise GestationalValidationError(trimester, week)


def trimester_for_week(week: int) -> int:
    """Return the trimester that contains the given week (validates range)."""
    if not (MIN_WEEK <= week <= MAX_WEEK):
        raise GestationalValidationError(0, week)
    for trimester, (low, high) in TRIMESTER_WEEK_RANGES.items():
        if low <= week <= high:
            return trimester
    raise GestationalValidationError(0, week)  # pragma: no cover
