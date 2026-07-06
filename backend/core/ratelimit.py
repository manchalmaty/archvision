"""In-process sliding-window rate limiter.

Single uvicorn process is the MVP deployment truth, so no Redis: a deque of
event timestamps per (key, window) suffices and dies with the process.
"""

import time
from collections import defaultdict, deque
from collections.abc import Sequence
from threading import Lock


class SlidingWindowLimiter:
    def __init__(self):
        self._events: dict[tuple[str, int], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(
        self,
        key: str,
        limits: Sequence[tuple[int, int]],
        now: float | None = None,
    ) -> float:
        """Try to record one event for key under every (limit, window_s) pair.

        Returns 0 if allowed (event recorded in all windows atomically), else
        the seconds until the tightest violated window frees up — nothing is
        recorded on rejection, so probing while limited never extends the ban.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            queues: list[deque[float]] = []
            retry = 0.0
            for limit, window_s in limits:
                if limit <= 0:  # 0 disables that window
                    continue
                q = self._events[(key, window_s)]
                cutoff = now - window_s
                while q and q[0] <= cutoff:
                    q.popleft()
                if len(q) >= limit:
                    retry = max(retry, q[0] + window_s - now)
                queues.append(q)
            if retry > 0:
                return retry
            for q in queues:
                q.append(now)
            return 0.0

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


limiter = SlidingWindowLimiter()
