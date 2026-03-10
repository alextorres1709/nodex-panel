"""Simple in-memory TTL cache for expensive DB queries."""
import time
import threading

_cache = {}
_lock = threading.Lock()

DEFAULT_TTL = 10  # seconds


def cache_get(key):
    """Get a cached value. Returns None if expired or missing."""
    with _lock:
        entry = _cache.get(key)
        if entry and time.time() < entry[1]:
            return entry[0]
        if entry:
            del _cache[key]
    return None


def cache_set(key, value, ttl=DEFAULT_TTL):
    """Set a cached value with TTL in seconds."""
    with _lock:
        _cache[key] = (value, time.time() + ttl)


def cache_delete_prefix(prefix):
    """Delete all cache entries starting with prefix."""
    with _lock:
        keys = [k for k in _cache if k.startswith(prefix)]
        for k in keys:
            del _cache[k]
