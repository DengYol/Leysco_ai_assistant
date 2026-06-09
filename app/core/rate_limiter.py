"""
app/core/rate_limiter.py
========================

Rate limiting implementation to prevent DDoS and brute force attacks.

Features:
  - Per-IP rate limiting
  - Per-user rate limiting
  - Per-endpoint rate limiting
  - Graceful degradation
  - Memory-based (development) and Redis-based (production)

Usage:
  from app.core.rate_limiter import RateLimiter, get_rate_limiter
  
  limiter = get_rate_limiter()
  
  # In your endpoint:
  @app.post("/api/auth/login")
  async def login(request: LoginRequest):
      await limiter.check_rate_limit(
          key=f"login:{request.username}",
          max_requests=5,
          window_seconds=300  # 5 requests per 5 minutes
      )
      # ... rest of login logic
"""

from typing import Dict, Tuple, Optional, List
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import Request
import asyncio
import logging
import os

logger = logging.getLogger(__name__)


# ============================================================================
# IN-MEMORY RATE LIMITER (Development/Testing)
# ============================================================================

class InMemoryRateLimiter:
    """
    Simple in-memory rate limiter using sliding window.
    
    Note: Not suitable for distributed systems.
    Use RedisRateLimiter for production.
    """
    
    def __init__(self):
        # Store: key -> list of (timestamp, request_count)
        self.requests: Dict[str, List[Tuple[datetime, int]]] = defaultdict(list)
        self.lock = asyncio.Lock()
    
    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> Tuple[bool, Dict[str, any]]:
        """
        Check if request is within rate limit.
        
        Args:
            key: Unique identifier (e.g., "login:user@example.com")
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds
        
        Returns:
            (allowed: bool, info: dict with limit details)
        """
        async with self.lock:
            now = datetime.now()
            window_start = now - timedelta(seconds=window_seconds)
            
            # Remove old requests outside the window
            if key in self.requests:
                self.requests[key] = [
                    (ts, count) for ts, count in self.requests[key]
                    if ts > window_start
                ]
            
            # Count requests in current window
            request_count = sum(count for _, count in self.requests[key])
            
            # Check if limit exceeded
            allowed = request_count < max_requests
            
            if allowed:
                # Add current request
                if key in self.requests and self.requests[key]:
                    self.requests[key][-1] = (now, self.requests[key][-1][1] + 1)
                else:
                    self.requests[key].append((now, 1))
            
            # Calculate reset time
            if self.requests[key]:
                oldest_request = self.requests[key][0][0]
                reset_time = oldest_request + timedelta(seconds=window_seconds)
            else:
                reset_time = now + timedelta(seconds=window_seconds)
            
            return allowed, {
                "limit": max_requests,
                "remaining": max(0, max_requests - request_count - 1),
                "reset": int(reset_time.timestamp()),
                "reset_at": reset_time.isoformat(),
            }
    
    async def clear_key(self, key: str):
        """Clear rate limit for a key"""
        async with self.lock:
            if key in self.requests:
                del self.requests[key]


# ============================================================================
# REDIS RATE LIMITER (Production)
# ============================================================================

class RedisRateLimiter:
    """
    Redis-based rate limiter for distributed systems.
    
    Uses Redis sorted sets for sliding window algorithm.
    Much more efficient for production use.
    """
    
    def __init__(self, redis_client=None):
        """
        Initialize Redis rate limiter.
        
        Args:
            redis_client: Redis client instance
        """
        self.redis = redis_client
        self.prefix = "rate_limit:"
    
    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> Tuple[bool, Dict[str, any]]:
        """
        Check rate limit using Redis sorted set.
        
        Uses sliding window: removes old requests before counting.
        """
        if not self.redis:
            # Fallback to in-memory if Redis not available
            logger.warning("Redis not available, falling back to in-memory limiter")
            fallback = InMemoryRateLimiter()
            return await fallback.check_rate_limit(key, max_requests, window_seconds)
        
        try:
            redis_key = f"{self.prefix}{key}"
            now_timestamp = datetime.now().timestamp()
            window_start = now_timestamp - window_seconds
            
            # Remove old entries
            await self.redis.zremrangebyscore(redis_key, 0, window_start)
            
            # Count current requests
            current_count = await self.redis.zcard(redis_key)
            
            allowed = current_count < max_requests
            
            if allowed:
                # Add current request
                await self.redis.zadd(redis_key, {str(now_timestamp): now_timestamp})
                # Set expiration
                await self.redis.expire(redis_key, window_seconds)
            
            reset_time = datetime.fromtimestamp(window_start + window_seconds)
            
            return allowed, {
                "limit": max_requests,
                "remaining": max(0, max_requests - current_count - (1 if allowed else 0)),
                "reset": int(reset_time.timestamp()),
                "reset_at": reset_time.isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            # Fallback to in-memory
            fallback = InMemoryRateLimiter()
            return await fallback.check_rate_limit(key, max_requests, window_seconds)


# ============================================================================
# UNIFIED RATE LIMITER
# ============================================================================

class RateLimiter:
    """
    Unified rate limiter with automatic fallback.
    
    Features:
    - Per-IP rate limiting
    - Per-user rate limiting
    - Per-endpoint rate limiting
    - Automatic Redis/in-memory selection
    - Configurable limits
    """
    
    def __init__(self):
        self.redis_available = False
        self.redis_client = None
        self.fallback_limiter = InMemoryRateLimiter()
        self._init_redis()
    
    def _init_redis(self):
        """Try to initialize Redis, fallback to in-memory if unavailable"""
        try:
            import redis
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=0,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_keepalive=True,
            )
            # Test connection
            self.redis_client.ping()
            self.redis_available = True
            logger.info("✅ Redis rate limiter initialized")
        except Exception as e:
            logger.warning(f"⚠️ Redis unavailable, using in-memory rate limiter: {e}")
            self.redis_available = False
    
    async def check_rate_limit(
        self,
        key: str,
        max_requests: int = 100,
        window_seconds: int = 60,
    ) -> Tuple[bool, Dict[str, any]]:
        """
        Check if request is allowed.
        
        Args:
            key: Unique identifier (e.g., "ip:192.168.1.1" or "user:123")
            max_requests: Max requests per window
            window_seconds: Time window in seconds
        
        Returns:
            (allowed: bool, info: dict)
        """
        if self.redis_available:
            limiter = RedisRateLimiter(self.redis_client)
        else:
            limiter = self.fallback_limiter
        
        return await limiter.check_rate_limit(key, max_requests, window_seconds)
    
    # ========================================================================
    # ENDPOINT-SPECIFIC RATE LIMITS
    # ========================================================================
    
    async def check_login_limit(self, identifier: str) -> Tuple[bool, Dict]:
        """
        Rate limit for login attempts.
        
        5 attempts per 5 minutes (brute force protection)
        """
        return await self.check_rate_limit(
            key=f"login:{identifier}",
            max_requests=5,
            window_seconds=300,
        )
    
    async def check_api_limit(self, ip: str) -> Tuple[bool, Dict]:
        """
        Rate limit for general API calls.
        
        100 requests per minute per IP
        """
        return await self.check_rate_limit(
            key=f"api:{ip}",
            max_requests=100,
            window_seconds=60,
        )
    
    async def check_chat_limit(self, user_id: str) -> Tuple[bool, Dict]:
        """
        Rate limit for chat endpoint.
        
        50 messages per minute per user
        """
        return await self.check_rate_limit(
            key=f"chat:{user_id}",
            max_requests=50,
            window_seconds=60,
        )
    
    async def check_export_limit(self, user_id: str) -> Tuple[bool, Dict]:
        """
        Rate limit for export operations.
        
        5 exports per hour per user (heavy operation)
        """
        return await self.check_rate_limit(
            key=f"export:{user_id}",
            max_requests=5,
            window_seconds=3600,
        )
    
    async def check_search_limit(self, user_id: str) -> Tuple[bool, Dict]:
        """
        Rate limit for search operations.
        
        120 per minute per user
        """
        return await self.check_rate_limit(
            key=f"search:{user_id}",
            max_requests=120,
            window_seconds=60,
        )


# ============================================================================
# GLOBAL RATE LIMITER INSTANCE
# ============================================================================

_rate_limiter_instance: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter instance"""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        _rate_limiter_instance = RateLimiter()
    return _rate_limiter_instance


# ============================================================================
# RATE LIMIT DECORATOR
# ============================================================================

from functools import wraps
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


def rate_limit(
    max_requests: int = 100,
    window_seconds: int = 60,
    key_func=None,
):
    """
    Decorator for applying rate limits to endpoints.
    
    Args:
        max_requests: Maximum requests allowed
        window_seconds: Time window in seconds
        key_func: Function to generate rate limit key (default: use client IP)
    
    Usage:
        @app.post("/api/auth/login")
        @rate_limit(max_requests=5, window_seconds=300)
        async def login(request: Request, data: LoginRequest):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: 'Request' = None, **kwargs):
            if not request:
                # Try to extract request from args
                for arg in args:
                    if isinstance(arg, type(request)):
                        request = arg
                        break
            
            if request:
                # Generate rate limit key
                if key_func:
                    key = key_func(request, *args, **kwargs)
                else:
                    client_ip = request.client.host if request.client else "unknown"
                    key = f"endpoint:{func.__name__}:{client_ip}"
                
                # Check rate limit
                limiter = get_rate_limiter()
                allowed, info = await limiter.check_rate_limit(
                    key=key,
                    max_requests=max_requests,
                    window_seconds=window_seconds,
                )
                
                if not allowed:
                    logger.warning(
                        f"Rate limit exceeded: {key}",
                        extra={"ip": request.client.host if request.client else "unknown"}
                    )
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "status": "rate_limit_exceeded",
                            "message": "Too many requests. Please try again later.",
                            "retry_after": info["reset"],
                            "reset_at": info["reset_at"],
                        },
                        headers={
                            "X-RateLimit-Limit": str(info["limit"]),
                            "X-RateLimit-Remaining": str(info["remaining"]),
                            "X-RateLimit-Reset": str(info["reset"]),
                            "Retry-After": str(info["reset"] - int(datetime.now().timestamp())),
                        },
                    )
            
            return await func(*args, request=request, **kwargs)
        
        return wrapper
    return decorator


# ============================================================================
# LOGGING & MONITORING
# ============================================================================

def log_rate_limit_event(
    event_type: str,
    key: str,
    ip: str,
    endpoint: str,
):
    """Log rate limiting events for monitoring"""
    logger.warning(
        f"Rate limit: {event_type}",
        extra={
            "event": event_type,
            "key": key,
            "ip": ip,
            "endpoint": endpoint,
            "timestamp": datetime.now().isoformat(),
        }
    )