"""Factory function for creating ActionRouter instances

OPTIMIZED: ActionRouter instances are now cached per user_token + company_code.

Why this matters
----------------
The original factory created a brand-new ActionRouter (and therefore a
brand-new PricingService, WarehouseService, etc.) on every single chat
request. PricingService.__init__ calls _build_maps() which makes a
blocking HTTP request to /price_lists — so every message paid that
startup cost.

With per-token + per-company caching:
- First message for a user token + company combination → cold start, services created lazily
- All subsequent messages for same user+company → existing ActionRouter reused, no
  redundant service creation or API calls

Cache is bounded (_MAX_CACHED_ROUTERS) and uses LRU eviction so memory
stays under control even with many concurrent users.

Thread safety
-------------
The cache uses a simple dict protected by a threading.Lock so concurrent
async requests for the same token get the same instance safely.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict

from .router import ActionRouter

logger = logging.getLogger(__name__)

# Maximum number of ActionRouter instances to keep in memory.
# Each instance holds HTTP sessions and in-memory caches, so don't set
# this too high. 200 covers a large concurrent user base comfortably.
_MAX_CACHED_ROUTERS = 200

# LRU cache: (user_token, company_code) → ActionRouter
_router_cache: OrderedDict[tuple, ActionRouter] = OrderedDict()
_cache_lock = threading.Lock()


def _get_cache_key(user_token: str = None, company_code: str = None) -> tuple:
    """
    Generate a cache key from user_token and company_code.
    
    Args:
        user_token: The authenticated user's Bearer token
        company_code: Company code for multi-tenant operations
    
    Returns:
        Tuple cache key
    """
    return (user_token or "no_token", company_code or "no_company")


def create_action_router(user_token: str = None, company_code: str = None) -> ActionRouter:
    """
    Return an ActionRouter for the given user_token and company_code.

    - If an instance already exists for this token+company combination,
      it is returned directly (services already initialised, no HTTP
      calls on this path).
    - If no instance exists a new one is created. Services inside it are
      lazy — they won't make any HTTP calls until the first intent that
      actually needs them.
    - If the cache is full the least-recently-used entry is evicted first.

    Args:
        user_token: The authenticated user's Bearer token. Pass None only
                    for unauthenticated / test scenarios.
        company_code: Company code for multi-tenant URL resolution.

    Returns:
        Configured ActionRouter instance (possibly from cache).
    """
    # Don't cache unauthenticated routers — each gets a fresh instance
    # so they can't accidentally share state.
    if not user_token:
        logger.warning("create_action_router called WITHOUT user token - data access will fail")
        return ActionRouter(user_token=None, company_code=company_code)

    cache_key = _get_cache_key(user_token, company_code)
    
    # Log what we're doing
    logger.info(f"create_action_router: token ...{user_token[-6:]}, company={company_code}")

    with _cache_lock:
        if cache_key in _router_cache:
            # Move to end (most-recently-used)
            _router_cache.move_to_end(cache_key)
            logger.debug("ActionRouter cache HIT for token ...%s, company=%s", 
                        user_token[-6:], company_code)
            return _router_cache[cache_key]

        # Evict LRU entry if at capacity
        if len(_router_cache) >= _MAX_CACHED_ROUTERS:
            evicted_key, _ = _router_cache.popitem(last=False)
            logger.debug("ActionRouter cache evicted LRU entry (capacity=%d) for key=%s", 
                        _MAX_CACHED_ROUTERS, evicted_key)

        logger.info("create_action_router: creating new instance for token ...%s, company=%s", 
                   user_token[-6:], company_code)
        router = ActionRouter(user_token=user_token, company_code=company_code)
        _router_cache[cache_key] = router
        return router


def invalidate_router(user_token: str = None, company_code: str = None) -> bool:
    """
    Remove a cached ActionRouter for the given token and company.

    Call this on logout or token refresh so the next request gets a fresh
    instance with the updated credentials.

    If company_code is not provided, invalidates all entries for that user_token.

    Returns True if an entry was found and removed, False otherwise.
    """
    if not user_token:
        return False

    with _cache_lock:
        if company_code:
            # Invalidate specific token+company combination
            cache_key = _get_cache_key(user_token, company_code)
            if cache_key in _router_cache:
                del _router_cache[cache_key]
                logger.info("ActionRouter cache invalidated for token ...%s, company=%s", 
                           user_token[-6:], company_code)
                return True
        else:
            # Invalidate all entries for this user_token (any company)
            keys_to_remove = [
                key for key in _router_cache.keys() 
                if key[0] == user_token
            ]
            for key in keys_to_remove:
                del _router_cache[key]
                logger.info("ActionRouter cache invalidated for token ...%s, company=%s", 
                           user_token[-6:], key[1])
            return len(keys_to_remove) > 0
        
        return False


def get_cache_stats() -> dict:
    """Return current cache statistics (useful for monitoring / debug endpoints)."""
    with _cache_lock:
        # Count unique users and companies
        unique_users = set(key[0] for key in _router_cache.keys() if key[0] != "no_token")
        unique_companies = set(key[1] for key in _router_cache.keys() if key[1] != "no_company")
        
        return {
            "cached_routers": len(_router_cache),
            "max_capacity":   _MAX_CACHED_ROUTERS,
            "unique_users":   len(unique_users),
            "unique_companies": len(unique_companies),
        }