"""Caching decorators for DB Query Service"""

import hashlib
import logging
from functools import wraps

logger = logging.getLogger(__name__)


def cache_result(ttl_seconds: int = 300, key_prefix: str = ""):
    """Decorator to cache query results."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Skip caching for debug/testing
            if hasattr(self, '_skip_cache') and self._skip_cache:
                return func(self, *args, **kwargs)
            
            # Generate cache key
            cache_key = f"{key_prefix or func.__name__}:{hashlib.md5(str(args).encode()).hexdigest()}:{hashlib.md5(str(sorted(kwargs.items())).encode()).hexdigest()}"
            
            # Check cache
            cached = self.cache.get(cache_key, {}, "")
            if cached is not None:
                logger.info(f"Cache hit: {func.__name__}")
                return cached.get("data")
            
            # Execute function
            result = func(self, *args, **kwargs)
            
            # Cache result
            if result:
                self.cache.set(cache_key, {}, "", {"data": result})
                logger.info(f"Cached: {func.__name__}")
            
            return result
        return wrapper
    return decorator


def cache_price_lookup(ttl_seconds: int = 3600):
    """Specialized cache for price lookups."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, item_name: str, customer_name: str = None):
            cache_key = f"price_lookup:{item_name}:{customer_name or 'default'}"
            cached = self.cache.get_simple(cache_key)
            if cached:
                logger.info(f"Price cache hit: {item_name}")
                return cached
            
            result = func(self, item_name, customer_name)
            
            if result:
                self.cache.set_simple(cache_key, result, ttl=ttl_seconds)
            
            return result
        return wrapper
    return decorator