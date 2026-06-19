from app.core.cache import InMemoryCache
from app.core.ratelimit import InMemoryRateLimiter


def test_cache_set_get_and_expiry():
    c = InMemoryCache()
    c.set("k", "v", ttl=60)
    assert c.get("k") == "v"
    c.set("k2", "v2", ttl=0)
    assert c.get("k2") is None  # already expired


def test_cache_lru_eviction():
    c = InMemoryCache(max_size=2)
    c.set("a", "1", ttl=60)
    c.set("b", "2", ttl=60)
    c.set("c", "3", ttl=60)  # evicts "a"
    assert c.get("a") is None
    assert c.get("b") == "2"
    assert c.get("c") == "3"


def test_rate_limiter_allows_then_blocks():
    rl = InMemoryRateLimiter()
    key = "client-x"
    assert all(rl.allow(key, 5) for _ in range(5))
    assert rl.allow(key, 5) is False  # 6th within the window
