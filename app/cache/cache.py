from __future__ import annotations

import copy
import threading
import time
from typing import Any, Protocol


class CacheBackend(Protocol):
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value with optional TTL in seconds."""

    def get(self, key: str) -> Any | None:
        """Read value from cache. Returns None on miss/expiry."""

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True when key existed."""

    def exists(self, key: str) -> bool:
        """Check whether a non-expired key exists."""


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


cache: CacheBackend = InMemoryCache()

