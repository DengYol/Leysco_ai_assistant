"""Caching decorators and management for Leysco API Service"""

import hashlib
import logging
from functools import wraps
from typing import Any, Callable

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


def cache_api_result(ttl_seconds: int = 300, key_prefix: str = ""):
    """Decorator to cache API results."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Skip caching if no user token (security)
            if not self.auth_handler.user_token:
                logger.debug("Skipping cache - no user token")
                return func(self, *args, **kwargs)
            
            cache = get_cache_service()
            
            # Generate cache key
            func_name = func.__name__
            cache_str = f"{key_prefix or func_name}:{str(args)}:{str(sorted(kwargs.items()))}"
            cache_key = hashlib.md5(cache_str.encode()).hexdigest()
            
            # Check cache
            cached = cache.get_simple(cache_key)
            if cached is not None:
                logger.info(f"⚡ API cache hit: {func_name}")
                self._record_cache_hit()
                return cached
            
            self._record_cache_miss()
            
            # Execute function
            result = func(self, *args, **kwargs)
            
            # Cache result
            if result:
                cache.set_simple(cache_key, result, ttl=ttl_seconds)
            
            return result
        return wrapper
    return decorator


class CacheManager:
    """Manages cache operations for the API service"""
    
    def __init__(self):
        self._stats = {"cache_hits": 0, "cache_misses": 0}
        self._cache = get_cache_service()
    
    def record_hit(self):
        self._stats["cache_hits"] += 1
    
    def record_miss(self):
        self._stats["cache_misses"] += 1
    
    def get_stats(self) -> dict:
        return self._stats.copy()
    
    def clear(self):
        """Clear all caches"""
        self._cache.clear()
        self._stats["cache_hits"] = 0
        self._stats["cache_misses"] = 0
        logger.info("Cache cleared")
    
    def get_simple(self, key: str):
        return self._cache.get_simple(key)
    
    def set_simple(self, key: str, value: Any, ttl: int = 300):
        return self._cache.set_simple(key, value, ttl)