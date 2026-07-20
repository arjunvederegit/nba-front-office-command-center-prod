"""In-memory provider health metrics, surfaced through /api/v1/data-health."""

import threading
import time
from dataclasses import dataclass, field


@dataclass
class EndpointHealth:
    endpoint: str
    successes: int = 0
    failures: int = 0
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_error: str | None = None
    last_latency_ms: float | None = None


@dataclass
class ProviderHealth:
    _lock: threading.Lock = field(default_factory=threading.Lock)
    endpoints: dict[str, EndpointHealth] = field(default_factory=dict)

    def record_success(self, endpoint: str, latency_ms: float) -> None:
        with self._lock:
            h = self.endpoints.setdefault(endpoint, EndpointHealth(endpoint))
            h.successes += 1
            h.last_success_at = time.time()
            h.last_latency_ms = latency_ms

    def record_failure(self, endpoint: str, error: str) -> None:
        with self._lock:
            h = self.endpoints.setdefault(endpoint, EndpointHealth(endpoint))
            h.failures += 1
            h.last_failure_at = time.time()
            h.last_error = error[:300]

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "endpoint": h.endpoint,
                    "successes": h.successes,
                    "failures": h.failures,
                    "last_success_at": h.last_success_at,
                    "last_failure_at": h.last_failure_at,
                    "last_error": h.last_error,
                    "last_latency_ms": h.last_latency_ms,
                }
                for h in self.endpoints.values()
            ]


_health = ProviderHealth()


def get_provider_health() -> ProviderHealth:
    return _health
