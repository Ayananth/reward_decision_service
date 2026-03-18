from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from typing import Any, Protocol

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None

logger = logging.getLogger(__name__)


class CacheBackend(Protocol):
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value with optional TTL in seconds."""

    def get(self, key: str) -> Any | None:
        """Read value from cache. Returns None on miss/expiry."""

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True when key existed."""

    def exists(self, key: str) -> bool:
        """Check whether a non-expired key exists."""

    def acquire_lock(self, key: str, token: str, ttl: int = 30) -> bool:
        """Acquire a lock key if absent. Returns True when acquired."""

    def release_lock(self, key: str, token: str) -> bool:
        """Release lock only when token matches. Returns True when released."""


class InMemoryCache:
    def __init__(self, default_ttl_seconds: int = 86400):
        self.default_ttl_seconds = default_ttl_seconds
        self._store: dict[str, Any] = {}
        self._expirations: dict[str, float] = {}
        self._lock = threading.RLock()

    def _purge_if_expired(self, key: str) -> None:
        expires_at = self._expirations.get(key)
        if expires_at is not None and expires_at <= time.time():
            self._store.pop(key, None)
            self._expirations.pop(key, None)

    def _set_expiration(self, key: str, ttl: int | None) -> None:
        if ttl is None:
            ttl = self.default_ttl_seconds
        if ttl > 0:
            self._expirations[key] = time.time() + ttl
        else:
            self._expirations.pop(key, None)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            self._store[key] = copy.deepcopy(value)
            self._set_expiration(key, ttl)

    def get(self, key: str) -> Any | None:
        with self._lock:
            self._purge_if_expired(key)
            value = self._store.get(key)
            if value is None:
                return None
            return copy.deepcopy(value)

    def delete(self, key: str) -> bool:
        with self._lock:
            self._purge_if_expired(key)
            existed = key in self._store
            self._store.pop(key, None)
            self._expirations.pop(key, None)
            return existed

    def exists(self, key: str) -> bool:
        with self._lock:
            self._purge_if_expired(key)
            return key in self._store

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._expirations.clear()

    def acquire_lock(self, key: str, token: str, ttl: int = 30) -> bool:
        with self._lock:
            self._purge_if_expired(key)
            if key in self._store:
                return False

            self._store[key] = token
            self._set_expiration(key, ttl)
            return True

    def release_lock(self, key: str, token: str) -> bool:
        with self._lock:
            self._purge_if_expired(key)
            if self._store.get(key) != token:
                return False

            self._store.pop(key, None)
            self._expirations.pop(key, None)
            return True


class RedisCache:
    _RELEASE_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""

    def __init__(self, default_ttl_seconds: int = 86400):
        if redis is None:
            raise RuntimeError("redis package is not installed")

        self.default_ttl_seconds = default_ttl_seconds
        self.client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True,
        )
        # Fail fast so we can fallback to memory immediately.
        self.client.ping()
        logger.info(
            "Connected to Redis cache host=%s port=%s db=%s",
            os.getenv("REDIS_HOST", "localhost"),
            os.getenv("REDIS_PORT", "6379"),
            os.getenv("REDIS_DB", "0"),
        )

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = json.dumps(value)
        if ttl is None:
            ttl = self.default_ttl_seconds

        if ttl > 0:
            self.client.setex(key, ttl, payload)
        else:
            self.client.set(key, payload)

    def get(self, key: str) -> Any | None:
        raw = self.client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def delete(self, key: str) -> bool:
        return bool(self.client.delete(key))

    def exists(self, key: str) -> bool:
        return bool(self.client.exists(key))

    def acquire_lock(self, key: str, token: str, ttl: int = 30) -> bool:
        return bool(self.client.set(key, token, nx=True, ex=ttl))

    def release_lock(self, key: str, token: str) -> bool:
        result = self.client.eval(self._RELEASE_LOCK_LUA, 1, key, token)
        return bool(result)


def _build_cache() -> CacheBackend:
    backend = os.getenv("CACHE_BACKEND", "redis").lower()
    if backend == "memory":
        logger.info("Using in-memory cache backend (forced by CACHE_BACKEND=memory)")
        return InMemoryCache()

    try:
        return RedisCache()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable, falling back to in-memory cache: %s", exc)
        return InMemoryCache()


cache: CacheBackend = _build_cache()
