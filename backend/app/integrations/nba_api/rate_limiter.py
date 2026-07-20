"""Global rate limiting for NBA.com traffic.

Two mechanisms compose:
- a minimum interval between request starts (politeness pacing);
- a bounded concurrency semaphore (NBA.com tolerates very little parallelism).
"""

import threading
import time

from app.config import get_settings


class RateLimiter:
    def __init__(self, min_interval_seconds: float, max_concurrency: int):
        self.min_interval = min_interval_seconds
        self._semaphore = threading.Semaphore(max_concurrency)
        self._lock = threading.Lock()
        self._last_start = 0.0

    def __enter__(self) -> "RateLimiter":
        self._semaphore.acquire()
        with self._lock:
            wait = self._last_start + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_start = time.monotonic()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._semaphore.release()


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        settings = get_settings()
        _limiter = RateLimiter(
            settings.nba_api_min_request_interval_seconds,
            settings.nba_api_max_concurrency,
        )
    return _limiter
