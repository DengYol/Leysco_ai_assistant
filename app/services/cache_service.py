"""
cache_service.py
================
Intelligent response caching with Redis support, async operations, and thread safety.
Supports both in-memory (default) and Redis backends for distributed caching.

UPDATED: Added Redis sorted set and hash operations for activity logging
"""

import hashlib
import json
import time
import logging
import threading
import asyncio
from typing import Optional, Dict, Any, List, Union
from functools import lru_cache, wraps
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache Backend Types
# ---------------------------------------------------------------------------

class CacheBackend(Enum):
    MEMORY = "memory"
    REDIS = "redis"


# ---------------------------------------------------------------------------
# Entity fields that determine cache uniqueness
# ---------------------------------------------------------------------------
_CACHE_ENTITY_FIELDS = {
    "item_name",
    "customer_name",
    "warehouse",
    "quantity",
    "date",
    "detail_mode",
    "items_list",
}

# ---------------------------------------------------------------------------
# Intents that must NEVER be cached (real-time or write operations)
# ---------------------------------------------------------------------------
_NEVER_CACHE = {
    "GET_WAREHOUSE_STOCK",
    "GET_CUSTOMER_ORDERS",
    "GET_CUSTOMER_PRICE",
    "GET_OUTSTANDING_DELIVERIES",
    "GET_DELIVERY_HISTORY",
    "GET_LOW_STOCK_ALERTS",
    "CREATE_QUOTATION",
    "TRACK_DELIVERY",
    "COMPETITOR_PRICE_CHECK",
    "FIND_BEST_PRICE",
    "PRICE_ALERT",
}

# Intents with shorter TTL
_SHORT_TTL_INTENTS = {
    "GET_STOCK_LEVELS",
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "GET_TRENDING_PRODUCTS",
    "GET_TOP_PRODUCTS",
    "GET_TOP_CUSTOMERS",
}
_SHORT_TTL_SECONDS = 60

# Intents with longer TTL (knowledge base)
_LONG_TTL_INTENTS = {
    "COMPANY_INFO",
    "PRODUCT_INFO",
    "HOW_TO_ORDER",
    "CONTACT_INFO",
    "PAYMENT_METHODS",
    "POLICY_QUESTION",
    "FAQ",
    "GREETING",
    "THANKS",
    "SMALL_TALK",
}
_LONG_TTL_SECONDS = 3600  # 1 hour

# Cache limits
DEFAULT_MAX_ENTRIES = 1000
DEFAULT_TTL_SECONDS = 300
CLEANUP_INTERVAL_SECONDS = 120  # Cleanup every 2 minutes


# ---------------------------------------------------------------------------
# Redis Client (lazy-loaded)
# ---------------------------------------------------------------------------

_redis_client = None
_redis_available = False


def _get_redis_client():
    """Lazy-load Redis client."""
    global _redis_client, _redis_available
    
    if _redis_client is not None:
        return _redis_client if _redis_available else None
    
    try:
        from app.core.config import settings
        import redis
        
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True
        )
        # Test connection
        _redis_client.ping()
        _redis_available = True
        logger.info("✅ Redis cache backend available")
        return _redis_client
        
    except ImportError:
        logger.warning("Redis library not installed, falling back to memory cache")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}, falling back to memory cache")
    
    _redis_available = False
    return None


class CacheService:
    """
    Intelligent response cache with Redis support and async operations.
    Automatically falls back to in-memory cache if Redis unavailable.
    """

    def __init__(
        self, 
        ttl_seconds: int = DEFAULT_TTL_SECONDS, 
        max_entries: int = DEFAULT_MAX_ENTRIES,
        backend: str = "auto"  # auto, memory, redis
    ):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.backend = self._determine_backend(backend)
        
        # In-memory cache
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._simple_cache: Dict[str, Dict[str, Any]] = {}  # Simple key-value cache
        
        # In-memory data structures for Redis-like operations
        self._memory_zsets: Dict[str, Dict[str, float]] = {}  # Sorted sets
        self._memory_hashes: Dict[str, Dict[str, Any]] = {}   # Hashes
        self._memory_expiry: Dict[str, float] = {}             # Expiry times
        
        # Statistics
        self.hit_count = 0
        self.miss_count = 0
        self.eviction_count = 0
        self.redis_errors = 0
        
        # Thread safety
        self._lock = threading.RLock()
        self._cleanup_thread = None
        self._stop_cleanup = threading.Event()
        
        # Track last cleanup
        self._last_cleanup = time.time()
        
        # Start background cleanup thread
        self._start_cleanup_thread()
        
        logger.info(f"✅ CacheService initialized: backend={self.backend}, TTL={ttl_seconds}s, MaxEntries={max_entries}")

    def _determine_backend(self, backend: str) -> str:
        """Determine which cache backend to use."""
        if backend == "redis":
            if _get_redis_client():
                return "redis"
            logger.warning("Redis requested but unavailable, falling back to memory")
            return "memory"
        elif backend == "memory":
            return "memory"
        else:  # auto
            if _get_redis_client():
                return "redis"
            return "memory"

    # -----------------------------------------------------------------------
    # Lifecycle Management
    # -----------------------------------------------------------------------
    
    def _start_cleanup_thread(self):
        """Start background thread for periodic cleanup (memory cache only)."""
        def cleanup_worker():
            while not self._stop_cleanup.wait(CLEANUP_INTERVAL_SECONDS):
                try:
                    self._cleanup_expired()
                except Exception as e:
                    logger.error(f"Cache cleanup error: {e}")
        
        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        logger.debug("Cache cleanup thread started")
    
    def _cleanup_expired(self):
        """Remove expired entries from memory cache."""
        if self.backend == "redis":
            return  # Redis handles TTL automatically
        
        now = time.time()
        
        with self._lock:
            # Clean up main cache
            expired_keys = []
            for key, data in self._memory_cache.items():
                effective_ttl = self._get_effective_ttl(data.get("intent", ""))
                if now - data.get("timestamp", 0) > effective_ttl:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._memory_cache[key]
            
            # Clean up simple cache
            simple_expired = []
            for key, data in self._simple_cache.items():
                if now - data.get("timestamp", 0) > data.get("ttl", self.ttl_seconds):
                    simple_expired.append(key)
            
            for key in simple_expired:
                del self._simple_cache[key]
            
            # Clean up hash expiry
            hash_expired = []
            for key, expiry in self._memory_expiry.items():
                if now > expiry:
                    hash_expired.append(key)
            
            for key in hash_expired:
                if key in self._memory_hashes:
                    del self._memory_hashes[key]
                if key in self._memory_zsets:
                    del self._memory_zsets[key]
                del self._memory_expiry[key]
            
            if expired_keys or simple_expired or hash_expired:
                logger.debug(f"Cleaned {len(expired_keys)} main + {len(simple_expired)} simple + {len(hash_expired)} hash entries")
            
            self._last_cleanup = now

    # -----------------------------------------------------------------------
    # Key Construction (Optimized)
    # -----------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=2048)
    def _hash_key(key_str: str) -> str:
        """Cache MD5 hash results for repeated keys."""
        return hashlib.md5(key_str.encode()).hexdigest()

    def _canonical_entities(self, entities: dict) -> tuple:
        """
        Convert entities to a hashable tuple for cache keys.
        This is more efficient than dict serialization.
        """
        result = []
        for field in sorted(_CACHE_ENTITY_FIELDS):
            val = entities.get(field)
            if val is None or val == "" or val == []:
                continue
            
            # Normalize strings
            if isinstance(val, str):
                val = val.lower().strip()
            
            # Normalize lists (sort for consistency)
            if field == "items_list" and isinstance(val, list):
                val = tuple(sorted(
                    (str(x.get("ItemCode", x.get("code", ""))) for x in val),
                    key=lambda x: x
                ))
            
            result.append((field, val))
        
        return tuple(result)

    def _get_cache_key(self, intent: str, entities: dict) -> str:
        """
        Generate stable cache key from intent + canonical entities.
        Uses tuple hashing for better performance.
        """
        canonical = self._canonical_entities(entities)
        key_str = f"{intent.upper()}:{canonical}"
        return self._hash_key(key_str)

    def _get_effective_ttl(self, intent: str) -> int:
        """Get effective TTL for an intent."""
        intent_upper = intent.upper()
        if intent_upper in _SHORT_TTL_INTENTS:
            return _SHORT_TTL_SECONDS
        if intent_upper in _LONG_TTL_INTENTS:
            return _LONG_TTL_SECONDS
        return self.ttl_seconds

    # -----------------------------------------------------------------------
    # Simple Key-Value Cache Methods
    # -----------------------------------------------------------------------
    
    def get_simple(self, key: str) -> Optional[Any]:
        """
        Simple key-value get (sync).
        Used for intent and entity caching.
        """
        # Try Redis first
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    value = redis_client.get(f"simple:{key}")
                    if value:
                        self.hit_count += 1
                        logger.debug(f"Simple Redis cache hit: {key[:50]}...")
                        return json.loads(value)
                except Exception as e:
                    self.redis_errors += 1
                    logger.warning(f"Redis simple get error: {e}")
        
        # Fallback to memory
        with self._lock:
            if key in self._simple_cache:
                entry = self._simple_cache[key]
                if time.time() - entry.get("timestamp", 0) < entry.get("ttl", self.ttl_seconds):
                    self.hit_count += 1
                    logger.debug(f"Simple memory cache hit: {key[:50]}...")
                    return entry.get("value")
                else:
                    del self._simple_cache[key]
        
        self.miss_count += 1
        return None
    
    async def get_simple_async(self, key: str) -> Optional[Any]:
        """
        Simple key-value get (async).
        """
        return await asyncio.to_thread(self.get_simple, key)
    
    def set_simple(self, key: str, value: Any, ttl: int = None) -> None:
        """
        Simple key-value set (sync).
        """
        ttl = ttl or self.ttl_seconds
        
        cache_data = {
            "value": value,
            "timestamp": time.time(),
            "ttl": ttl
        }
        
        # Try Redis first
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    redis_client.setex(f"simple:{key}", ttl, json.dumps(value, default=str))
                    logger.debug(f"Simple Redis cache set: {key[:50]}... (TTL={ttl}s)")
                    return
                except Exception as e:
                    self.redis_errors += 1
                    logger.warning(f"Redis simple set error: {e}")
        
        # Fallback to memory
        with self._lock:
            # LRU eviction for simple cache
            if len(self._simple_cache) > self.max_entries:
                # Remove oldest entries
                oldest = sorted(self._simple_cache.items(), key=lambda x: x[1].get("timestamp", 0))[:50]
                for old_key, _ in oldest:
                    del self._simple_cache[old_key]
            
            self._simple_cache[key] = cache_data
            logger.debug(f"Simple memory cache set: {key[:50]}...")
    
    async def set_simple_async(self, key: str, value: Any, ttl: int = None) -> None:
        """
        Simple key-value set (async).
        """
        await asyncio.to_thread(self.set_simple, key, value, ttl)
    
    def delete_simple(self, key: str) -> bool:
        """
        Delete a simple cache entry.
        """
        # Delete from Redis
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    result = redis_client.delete(f"simple:{key}")
                    if result:
                        logger.debug(f"Simple Redis cache delete: {key[:50]}...")
                        return True
                except Exception as e:
                    logger.warning(f"Redis simple delete error: {e}")
        
        # Delete from memory
        with self._lock:
            if key in self._simple_cache:
                del self._simple_cache[key]
                logger.debug(f"Simple memory cache delete: {key[:50]}...")
                return True
        
        return False
    
    async def delete_simple_async(self, key: str) -> bool:
        """
        Delete a simple cache entry (async).
        """
        return await asyncio.to_thread(self.delete_simple, key)

    # -----------------------------------------------------------------------
    # Redis Sorted Set Operations (ZSET) - For activity logging
    # -----------------------------------------------------------------------
    
    async def zadd_async(self, key: str, mapping: Dict[str, float]) -> int:
        """
        Add members to a sorted set with scores.
        Compatible with both Redis and memory cache.
        """
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    return await asyncio.to_thread(redis_client.zadd, key, mapping)
                except Exception as e:
                    self.redis_errors += 1
                    logger.warning(f"Redis zadd error: {e}")
        
        # Memory implementation
        with self._lock:
            if key not in self._memory_zsets:
                self._memory_zsets[key] = {}
            
            for member, score in mapping.items():
                self._memory_zsets[key][member] = score
            
            # Set expiry for this key
            self._memory_expiry[key] = time.time() + 86400  # Default 24 hours
            
            return len(mapping)
    
    async def zrevrangebyscore_async(
        self, 
        key: str, 
        max: float, 
        min: float, 
        start: int = 0, 
        num: int = -1
    ) -> List[str]:
        """
        Get members from sorted set by score range (descending).
        """
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    return await asyncio.to_thread(
                        redis_client.zrevrangebyscore, 
                        key, max, min, start=start, num=num
                    )
                except Exception as e:
                    self.redis_errors += 1
                    logger.warning(f"Redis zrevrangebyscore error: {e}")
        
        # Memory implementation
        with self._lock:
            zset = self._memory_zsets.get(key, {})
            # Filter by score range
            filtered = [(member, score) for member, score in zset.items() if min <= score <= max]
            # Sort by score descending
            filtered.sort(key=lambda x: x[1], reverse=True)
            # Apply start/num
            if num > 0:
                filtered = filtered[start:start+num]
            else:
                filtered = filtered[start:]
            return [member for member, _ in filtered]
    
    async def zremrangebyrank_async(self, key: str, start: int, stop: int) -> int:
        """
        Remove members from sorted set by rank range.
        """
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    return await asyncio.to_thread(redis_client.zremrangebyrank, key, start, stop)
                except Exception as e:
                    self.redis_errors += 1
                    logger.warning(f"Redis zremrangebyrank error: {e}")
        
        # Memory implementation
        with self._lock:
            zset = self._memory_zsets.get(key, {})
            # Sort by score
            sorted_items = sorted(zset.items(), key=lambda x: x[1])
            # Remove range
            removed = 0
            to_remove = []
            for i in range(start, stop + 1):
                if 0 <= i < len(sorted_items):
                    to_remove.append(sorted_items[i][0])
                    removed += 1
            
            for member in to_remove:
                del zset[member]
            
            return removed

    # -----------------------------------------------------------------------
    # Redis Hash Operations - For activity logging
    # -----------------------------------------------------------------------
    
    async def hset_async(self, key: str, value: Dict[str, Any]) -> int:
        """
        Set hash field(s).
        """
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    return await asyncio.to_thread(redis_client.hset, key, mapping=value)
                except Exception as e:
                    self.redis_errors += 1
                    logger.warning(f"Redis hset error: {e}")
        
        # Memory implementation
        with self._lock:
            if key not in self._memory_hashes:
                self._memory_hashes[key] = {}
            
            for field, val in value.items():
                self._memory_hashes[key][field] = val
            
            # Set expiry
            self._memory_expiry[key] = time.time() + 86400
            
            return len(value)
    
    async def hgetall_async(self, key: str) -> Dict[str, Any]:
        """
        Get all hash fields.
        """
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    return await asyncio.to_thread(redis_client.hgetall, key)
                except Exception as e:
                    self.redis_errors += 1
                    logger.warning(f"Redis hgetall error: {e}")
        
        # Memory implementation
        with self._lock:
            # Check expiry
            if key in self._memory_expiry and time.time() > self._memory_expiry[key]:
                if key in self._memory_hashes:
                    del self._memory_hashes[key]
                if key in self._memory_zsets:
                    del self._memory_zsets[key]
                del self._memory_expiry[key]
                return {}
            
            return self._memory_hashes.get(key, {}).copy()
    
    async def expire_async(self, key: str, ttl: int) -> bool:
        """
        Set expiry on key.
        """
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    return await asyncio.to_thread(redis_client.expire, key, ttl)
                except Exception as e:
                    self.redis_errors += 1
                    logger.warning(f"Redis expire error: {e}")
        
        # Memory implementation
        with self._lock:
            self._memory_expiry[key] = time.time() + ttl
            return True
    
    async def delete_async(self, key: str) -> int:
        """
        Delete a key.
        """
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    return await asyncio.to_thread(redis_client.delete, key)
                except Exception as e:
                    self.redis_errors += 1
                    logger.warning(f"Redis delete error: {e}")
        
        # Memory implementation
        with self._lock:
            deleted = 0
            if key in self._memory_hashes:
                del self._memory_hashes[key]
                deleted += 1
            if key in self._memory_zsets:
                del self._memory_zsets[key]
                deleted += 1
            if key in self._memory_expiry:
                del self._memory_expiry[key]
            if key in self._memory_cache:
                del self._memory_cache[key]
                deleted += 1
            if key in self._simple_cache:
                del self._simple_cache[key]
                deleted += 1
            return deleted

    # -----------------------------------------------------------------------
    # Core Cache Operations (Sync)
    # -----------------------------------------------------------------------

    def get(self, intent: str, entities: dict, message: str = "") -> Optional[Dict[str, Any]]:
        """
        Retrieve cached response (sync version).
        
        Args:
            intent: Intent string
            entities: Extracted entities
            message: Original message (kept for compatibility, not used in key)
        
        Returns:
            Cached response dict or None if not found/expired
        """
        # Skip caching for certain intents
        if not self.should_cache(intent):
            return None
        
        # Skip if no entities that affect the result
        canonical = self._canonical_entities(entities)
        if not canonical:
            return None
        
        cache_key = self._get_cache_key(intent, entities)
        
        # Try Redis first
        if self.backend == "redis":
            return self._get_from_redis(cache_key, intent)
        
        # Fallback to memory cache
        return self._get_from_memory(cache_key, intent)

    def _get_from_redis(self, cache_key: str, intent: str) -> Optional[Dict[str, Any]]:
        """Get from Redis backend."""
        redis_client = _get_redis_client()
        if not redis_client:
            return self._get_from_memory(cache_key, intent)
        
        try:
            value = redis_client.get(f"cache:{cache_key}")
            if value:
                data = json.loads(value)
                self.hit_count += 1
                logger.debug(f"Redis cache hit: {intent}")
                return data
        except Exception as e:
            self.redis_errors += 1
            logger.warning(f"Redis get error: {e}")
        
        self.miss_count += 1
        return None

    def _get_from_memory(self, cache_key: str, intent: str) -> Optional[Dict[str, Any]]:
        """Get from memory backend."""
        with self._lock:
            if cache_key not in self._memory_cache:
                self.miss_count += 1
                return None
            
            cached_data = self._memory_cache[cache_key]
            age = time.time() - cached_data.get("timestamp", 0)
            effective_ttl = self._get_effective_ttl(intent)
            
            # Check expiration
            if age > effective_ttl:
                del self._memory_cache[cache_key]
                self.miss_count += 1
                logger.debug(f"Cache expired: {intent} age={age:.0f}s")
                return None
            
            # Update access time for LRU
            cached_data["last_access"] = time.time()
            self.hit_count += 1
            
            logger.debug(f"Memory cache hit: {intent} age={age:.0f}s")
            return cached_data.get("response")

    def set(self, intent: str, entities: dict, message: str, response: Dict[str, Any]) -> None:
        """
        Store response in cache (sync version).
        """
        if not self.should_cache(intent):
            return
        
        canonical = self._canonical_entities(entities)
        if not canonical:
            return
        
        cache_key = self._get_cache_key(intent, entities)
        now = time.time()
        ttl = self._get_effective_ttl(intent)
        
        cache_data = {
            "response": response,
            "timestamp": now,
            "last_access": now,
            "intent": intent,
            "entities": canonical,
        }
        
        # Try Redis first
        if self.backend == "redis":
            self._set_in_redis(cache_key, cache_data, ttl)
        else:
            self._set_in_memory(cache_key, cache_data)

    def _set_in_redis(self, cache_key: str, cache_data: dict, ttl: int):
        """Set in Redis backend."""
        redis_client = _get_redis_client()
        if redis_client:
            try:
                redis_client.setex(
                    f"cache:{cache_key}",
                    ttl,
                    json.dumps(cache_data, default=str)
                )
                logger.debug(f"Redis cache set: {cache_key} (TTL={ttl}s)")
            except Exception as e:
                self.redis_errors += 1
                logger.warning(f"Redis set error: {e}")

    def _set_in_memory(self, cache_key: str, cache_data: dict):
        """Set in memory backend."""
        with self._lock:
            self._memory_cache[cache_key] = cache_data
            logger.debug(f"Memory cache set: {cache_key}")
            self._evict_if_needed()

    def _evict_if_needed(self):
        """Evict oldest entries if cache exceeds max_entries."""
        if len(self._memory_cache) <= self.max_entries:
            return
        
        # Sort by last_access (least recently used first)
        sorted_items = sorted(
            self._memory_cache.items(),
            key=lambda x: x[1].get("last_access", x[1].get("timestamp", 0))
        )
        
        # Remove oldest entries (20% or min 10)
        evict_count = max(10, int(len(self._memory_cache) * 0.2))
        evict_keys = [key for key, _ in sorted_items[:evict_count]]
        
        for key in evict_keys:
            del self._memory_cache[key]
        
        self.eviction_count += len(evict_keys)
        logger.debug(f"Evicted {len(evict_keys)} entries, cache size now {len(self._memory_cache)}")

    # -----------------------------------------------------------------------
    # Async Operations
    # -----------------------------------------------------------------------

    async def get_async(self, intent: str, entities: dict, message: str = "") -> Optional[Dict[str, Any]]:
        """
        Async version of get() - runs in thread pool for Redis operations.
        """
        return await asyncio.to_thread(self.get, intent, entities, message)

    async def set_async(self, intent: str, entities: dict, message: str, response: Dict[str, Any]) -> None:
        """
        Async version of set() - runs in thread pool for Redis operations.
        """
        await asyncio.to_thread(self.set, intent, entities, message, response)

    # -----------------------------------------------------------------------
    # Cache Management
    # -----------------------------------------------------------------------

    def invalidate_intent(self, intent: str) -> int:
        """Remove all cached entries for a specific intent."""
        intent_upper = intent.upper()
        removed = 0
        
        # Invalidate in Redis
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    # Use SCAN to find matching keys (avoid KEYS in production)
                    pattern = f"cache:*"
                    keys = redis_client.keys(pattern)
                    for key in keys:
                        value = redis_client.get(key)
                        if value:
                            data = json.loads(value)
                            if data.get("intent", "").upper() == intent_upper:
                                redis_client.delete(key)
                                removed += 1
                except Exception as e:
                    logger.warning(f"Redis invalidation error: {e}")
        
        # Invalidate in memory
        with self._lock:
            to_delete = [
                key for key, data in self._memory_cache.items()
                if data.get("intent", "").upper() == intent_upper
            ]
            
            for key in to_delete:
                del self._memory_cache[key]
                removed += 1
        
        if removed > 0:
            logger.info(f"Invalidated {removed} entries for intent {intent_upper}")
        
        return removed

    def invalidate_entity(self, intent: str, entity_key: str, entity_value: str) -> int:
        """Invalidate cache entries containing a specific entity value."""
        removed = 0
        target_value = entity_value.lower().strip()
        
        with self._lock:
            to_delete = []
            for key, data in self._memory_cache.items():
                if intent and data.get("intent", "").upper() != intent.upper():
                    continue
                
                entities = data.get("entities", {})
                if isinstance(entities, tuple):
                    entities_dict = dict(entities)
                    if entities_dict.get(entity_key) == target_value:
                        to_delete.append(key)
                elif isinstance(entities, dict):
                    if entities.get(entity_key) == target_value:
                        to_delete.append(key)
            
            for key in to_delete:
                del self._memory_cache[key]
                removed += 1
        
        if removed > 0:
            logger.info(f"Invalidated {removed} entries for {entity_key}={entity_value}")
        
        return removed

    def clear(self) -> None:
        """Wipe entire cache."""
        # Clear Redis
        if self.backend == "redis":
            redis_client = _get_redis_client()
            if redis_client:
                try:
                    redis_client.flushdb()
                except Exception as e:
                    logger.warning(f"Redis flush error: {e}")
        
        # Clear memory
        with self._lock:
            count = len(self._memory_cache)
            self._memory_cache.clear()
            self._simple_cache.clear()
            self._memory_zsets.clear()
            self._memory_hashes.clear()
            self._memory_expiry.clear()
            logger.info(f"Memory cache cleared: removed {count} entries")

    def should_cache(self, intent: str) -> bool:
        """Determine if an intent should be cached."""
        return intent.upper() not in _NEVER_CACHE

    # -----------------------------------------------------------------------
    # Statistics
    # -----------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        with self._lock:
            total_requests = self.hit_count + self.miss_count
            hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0
            
            now = time.time()
            ages = []
            intent_counts = {}
            
            for data in self._memory_cache.values():
                age = now - data.get("timestamp", 0)
                ages.append(age)
                
                intent = data.get("intent", "unknown")
                intent_counts[intent] = intent_counts.get(intent, 0) + 1
            
            return {
                "backend": self.backend,
                "cache_size": len(self._memory_cache),
                "simple_cache_size": len(self._simple_cache),
                "zset_count": len(self._memory_zsets),
                "hash_count": len(self._memory_hashes),
                "max_entries": self.max_entries,
                "hit_count": self.hit_count,
                "miss_count": self.miss_count,
                "hit_rate": f"{hit_rate:.1f}%",
                "total_requests": total_requests,
                "eviction_count": self.eviction_count,
                "redis_errors": self.redis_errors,
                "ttl_seconds": self.ttl_seconds,
                "utilization": f"{len(self._memory_cache) / self.max_entries * 100:.1f}%" if self.max_entries > 0 else "n/a",
                "age_stats": {
                    "min": f"{min(ages):.0f}s" if ages else "n/a",
                    "max": f"{max(ages):.0f}s" if ages else "n/a",
                    "avg": f"{sum(ages) / len(ages):.0f}s" if ages else "n/a",
                },
                "intent_distribution": intent_counts,
            }

    def get_cached_intents(self) -> List[str]:
        """Get list of intents currently in cache."""
        with self._lock:
            return list(set(data.get("intent", "unknown") for data in self._memory_cache.values()))

    # -----------------------------------------------------------------------
    # Warm-up / Preloading
    # -----------------------------------------------------------------------

    def preload(self, key: str, value: Any, ttl: int = None) -> bool:
        """
        Preload a value into cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (optional)
        
        Returns:
            True if successful
        """
        try:
            cache_key = self._hash_key(f"preload:{key}")
            ttl = ttl or self.ttl_seconds
            
            cache_data = {
                "response": value,
                "timestamp": time.time(),
                "last_access": time.time(),
                "intent": "PRELOAD",
                "entities": (),
            }
            
            if self.backend == "redis":
                redis_client = _get_redis_client()
                if redis_client:
                    redis_client.setex(f"cache:{cache_key}", ttl, json.dumps(cache_data, default=str))
            else:
                with self._lock:
                    self._memory_cache[cache_key] = cache_data
            
            logger.info(f"Preloaded cache key: {key}")
            return True
            
        except Exception as e:
            logger.error(f"Preload failed for {key}: {e}")
            return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_cache_instance: Optional[CacheService] = None


def get_cache_service(
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    backend: str = "auto"
) -> CacheService:
    """Get or create the singleton cache service instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheService(
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
            backend=backend
        )
    return _cache_instance


def reset_cache_service():
    """Reset the cache service singleton (useful for testing)."""
    global _cache_instance
    if _cache_instance:
        _cache_instance.clear()
        _cache_instance = None
    logger.info("Cache service reset")


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def cached(ttl_seconds: int = None, intent_filter: str = None):
    """
    Decorator to cache function results.
    
    Example:
        @cached(ttl_seconds=60)
        def get_item_price(item_code):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache_service()
            
            # Generate cache key from function name and arguments
            key_parts = [func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = hashlib.md5(":".join(key_parts).encode()).hexdigest()
            
            # Try cache
            result = cache.get(cache_key, {}, "")
            if result:
                return result.get("response")
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            cache.set(cache_key, {}, "", {"response": result})
            
            return result
        return wrapper
    return decorator


# Global instance for easy import
cache_service = get_cache_service()