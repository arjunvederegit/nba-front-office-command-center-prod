"""Cache abstraction: Redis when configured, in-process TTL cache otherwise.

Cache keys embed a data-version namespace so evaluations computed against an older
snapshot are invalidated after each ingestion run (see bump_data_version)."""

import contextlib
import json
import threading
import time
from typing import Any

from app.config import get_settings


class InProcessTTLCache:
    """Thread-safe TTL cache used when no Redis URL is configured (single instance only)."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at < time.monotonic():
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        with self._lock:
            if len(self._store) > 4096:
                now = time.monotonic()
                self._store = {k: v for k, v in self._store.items() if v[0] >= now}
            self._store[key] = (time.monotonic() + ttl_seconds, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


class Cache:
    def __init__(self) -> None:
        settings = get_settings()
        self._redis: Any = None
        self._local = InProcessTTLCache()
        self.backend = "in-process"
        if settings.redis_url:
            try:
                import redis

                self._redis = redis.Redis.from_url(
                    settings.redis_url, decode_responses=True, socket_timeout=3
                )
                self._redis.ping()
                self.backend = "redis"
            except Exception:
                self._redis = None  # fall back silently; surfaced via /data-health

    def get_json(self, key: str) -> Any | None:
        raw = None
        if self._redis is not None:
            try:
                raw = self._redis.get(key)
            except Exception:
                raw = None
        if raw is None:
            raw = self._local.get(key)
        return json.loads(raw) if raw else None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        raw = json.dumps(value, default=str)
        if self._redis is not None:
            try:
                self._redis.setex(key, ttl_seconds, raw)
                return
            except Exception:
                pass
        self._local.set(key, raw, ttl_seconds)

    def get_data_version(self) -> str:
        version = None
        if self._redis is not None:
            try:
                version = self._redis.get("tradelab:data_version")
            except Exception:
                version = None
        if version is None:
            version = self._local.get("tradelab:data_version")
        return version or "0"

    def bump_data_version(self) -> None:
        version = str(int(time.time()))
        if self._redis is not None:
            with contextlib.suppress(Exception):
                self._redis.set("tradelab:data_version", version)
        self._local.set("tradelab:data_version", version, ttl_seconds=10 * 365 * 86400)

    def versioned_key(self, *parts: str) -> str:
        return "tradelab:v" + self.get_data_version() + ":" + ":".join(parts)


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache
