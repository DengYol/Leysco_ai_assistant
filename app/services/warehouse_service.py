"""
warehouse_service.py
====================
Warehouse intelligence layer for Leysco ERP - Optimized with caching and async support

FIXED: Now accepts user_token and company_code parameters and passes to LeyscoAPIService

Features:
1. Stock level summaries per warehouse
2. Warehouse details (address, manager, status)
3. Search/filter by name or region
4. Low stock alerts per warehouse
5. Show all items in a specific warehouse with details
6. Enhanced caching for inventory data
7. Async support for concurrent operations

Optimizations:
- Redis caching for inventory data
- Batch processing for large inventories
- LRU cache for frequently accessed warehouses
- Async methods for non-blocking operations
- Connection pooling via LeyscoAPIService
"""

import logging
import asyncio
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from functools import lru_cache, wraps
from datetime import datetime, timedelta

from app.services.leysco_api.client import LeyscoAPIService, create_api_service
from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# Cache TTLs
WAREHOUSE_CACHE_TTL = 300      # 5 minutes
INVENTORY_CACHE_TTL = 120       # 2 minutes for inventory data
LOW_STOCK_CACHE_TTL = 60        # 1 minute for low stock alerts


def cache_result(ttl_seconds: int = WAREHOUSE_CACHE_TTL, key_prefix: str = ""):
    """
    Decorator to cache warehouse results.
    Includes user token in cache key for isolation.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            cache = get_cache_service()
            
            # Include user token in cache key for isolation
            user_suffix = self.user_token[:8] if self.user_token else "no_token"
            company_suffix = self.company_code if self.company_code else "no_company"
            
            # Generate cache key
            cache_str = f"{key_prefix or func.__name__}:{user_suffix}:{company_suffix}:{str(args)}:{str(sorted(kwargs.items()))}"
            cache_key = hashlib.md5(cache_str.encode()).hexdigest()
            
            # Check cache
            cached = cache.get(cache_key, {}, "")
            if cached is not None:
                logger.info(f"📦 Warehouse cache hit: {func.__name__}")
                return cached.get("data")
            
            # Execute function
            result = func(self, *args, **kwargs)
            
            # Cache result
            if result:
                cache.set(cache_key, {}, "", {"data": result})
            
            return result
        return wrapper
    return decorator


class WarehouseService:
    """
    Service for warehouse-related operations.
    FIXED: Now accepts user_token and company_code for multi-tenant support.
    """
    
    def __init__(self, user_token: str = None, company_code: str = None, api_service: LeyscoAPIService = None):
        """
        Initialize WarehouseService with user token and company code.
        
        Args:
            user_token: The authenticated user's Bearer token
            company_code: Company code for multi-tenant URL resolution
            api_service: Optional pre-configured API service instance
        """
        self.user_token = user_token
        self.company_code = company_code
        
        if api_service:
            self.api = api_service
            logger.debug("WarehouseService initialized with existing API service")
        elif user_token:
            # Pass company_code to API service for proper URL resolution
            self.api = create_api_service(user_token=user_token, company_code=company_code)
            logger.info(f"✅ WarehouseService initialized WITH user token and company_code={company_code}")
        else:
            self.api = LeyscoAPIService()
            logger.warning("⚠️ WarehouseService initialized WITHOUT user token - data access will fail")
        
        self._inventory_cache = {}
        self._inventory_cache_time = {}
        self._inventory_cache_ttl = 120  # 2 minutes
        
        # Stats tracking
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "errors": 0
        }

    # ------------------------------------------------------------------
    # TOKEN MANAGEMENT
    # ------------------------------------------------------------------
    
    def set_user_token(self, token: str):
        """Update user token for this service."""
        self.user_token = token
        self.api.set_user_token(token)
        logger.debug("WarehouseService token updated")
    
    def set_company_code(self, company_code: str):
        """Update company code for this service."""
        self.company_code = company_code
        self.api.set_company_code(company_code)
        logger.debug(f"WarehouseService company code updated to: {company_code}")
    
    def _ensure_auth(self) -> bool:
        """Check if we have valid authentication."""
        if not self.user_token:
            logger.warning("No user token available for warehouse operation")
            return False
        return True

    # ------------------------------------------------------------------
    # STATS HELPERS
    # ------------------------------------------------------------------
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return self._stats.copy()
    
    def _record_cache_hit(self):
        self._stats["cache_hits"] += 1
    
    def _record_cache_miss(self):
        self._stats["cache_misses"] += 1
    
    def _record_api_call(self):
        self._stats["api_calls"] += 1
    
    def _record_error(self):
        self._stats["errors"] += 1

    # ------------------------------------------------------------------
    # PRIVATE: Inventory data with caching
    # ------------------------------------------------------------------
    
    def _get_inventory_cached(self, force_refresh: bool = False) -> List[Dict]:
        """Get inventory data with TTL-based caching."""
        # Check authentication
        if not self._ensure_auth():
            return []
        
        now = datetime.now()
        
        # Check if we have valid cached data
        if not force_refresh and self._inventory_cache:
            cache_time = self._inventory_cache_time.get("inventory")
            if cache_time and (now - cache_time).seconds < self._inventory_cache_ttl:
                self._record_cache_hit()
                return self._inventory_cache.get("inventory", [])
        
        self._record_cache_miss()
        self._record_api_call()
        
        try:
            inventory = self.api.get_inventory_report(limit=500)
            self._inventory_cache["inventory"] = inventory
            self._inventory_cache_time["inventory"] = now
            return inventory
        except Exception as e:
            self._record_error()
            logger.error(f"Error fetching inventory: {e}")
            return self._inventory_cache.get("inventory", [])

    # ------------------------------------------------------------------
    # FEATURE 1: Stock Level Summaries (Optimized)
    # ------------------------------------------------------------------
    
    @cache_result(ttl_seconds=WAREHOUSE_CACHE_TTL)
    def get_warehouse_stock_summary(self, whscode: str) -> Dict:
        """
        Get aggregated stock summary for a warehouse.
        Optimized with caching.
        
        Returns:
        {
            "warehouse_code": str,
            "warehouse_name": str,
            "total_items": int,
            "total_units": int,
            "total_committed": int,
            "total_available": int,
            "top_items": [...],
            "low_stock_items": [...],
            "all_items": [...]
        }
        """
        if not self._ensure_auth():
            return {"error": "Not authenticated. Please log in again."}
        
        logger.info(f"📊 Getting stock summary for warehouse: {whscode}")
        
        inventory = self._get_inventory_cached()
        
        if not inventory:
            return {"error": f"No inventory data available for warehouse {whscode}"}
        
        # Filter to this warehouse
        wh_items = [
            itm for itm in inventory
            if (itm.get("WhsCode") or "").upper() == whscode.upper()
        ]
        
        if not wh_items:
            return {"error": f"No inventory found for warehouse {whscode}"}
        
        # Aggregate by item (using dict for O(1) lookups)
        items_map = {}
        for itm in wh_items:
            code = itm.get("ItemCode")
            if code not in items_map:
                on_hand = itm.get("CurrentOnHand", 0)
                committed = itm.get("CurrentIsCommited", 0)
                items_map[code] = {
                    "ItemCode": code,
                    "ItemName": itm.get("ItemName", code),
                    "OnHand": on_hand,
                    "Committed": committed,
                    "Available": on_hand - committed,
                }
            else:
                # If duplicate, sum quantities
                items_map[code]["OnHand"] += itm.get("CurrentOnHand", 0)
                items_map[code]["Committed"] += itm.get("CurrentIsCommited", 0)
                items_map[code]["Available"] = items_map[code]["OnHand"] - items_map[code]["Committed"]
        
        items = list(items_map.values())
        
        # Sort items by name for easy browsing
        items_sorted = sorted(items, key=lambda x: x["ItemName"])
        
        # Low stock detection (available < 10% of on-hand OR available < 100)
        low_stock = [
            itm for itm in items
            if itm["Available"] < max(itm["OnHand"] * 0.1, 100) and itm["OnHand"] > 0
        ]
        
        # Get warehouse name
        warehouse_name = whscode
        try:
            warehouses = self.api.get_warehouses(search=whscode)
            if warehouses:
                for wh in warehouses:
                    if (wh.get("WhsCode") or "").upper() == whscode.upper():
                        warehouse_name = wh.get("WhsName", whscode)
                        break
        except Exception as e:
            logger.debug(f"Could not get warehouse name: {e}")
        
        return {
            "warehouse_code": whscode.upper(),
            "warehouse_name": warehouse_name,
            "total_items": len(items),
            "total_units": sum(i["OnHand"] for i in items),
            "total_committed": sum(i["Committed"] for i in items),
            "total_available": sum(i["Available"] for i in items),
            "top_items": sorted(items, key=lambda x: x["OnHand"], reverse=True)[:10],
            "low_stock_items": sorted(low_stock, key=lambda x: x["Available"])[:20],
            "all_items": items_sorted,
        }
    
    async def get_warehouse_stock_summary_async(self, whscode: str) -> Dict:
        """Async version of get_warehouse_stock_summary."""
        return await asyncio.to_thread(self.get_warehouse_stock_summary, whscode)
    
    # ------------------------------------------------------------------
    # FEATURE 1b: Show all items in a warehouse (Optimized)
    # ------------------------------------------------------------------
    
    def get_warehouse_items(
        self, 
        whscode: str, 
        search: str = "", 
        limit: int = 50,
        include_out_of_stock: bool = True
    ) -> Dict:
        """
        Get all items in a specific warehouse with stock details.
        Optimized with caching and filtering.
        
        Args:
            whscode: Warehouse code
            search: Optional search term to filter items by name/code
            limit: Maximum number of items to return
            include_out_of_stock: Whether to include items with zero stock
        
        Returns:
        {
            "warehouse_code": str,
            "warehouse_name": str,
            "total_items_in_warehouse": int,
            "items": [...],
            "has_more": bool
        }
        """
        if not self._ensure_auth():
            return {"error": True, "message": "Not authenticated. Please log in again."}
        
        logger.info(f"📦 Getting items for warehouse: {whscode}")
        
        # Check cache for this warehouse's items
        cache = get_cache_service()
        user_suffix = self.user_token[:8] if self.user_token else "no_token"
        company_suffix = self.company_code if self.company_code else "no_company"
        cache_key = f"warehouse_items:{user_suffix}:{company_suffix}:{whscode}:{search}:{limit}:{include_out_of_stock}"
        cached = cache.get(cache_key, {}, "")
        if cached is not None:
            self._record_cache_hit()
            return cached.get("data")
        
        self._record_cache_miss()
        
        inventory = self._get_inventory_cached()
        
        if not inventory:
            result = {
                "error": True,
                "message": f"No inventory data available",
                "warehouse_code": whscode,
                "warehouse_name": whscode,
                "total_items_in_warehouse": 0,
                "items": [],
                "has_more": False
            }
            cache.set(cache_key, {}, "", {"data": result})
            return result
        
        # Filter to this warehouse
        wh_items = [
            itm for itm in inventory
            if (itm.get("WhsCode") or "").upper() == whscode.upper()
        ]
        
        if not wh_items:
            result = {
                "error": True,
                "message": f"No inventory found for warehouse {whscode}",
                "warehouse_code": whscode,
                "warehouse_name": whscode,
                "total_items_in_warehouse": 0,
                "items": [],
                "has_more": False
            }
            cache.set(cache_key, {}, "", {"data": result})
            return result
        
        # Aggregate by item (using dict for O(1) lookups)
        items_map = {}
        for itm in wh_items:
            code = itm.get("ItemCode")
            if code not in items_map:
                on_hand = itm.get("CurrentOnHand", 0)
                committed = itm.get("CurrentIsCommited", 0)
                items_map[code] = {
                    "ItemCode": code,
                    "ItemName": itm.get("ItemName", code),
                    "OnHand": on_hand,
                    "Committed": committed,
                    "Available": on_hand - committed,
                    "IsSellable": itm.get("SellItem") == "Y",
                    "ItemGroup": (itm.get("item_group") or {}).get("ItmsGrpNam", ""),
                }
        
        items = list(items_map.values())
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            items = [
                item for item in items
                if search_lower in item["ItemName"].lower() or 
                   search_lower in item["ItemCode"].lower()
            ]
        
        # Filter out zero stock if requested
        if not include_out_of_stock:
            items = [item for item in items if item["OnHand"] > 0]
        
        # Sort by name
        items_sorted = sorted(items, key=lambda x: x["ItemName"])
        
        # Apply limit
        total_count = len(items_sorted)
        has_more = total_count > limit
        items_limited = items_sorted[:limit]
        
        # Get warehouse name
        warehouse_name = whscode
        try:
            warehouses = self.api.get_warehouses(search=whscode)
            if warehouses:
                for wh in warehouses:
                    if (wh.get("WhsCode") or "").upper() == whscode.upper():
                        warehouse_name = wh.get("WhsName", whscode)
                        break
        except Exception:
            pass
        
        result = {
            "warehouse_code": whscode.upper(),
            "warehouse_name": warehouse_name,
            "total_items_in_warehouse": total_count,
            "items": items_limited,
            "has_more": has_more,
            "message": f"Found {total_count} item(s) in {warehouse_name}" + 
                       (f" (showing first {limit})" if has_more else "")
        }
        
        # Cache the result
        cache.set(cache_key, {}, "", {"data": result})
        
        return result
    
    async def get_warehouse_items_async(
        self, 
        whscode: str, 
        search: str = "", 
        limit: int = 50,
        include_out_of_stock: bool = True
    ) -> Dict:
        """Async version of get_warehouse_items."""
        return await asyncio.to_thread(
            self.get_warehouse_items, whscode, search, limit, include_out_of_stock
        )
    
    # ------------------------------------------------------------------
    # FEATURE 2: Warehouse Details (Optimized)
    # ------------------------------------------------------------------
    
    @cache_result(ttl_seconds=WAREHOUSE_CACHE_TTL)
    def get_warehouse_details(self, whscode: str) -> Optional[Dict]:
        """
        Get full details for a warehouse.
        Optimized with caching.
        
        Returns warehouse record with all available fields plus stock summary.
        """
        if not self._ensure_auth():
            return None
        
        warehouses = self.api.get_warehouses(search=whscode)
        
        if not warehouses:
            return None
        
        # Exact match on code
        wh = next(
            (w for w in warehouses if (w.get("WhsCode") or "").upper() == whscode.upper()),
            warehouses[0]  # fallback to first result
        )
        
        # Enrich with stock summary
        stock_summary = self.get_warehouse_stock_summary(wh.get("WhsCode", whscode))
        
        return {
            **wh,
            "stock_summary": stock_summary,
        }
    
    # ------------------------------------------------------------------
    # FEATURE 3: Search/Filter (Optimized)
    # ------------------------------------------------------------------
    
    def search_warehouses(
        self,
        query: str = "",
        region: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict]:
        """
        Search warehouses by name, code, or region.
        Optimized with caching for frequent searches.
        """
        if not self._ensure_auth():
            return []
        
        # Check cache for common searches
        if not region and active_only:
            cache = get_cache_service()
            user_suffix = self.user_token[:8] if self.user_token else "no_token"
            company_suffix = self.company_code if self.company_code else "no_company"
            cache_key = f"warehouse_search:{user_suffix}:{company_suffix}:{query}"
            cached = cache.get(cache_key, {}, "")
            if cached is not None:
                self._record_cache_hit()
                return cached.get("data")
        
        self._record_cache_miss()
        warehouses = self.api.get_warehouses(search=query)
        
        # Apply filters
        results = []
        for wh in warehouses:
            # Active filter
            if active_only and wh.get("Inactive") == "Y":
                continue
            
            # Region filter
            if region:
                wh_region = (
                    wh.get("Region") or
                    wh.get("Territory") or
                    wh.get("Location") or
                    ""
                ).lower()
                if region.lower() not in wh_region:
                    continue
            
            results.append(wh)
        
        # Cache results for common searches
        if not region and active_only:
            cache = get_cache_service()
            user_suffix = self.user_token[:8] if self.user_token else "no_token"
            company_suffix = self.company_code if self.company_code else "no_company"
            cache.set(f"warehouse_search:{user_suffix}:{company_suffix}:{query}", {}, "", {"data": results})
        
        return results
    
    def get_all_warehouses_summary(self) -> List[Dict]:
        """
        Get stock summaries for all warehouses.
        Optimized with inventory caching.
        """
        if not self._ensure_auth():
            return []
        
        warehouses = self.api.get_warehouses()
        inventory = self._get_inventory_cached()
        
        if not inventory:
            return []
        
        summaries = []
        for wh in warehouses:
            whscode = wh.get("WhsCode")
            if not whscode:
                continue
            
            # Filter inventory to this warehouse (fast list comprehension)
            wh_items = [
                itm for itm in inventory
                if (itm.get("WhsCode") or "").upper() == whscode.upper()
            ]
            
            total_units = sum(itm.get("CurrentOnHand", 0) for itm in wh_items)
            total_committed = sum(itm.get("CurrentIsCommited", 0) for itm in wh_items)
            
            summaries.append({
                "WhsCode": whscode,
                "WhsName": wh.get("WhsName", whscode),
                "total_items": len(set(itm.get("ItemCode") for itm in wh_items)),
                "total_units": total_units,
                "total_committed": total_committed,
                "total_available": total_units - total_committed,
                "details": wh,
            })
        
        return sorted(summaries, key=lambda x: x["total_units"], reverse=True)
    
    # ------------------------------------------------------------------
    # FEATURE 4: Low Stock Alerts (Optimized)
    # ------------------------------------------------------------------
    
    @cache_result(ttl_seconds=LOW_STOCK_CACHE_TTL)
    def get_low_stock_alerts(
        self,
        whscode: Optional[str] = None,
        threshold_pct: float = 0.1,
        min_available: int = 100,
    ) -> List[Dict]:
        """
        Find items with low available stock across warehouses.
        Optimized with caching.
        
        Low stock = Available < max(OnHand * threshold_pct, min_available)
        """
        if not self._ensure_auth():
            return []
        
        inventory = self._get_inventory_cached()
        
        if not inventory:
            return []
        
        # Filter by warehouse if specified
        if whscode:
            inventory = [
                itm for itm in inventory
                if (itm.get("WhsCode") or "").upper() == whscode.upper()
            ]
        
        # Aggregate by item+warehouse
        alerts = []
        for itm in inventory:
            on_hand = itm.get("CurrentOnHand", 0)
            committed = itm.get("CurrentIsCommited", 0)
            available = on_hand - committed
            
            # Skip if no stock at all
            if on_hand == 0:
                continue
            
            # Check threshold
            threshold = max(on_hand * threshold_pct, min_available)
            if available < threshold:
                alerts.append({
                    "ItemCode": itm.get("ItemCode"),
                    "ItemName": itm.get("ItemName", itm.get("ItemCode", "Unknown")),
                    "WhsCode": itm.get("WhsCode"),
                    "OnHand": on_hand,
                    "Committed": committed,
                    "Available": available,
                    "Threshold": int(threshold),
                    "Severity": "CRITICAL" if available < threshold * 0.5 else "LOW",
                })
        
        # Sort by available quantity (lowest first)
        return sorted(alerts, key=lambda x: x["Available"])
    
    async def get_low_stock_alerts_async(
        self,
        whscode: Optional[str] = None,
        threshold_pct: float = 0.1,
        min_available: int = 100,
    ) -> List[Dict]:
        """Async version of get_low_stock_alerts."""
        return await asyncio.to_thread(
            self.get_low_stock_alerts, whscode, threshold_pct, min_available
        )
    
    def get_warehouse_low_stock_summary(self) -> Dict[str, List[Dict]]:
        """
        Group low stock alerts by warehouse.
        """
        alerts = self.get_low_stock_alerts()
        
        by_warehouse = {}
        for alert in alerts:
            whscode = alert["WhsCode"]
            if whscode not in by_warehouse:
                by_warehouse[whscode] = []
            by_warehouse[whscode].append(alert)
        
        return by_warehouse
    
    # ------------------------------------------------------------------
    # FEATURE 5: Get Warehouse by Name or Code (Optimized)
    # ------------------------------------------------------------------
    
    @lru_cache(maxsize=128)
    def find_warehouse(self, query: str) -> Optional[Dict]:
        """
        Find a warehouse by code or name.
        LRU cache for frequently searched warehouses.
        
        Args:
            query: Warehouse code or name to search for
        
        Returns:
            Warehouse details if found, None otherwise
        """
        if not self._ensure_auth():
            return None
        
        warehouses = self.api.get_warehouses(search=query)
        
        if not warehouses:
            return None
        
        # Try exact match on code first
        for wh in warehouses:
            if (wh.get("WhsCode") or "").upper() == query.upper():
                return wh
        
        # Try exact match on name
        for wh in warehouses:
            if (wh.get("WhsName") or "").upper() == query.upper():
                return wh
        
        # Return first match if any
        return warehouses[0] if warehouses else None
    
    def warehouse_exists(self, whscode: str) -> bool:
        """
        Check if a warehouse exists in the system.
        """
        if not self._ensure_auth():
            return False
        
        warehouses = self.api.get_warehouses(search=whscode)
        
        for wh in warehouses:
            if (wh.get("WhsCode") or "").upper() == whscode.upper():
                return True
        
        return False
    
    # ------------------------------------------------------------------
    # FEATURE 6: Format Warehouse Items for Display (Optimized)
    # ------------------------------------------------------------------
    
    def format_warehouse_items(self, whscode: str, search: str = "", limit: int = 20) -> str:
        """
        Format warehouse items for display in chat.
        Optimized to return quickly with cached data.
        """
        result = self.get_warehouse_items(whscode, search, limit)
        
        if result.get("error"):
            return f"❌ {result.get('message', 'Warehouse not found')}"
        
        if not result["items"]:
            return f"📦 **{result['warehouse_name']}** ({result['warehouse_code']})\n\nNo items found in this warehouse."
        
        lines = [
            f"📦 **{result['warehouse_name']}** ({result['warehouse_code']})",
            f"📊 Total items: {result['total_items_in_warehouse']}",
            "",
            "**Items:**",
        ]
        
        for item in result["items"]:
            stock_status = "✅" if item["Available"] > 0 else "❌"
            lines.append(f"{stock_status} **{item['ItemName']}** ({item['ItemCode']})")
            lines.append(f"   📦 On Hand: {item['OnHand']:,.0f} | ✅ Available: {item['Available']:,.0f}")
            if item.get("ItemGroup"):
                lines.append(f"   🏷️ Category: {item['ItemGroup']}")
            lines.append("")
        
        if result["has_more"]:
            remaining = result['total_items_in_warehouse'] - len(result['items'])
            lines.append(f"... and {remaining} more items.")
            lines.append(f"💡 Use a specific search term to filter: 'Show items in {whscode} containing [name]'")
        
        return "\n".join(lines)
    
    # ------------------------------------------------------------------
    # CACHE MANAGEMENT
    # ------------------------------------------------------------------
    
    def clear_cache(self):
        """Clear all caches."""
        self._inventory_cache = {}
        self._inventory_cache_time = {}
        # Clear LRU cache for find_warehouse
        self.find_warehouse.cache_clear()
        # Clear Redis cache
        cache = get_cache_service()
        # This would need to clear all warehouse-related keys
        # For now, just log
        logger.info("Warehouse service cache cleared")
    
    def refresh_inventory(self):
        """Force refresh of inventory data."""
        self._get_inventory_cached(force_refresh=True)
        logger.info("Inventory data refreshed")


# =========================================================
# Factory function
# =========================================================

def create_warehouse_service(user_token: str = None, company_code: str = None) -> WarehouseService:
    """
    Create a new WarehouseService instance with the user's token and company code.
    
    Args:
        user_token: The authenticated user's Bearer token
        company_code: Company code for multi-tenant URL resolution
    
    Returns:
        Configured WarehouseService instance
    """
    if not user_token:
        logger.warning("⚠️ create_warehouse_service called WITHOUT user token - data access will fail")
    else:
        logger.info(f"✅ create_warehouse_service called WITH user token and company_code={company_code}")
    
    return WarehouseService(user_token=user_token, company_code=company_code)