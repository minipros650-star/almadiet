"""AlmaDiet — In-process rate limiting and login lockout.

Suitable for single-instance deployments; for multi-instance deployments
back this with a shared store (Redis). Interface is intentionally tiny so
swapping the backend is a one-file change.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: float) -> None:
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self._events[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_events:
            return False
        q.append(now)
        return True

    def reset(self, key: str) -> None:
        self._events.pop(key, None)


class LoginLockout:
    """Tracks failed attempts per identity (email lowercased)."""

    def __init__(self, max_attempts: int, lockout_minutes: int) -> None:
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_minutes * 60
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._locked_until: dict[str, float] = {}

    def is_locked(self, key: str) -> bool:
        until = self._locked_until.get(key.lower())
        if until is None:
            return False
        if time.monotonic() >= until:
            self._locked_until.pop(key.lower(), None)
            self._failures.pop(key.lower(), None)
            return False
        return True

    def record_failure(self, key: str) -> bool:
        """Record a failure; returns True if this failure triggered a lock."""
        k = key.lower()
        now = time.monotonic()
        window_start = now - self.lockout_seconds
        fails = [t for t in self._failures[k] if t >= window_start]
        fails.append(now)
        self._failures[k] = fails
        if len(fails) >= self.max_attempts:
            self._locked_until[k] = now + self.lockout_seconds
            return True
        return False

    def record_success(self, key: str) -> None:
        self._failures.pop(key.lower(), None)
        self._locked_until.pop(key.lower(), None)


# Shared singletons (per process). Login limiter is a coarse abuse floor
# (10/min/IP); the per-account lockout (5 fails → 15 min) is the primary
# credential-stuffing defence.
login_rate_limiter = SlidingWindowLimiter(max_events=10, window_seconds=60)
register_rate_limiter = SlidingWindowLimiter(max_events=10, window_seconds=3600)
