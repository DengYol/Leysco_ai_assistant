"""Caching utilities for Decision Support"""

import time
import asyncio
import logging
from typing import Any, Optional, Dict
from functools import wraps

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages caching for decision support operations"""
    
    def __init__(self):
        self._cache: Dict[str, tuple] = {}
        self.metrics = {"hits": 0, "misses": 0}
    
    def get(self, key: str, ttl: int = 300) -> Optional[Any]:
        """Get value from cache if still valid."""
        if key in self._cache:
            cached_time, value = self._cache[key]
            if time.time() - cached_time < ttl:
                self.metrics["hits"] += 1
                logger.debug(f"Cache hit for key: {key}")
                return value
            else:
                del self._cache[key]
        self.metrics["misses"] += 1
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        # Don't cache coroutines
        if asyncio.iscoroutine(value):
            logger.warning(f"Attempted to cache coroutine for key {key}, skipping")
            return
        self._cache[key] = (time.time(), value)
    
    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()
        logger.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        total = self.metrics["hits"] + self.metrics["misses"]
        hit_rate = (self.metrics["hits"] / total * 100) if total > 0 else 0
        return {
            "hits": self.metrics["hits"],
            "misses": self.metrics["misses"],
            "hit_rate": round(hit_rate, 1)
        }


# Global cache instance
_cache_manager = CacheManager()


def cached(ttl_key: str):
    """Decorator for caching decision support methods."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            from .constants import CACHE_TTL
            ttl = CACHE_TTL.get(ttl_key, 300)
            
            # Generate cache key
            cache_str = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            cache_key = f"{ttl_key}:{hash(cache_str)}"
            
            # Check cache
            cached_result = _cache_manager.get(cache_key, ttl)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = func(self, *args, **kwargs)
            
            # Cache result
            if result and not result.get("error"):
                _cache_manager.set(cache_key, result)
            
            return result
        return wrapper
    return decorator