import hashlib
import json
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self, ttl_seconds: int = 300):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl_seconds = ttl_seconds
        self.hit_count = 0
        self.miss_count = 0
    
    def _normalize_query(self, query: str) -> str:
        normalized = query.lower().strip()
        filler_words = ['please', 'can you', 'could you', 'me', 'the', 'some']
        words = normalized.split()
        words = [w for w in words if w not in filler_words]
        return ' '.join(words)
    
    def _get_cache_key(self, intent: str, entities: dict, message: str) -> str:
        normalized_msg = self._normalize_query(message)
        key_data = {
            'intent': intent,
            'entities': {k: v for k, v in entities.items() if v is not None},
            'message': normalized_msg
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, intent: str, entities: dict, message: str) -> Optional[Dict[str, Any]]:
        cache_key = self._get_cache_key(intent, entities, message)
        if cache_key not in self.cache:
            self.miss_count += 1
            return None
        cached_data = self.cache[cache_key]
        age = time.time() - cached_data['timestamp']
        if age > self.ttl_seconds:
            del self.cache[cache_key]
            self.miss_count += 1
            return None
        self.hit_count += 1
        logger.info(f"Cache HIT for '{message}' (age: {age:.0f}s)")
        return cached_data['response']
    
    def set(self, intent: str, entities: dict, message: str, response: Dict[str, Any]):
        cache_key = self._get_cache_key(intent, entities, message)
        self.cache[cache_key] = {
            'response': response,
            'timestamp': time.time(),
            'intent': intent,
            'message': message
        }
        logger.info(f"Cached response for '{message}'")
        if len(self.cache) > 100:
            sorted_keys = sorted(self.cache.keys(), key=lambda k: self.cache[k]['timestamp'])
            for old_key in sorted_keys[:20]:
                del self.cache[old_key]
    
    def clear(self):
        self.cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        total = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total * 100) if total > 0 else 0
        return {
            'cache_size': len(self.cache),
            'hit_count': self.hit_count,
            'miss_count': self.miss_count,
            'hit_rate': f"{hit_rate:.1f}%",
            'total_requests': total,
            'ttl_seconds': self.ttl_seconds
        }
    
    def should_cache(self, intent: str) -> bool:
        NEVER = {'GET_WAREHOUSE_STOCK', 'GET_CUSTOMER_ORDERS', 'GET_CUSTOMER_PRICE'}
        return intent not in NEVER

_cache_instance = None

def get_cache_service(ttl_seconds: int = 300) -> CacheService:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheService(ttl_seconds=ttl_seconds)
    return _cache_instance
