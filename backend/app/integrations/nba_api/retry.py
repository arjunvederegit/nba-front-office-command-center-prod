"""Bounded retries with exponential backoff + jitter, and a per-endpoint circuit breaker."""

import random
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from app.core.logging import get_logger

from .exceptions import (
    NBAProviderError,
    ProviderBlockedError,
    ProviderUnavailableError,
    classify_exception,
)

T = TypeVar("T")
logger = get_logger(__name__)

FAILURES_TO_OPEN = 3
COOLDOWN_SECONDS = 300.0


class CircuitBreaker:
    """Opens after consecutive classified failures; half-opens after a cooldown."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def check(self, endpoint: str) -> None:
        with self._lock:
            opened = self._opened_at.get(endpoint)
            if opened is None:
                return
            if time.monotonic() - opened > COOLDOWN_SECONDS:
                # half-open: allow one probe through
                del self._opened_at[endpoint]
                self._failures[endpoint] = FAILURES_TO_OPEN - 1
                return
        raise ProviderUnavailableError(
            endpoint, "circuit open after repeated failures; retrying after cooldown"
        )

    def record_success(self, endpoint: str) -> None:
        with self._lock:
            self._failures.pop(endpoint, None)
            self._opened_at.pop(endpoint, None)

    def record_failure(self, endpoint: str) -> None:
        with self._lock:
            count = self._failures.get(endpoint, 0) + 1
            self._failures[endpoint] = count
            if count >= FAILURES_TO_OPEN:
                self._opened_at[endpoint] = time.monotonic()
                logger.warning("circuit opened for %s", endpoint, extra={"endpoint": endpoint})


_breaker = CircuitBreaker()


def get_circuit_breaker() -> CircuitBreaker:
    return _breaker


def with_retries(
    endpoint: str,
    fn: Callable[[], T],
    max_retries: int,
    base_delay: float = 1.5,
) -> T:
    """Run fn with classified retries. Blocked responses are not retried aggressively —
    hammering an edge block only makes it worse."""
    _breaker.check(endpoint)
    last_error: NBAProviderError | None = None
    for attempt in range(max_retries + 1):
        try:
            result = fn()
            _breaker.record_success(endpoint)
            return result
        except Exception as exc:  # noqa: BLE001 — classified below
            error = classify_exception(endpoint, exc)
            last_error = error
            _breaker.record_failure(endpoint)
            if isinstance(error, ProviderBlockedError) or attempt >= max_retries:
                break
            delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
            logger.warning(
                "retryable %s failure (%s), attempt %d/%d, sleeping %.1fs",
                endpoint,
                error.classification,
                attempt + 1,
                max_retries,
                delay,
                extra={"endpoint": endpoint},
            )
            time.sleep(delay)
    assert last_error is not None
    raise last_error
