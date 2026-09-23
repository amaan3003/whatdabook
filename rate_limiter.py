"""Small in-memory rate limiters for short-lived bot actions."""

from collections import deque
from math import ceil
from threading import Lock
from time import monotonic


class SlidingWindowRateLimiter:
    """Allow a fixed number of actions during a rolling time window."""

    def __init__(self, limit, window_seconds):
        if limit < 1 or window_seconds <= 0:
            raise ValueError("Rate limit and window must be positive.")

        self.limit = limit
        self.window_seconds = window_seconds
        self._events = {}
        self._lock = Lock()

    def check(self, key, now=None):
        """Return ``(allowed, retry_after_seconds)`` and record allowed actions."""
        timestamp = monotonic() if now is None else now
        cutoff = timestamp - self.window_seconds

        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= self.limit:
                retry_after = max(
                    1,
                    ceil(events[0] + self.window_seconds - timestamp),
                )
                return False, retry_after

            events.append(timestamp)
            return True, 0
