"""Token-bucket rate limiter (in-memory; Redis fixed-window when REDIS_URL set)."""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List

from app.config import get_settings


class InMemoryRateLimiter:
    backend = "in-memory"

    def __init__(self) -> None:
        self._hits: Dict[str, List[float]] = defaultdict(list)

    def allow(self, key: str, limit_per_min: int) -> bool:
        now = time.time()
        window_start = now - 60
        hits = [t for t in self._hits[key] if t >= window_start]
        hits.append(now)
        self._hits[key] = hits
        return len(hits) <= limit_per_min


class RedisRateLimiter:
    backend = "redis"

    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url, decode_responses=True)
        self._r.ping()

    def allow(self, key: str, limit_per_min: int) -> bool:
        bucket = f"rl:{key}:{int(time.time() // 60)}"
        count = self._r.incr(bucket)
        if count == 1:
            self._r.expire(bucket, 60)
        return count <= limit_per_min


_LIMITER = None


def get_limiter():
    global _LIMITER
    if _LIMITER is not None:
        return _LIMITER
    settings = get_settings()
    if settings.use_redis:
        try:
            _LIMITER = RedisRateLimiter(settings.redis_url)
            return _LIMITER
        except Exception as exc:  # pragma: no cover
            print(f"[ratelimit] Redis unavailable ({exc}); using in-memory limiter.")
    _LIMITER = InMemoryRateLimiter()
    return _LIMITER
