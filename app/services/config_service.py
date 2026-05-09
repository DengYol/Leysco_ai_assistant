"""
app/services/config_service.py
===============================
Dynamic Configuration Service
Removes hardcoded values and enables per-tenant configuration.

FEATURES:
- Tenant-specific configuration overrides
- Global defaults with fallback
- Redis caching for performance
- Configuration change logging
"""

import logging
import json
from typing import Any, Optional, Dict
from datetime import datetime
from functools import wraps

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


# =========================================================
# DEFAULT CONFIGURATIONS (Global Fallbacks)
# =========================================================

DEFAULT_CONFIG = {
    # Inventory thresholds
    "inventory.critical_days": 3,
    "inventory.low_days": 7,
    "inventory.optimal_days": 30,
    "inventory.max_days": 60,
    "inventory.reorder_multiplier": 1.5,
    
    # Pricing thresholds
    "pricing.drop_threshold": 0.15,  # 15% drop triggers alert
    "pricing.hike_threshold": 0.20,  # 20% hike triggers alert
    "pricing.bulk_discount_threshold": 100,  # Units for bulk discount
    
    # Customer analytics
    "customer.churn_risk_days": 60,
    "customer.high_value_threshold": 50000,  # KES
    "customer.inactive_days": 90,
    
    # Inventory classification
    "inventory.slow_mover_days": 90,
    "inventory.fast_mover_days": 30,
    
    # SKIP lists (items to exclude)
    "skip.item_groups": ["PACKING MATERIAL", "RAW MATERIAL", "PACKAGING"],
    "skip.item_prefixes": ["RMST", "RMOP", "RMFC", "RMPA", "RMPK", "PACK", "BAG", "BOX"],
    
    # Business partner keywords
    "bp.customer_keywords": ["vendor", "supplier"],
    "bp.lead_keywords": ["lead", "prospect"],
    
    # Notification settings
    "notifications.max_per_user": 50,
    "notifications.scan_interval_minutes": 15,
    "notifications.critical_score": 80,
    "notifications.high_score": 60,
    "notifications.medium_score": 40,
    
    # Performance
    "performance.max_results_default": 10,
    "performance.max_results_limit": 100,
    "performance.session_timeout_minutes": 30,
    
    # Feature flags
    "features.proactive_notifications": True,
    "features.conversation_memory": True,
    "features.activity_logging": True,
    "features.analytics_enabled": True,
    
    # EOQ calculations
    "eoq.ordering_cost": 500.0,  # KES per order
    "eoq.holding_cost_percent": 0.25,  # 25% of unit price
    
    # Cache TTLs
    "cache.inventory_ttl_seconds": 120,
    "cache.price_ttl_seconds": 300,
    "cache.customer_ttl_seconds": 300,
    "cache.item_ttl_seconds": 300,
    "cache.delivery_ttl_seconds": 60,
    "cache.analytics_ttl_seconds": 3600,
    
    # Anomaly detection thresholds
    "anomaly.sales_zscore_threshold": 2.5,
    "anomaly.sales_percent_change": 0.30,
    "anomaly.stock_drop_percent": 0.50,
    "anomaly.price_change_percent": 0.20,
    "anomaly.min_data_points": 14,
    "anomaly.lookback_days": 30,
}


class ConfigService:
    """
    Dynamic configuration service with per-tenant overrides.
    """
    
    CACHE_TTL = 300  # 5 minutes
    CACHE_PREFIX = "config:"
    
    def __init__(self):
        self.cache = get_cache_service()
        self._local_cache = {}  # Fallback in-memory cache
        self._defaults = DEFAULT_CONFIG.copy()
    
    def _get_cache_key(self, tenant_code: str, key: str) -> str:
        """Generate cache key for a configuration value."""
        return f"{self.CACHE_PREFIX}{tenant_code}:{key}"
    
    async def get(
        self,
        key: str,
        default: Any = None,
        tenant_code: Optional[str] = None
    ) -> Any:
        """
        Get a configuration value.
        
        Priority:
        1. Tenant-specific override (if tenant_code provided)
        2. Global default from DEFAULT_CONFIG
        3. Provided default value
        """
        # Try tenant-specific config first
        if tenant_code:
            cache_key = self._get_cache_key(tenant_code, key)
            
            # Check Redis cache
            cached = await self.cache.get_simple_async(cache_key)
            if cached is not None:
                return cached
            
            # Check local cache
            local_key = f"{tenant_code}:{key}"
            if local_key in self._local_cache:
                return self._local_cache[local_key]
        
        # Fallback to global default
        if key in self._defaults:
            return self._defaults[key]
        
        # Fallback to provided default
        return default
    
    async def set(
        self,
        key: str,
        value: Any,
        tenant_code: str,
        updated_by: Optional[str] = None
    ) -> bool:
        """
        Set a tenant-specific configuration value.
        """
        try:
            # Store in cache
            cache_key = self._get_cache_key(tenant_code, key)
            await self.cache.set_simple_async(cache_key, value, ttl=self.CACHE_TTL)
            
            # Store in local cache
            self._local_cache[f"{tenant_code}:{key}"] = value
            
            logger.info(f"✅ Config updated: {tenant_code}:{key} = {value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set config {key}: {e}")
            return False
    
    async def delete(self, key: str, tenant_code: str) -> bool:
        """Delete a tenant-specific configuration (revert to default)."""
        try:
            # Remove from cache
            cache_key = self._get_cache_key(tenant_code, key)
            await self.cache.delete_simple_async(cache_key)
            
            # Remove from local cache
            local_key = f"{tenant_code}:{key}"
            if local_key in self._local_cache:
                del self._local_cache[local_key]
            
            logger.info(f"✅ Config deleted: {tenant_code}:{key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete config {key}: {e}")
            return False
    
    async def get_all_for_tenant(self, tenant_code: str) -> Dict[str, Any]:
        """Get all configuration values for a tenant."""
        return self._defaults.copy()
    
    async def get_int(self, key: str, tenant_code: Optional[str] = None, default: int = 0) -> int:
        """Get integer configuration value."""
        value = await self.get(key, default, tenant_code)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    async def get_float(self, key: str, tenant_code: Optional[str] = None, default: float = 0.0) -> float:
        """Get float configuration value."""
        value = await self.get(key, default, tenant_code)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    async def get_bool(self, key: str, tenant_code: Optional[str] = None, default: bool = False) -> bool:
        """Get boolean configuration value."""
        value = await self.get(key, default, tenant_code)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1", "on")
        return bool(value)
    
    async def get_list(self, key: str, tenant_code: Optional[str] = None, default: list = None) -> list:
        """Get list configuration value."""
        value = await self.get(key, default, tenant_code)
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except:
                return [v.strip() for v in value.split(",")]
        return default or []
    
    async def invalidate_tenant_cache(self, tenant_code: str) -> None:
        """Invalidate all cached configs for a tenant."""
        keys_to_delete = [k for k in self._local_cache if k.startswith(f"{tenant_code}:")]
        for key in keys_to_delete:
            del self._local_cache[key]
        logger.info(f"🗑️ Invalidated config cache for tenant: {tenant_code}")
    
    def get_default(self, key: str) -> Any:
        """Get global default value."""
        return self._defaults.get(key)
    
    def set_default(self, key: str, value: Any) -> None:
        """Set global default value (for system configuration)."""
        self._defaults[key] = value
        logger.info(f"📝 Global default updated: {key} = {value}")


# Singleton instance
_config_service = None


def get_config_service() -> ConfigService:
    """Get or create ConfigService singleton."""
    global _config_service
    if _config_service is None:
        _config_service = ConfigService()
    return _config_service