"""
app/core/tenant_context.py
===========================
Tenant context management with per-request token isolation
"""

from contextvars import ContextVar
from typing import Optional, Dict
from dataclasses import dataclass
import hashlib
import logging

logger = logging.getLogger(__name__)


@dataclass
class TenantContext:
    """Tenant context for the current request"""
    company_code: str
    company_id: int
    user_id: int
    user_email: str
    user_role: str
    user_token: str  # Pass-through token - never stored permanently
    
    @property
    def cache_prefix(self) -> str:
        """Generate tenant-isolated cache prefix"""
        return f"tenant:{self.company_code}:{self.user_id}"
    
    @property
    def token_hash(self) -> str:
        """Masked token for logging (first 8 chars only)"""
        if len(self.user_token) > 8:
            return f"{self.user_token[:8]}...{self.user_token[-4:]}"
        return "***MASKED***"
    
    def get_cache_key(self, key: str) -> str:
        """Generate tenant-isolated cache key"""
        return f"{self.cache_prefix}:{key}"


# ContextVar for thread-safe tenant propagation
_current_tenant: ContextVar[Optional[TenantContext]] = ContextVar(
    'current_tenant', default=None
)


def get_current_tenant() -> Optional[TenantContext]:
    """Get current tenant context for this request"""
    return _current_tenant.get()


def set_current_tenant(tenant: TenantContext) -> None:
    """Set current tenant context for this request"""
    _current_tenant.set(tenant)
    logger.debug(f"Tenant context set for: {tenant.company_code} (User: {tenant.user_id})")


def clear_current_tenant() -> None:
    """Clear current tenant context"""
    _current_tenant.set(None)


class TenantContextManager:
    """Context manager for tenant operations"""
    
    def __init__(self, tenant: TenantContext):
        self.tenant = tenant
        self._previous = None
    
    def __enter__(self):
        self._previous = get_current_tenant()
        set_current_tenant(self.tenant)
        return self.tenant
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        set_current_tenant(self._previous)