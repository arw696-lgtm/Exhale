"""Basic per-client rate limiting for the exposed surfaces.

The auth and OAuth endpoints are the ones an attacker can hammer without a
token (password guessing, signup spam, state probing), so they get a sliding
one-minute window per client IP. In-memory by design: the current deployment
is a single process, and a limiter that survives restarts adds a dependency
the threat model doesn't yet demand — noted in PROJECT_SCOPE §5 alongside the
open-signup gap this closes.
"""

from __future__ import annotations

import threading
import time
from collections import deque

WINDOW_SECONDS = 60.0


class RateLimiter:
    """Sliding-window counter per key (thread-safe)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, *, now: float | None = None) -> bool:
        """Record a hit for ``key`` and say whether it stays within ``limit``
        per :data:`WINDOW_SECONDS`. A denied hit still counts — hammering while
        throttled never earns a slot."""

        if limit <= 0:
            return True
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            cutoff = now - WINDOW_SECONDS
            while hits and hits[0] <= cutoff:
                hits.popleft()
            hits.append(now)
            return len(hits) <= limit

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
