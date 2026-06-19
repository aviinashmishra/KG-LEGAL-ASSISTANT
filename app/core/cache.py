"""Query-result cache: Redis when REDIS_URL is set, else in-memory TTL/LRU."""
from __future__ import annotations

import json
import time
from collections import OrderedDict
from typing import Optional

from app.config import get_settings


class InMemoryCache:
    backend = "in-memory"

    def __init__(self, max_size: int = 512) -> None:
        self._store: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
        self._max = max_size

    def get(self, key: str) -> Optional[str]:
        item = self._store.get(key)
        if not item:
            return None
        expires, value = item
        if expires <= time.time():
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: str, ttl: int) -> None:
        self._store[key] = (time.time() + ttl, value)
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)


class RedisCache:
    backend = "redis"

    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url, decode_responses=True)
        self._r.ping()

    def get(self, key: str) -> Optional[str]:
        return self._r.get(key)

    def set(self, key: str, value: str, ttl: int) -> None:
        self._r.set(key, value, ex=ttl)


_CACHE = None


def get_cache():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    settings = get_settings()
    if settings.use_redis:
        try:
            _CACHE = RedisCache(settings.redis_url)
            return _CACHE
        except Exception as exc:  # pragma: no cover
            print(f"[cache] Redis unavailable ({exc}); using in-memory cache.")
    _CACHE = InMemoryCache()
    return _CACHE


def cache_key(*parts: str) -> str:
    return "kgl:" + ":".join(parts)


def cached_json_get(key: str) -> Optional[dict]:
    raw = get_cache().get(key)
    return json.loads(raw) if raw else None


def cached_json_set(key: str, value: dict) -> None:
    get_cache().set(key, json.dumps(value), ttl=get_settings().cache_ttl_seconds)
