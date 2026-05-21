"""Inventory, items, and warehouse operations"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from .utils import normalize_response, normalize_warehouse_response, apply_limit, safe_float
from .cache import cache_api_result
from .constants import ITEM_CACHE_TTL, INVENTORY_CACHE_TTL

logger = logging.getLogger(__name__)


class InventoryHandler:
    """Handles items, inventory, and warehouse operations"""
    
    def __init__(self, parent):
        self.parent = parent
        self.session = parent.session
        self.base_url = parent.base_url
        self.auth_handler = parent.auth_handler
        self.cache_manager = parent.cache_manager
    
    def _record_cache_hit(self):
        """Record cache hit for statistics."""
        if hasattr(self.parent, '_record_cache_hit'):
            self.parent._record_cache_hit()
    
    def _record_cache_miss(self):
        """Record cache miss for statistics."""
        if hasattr(self.parent, '_record_cache_miss'):
            self.parent._record_cache_miss()
    
    @cache_api_result(ttl_seconds=ITEM_CACHE_TTL)
    def get_items(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get items from item masterdata"""
        try:
            if not self.auth_handler.ensure_auth():
                return []
                
            url = f"{self.base_url}/item_masterdata"
            params = {"page": 1, "per_page": 50, "search": search}
            self.parent._record_api_call()
            resp = self.session.get(url, params=params, timeout=15)
            
            if not self.auth_handler.check_auth(resp):
                return []
            
            self.parent._debug_response("ITEMS", resp)
            if resp.status_code == 200:
                return apply_limit(normalize_response(resp.json()), limit)
            return []
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch items: {e}")
            return []
    
    def get_item_by_name(self, name: str) -> Optional[Dict]:
        """Get a single item by name"""
        items = self.get_items(search=name, limit=1)
        return items[0] if items else None
    
    def get_item_by_code(self, item_code: str) -> Optional[Dict]:
        """
        Get a single item by its code.
        Used by quotation service to validate items.
        """
        try:
            if not self.auth_handler.ensure_auth():
                return None
            
            items = self.get_items(search=item_code, limit=5)
            
            if items:
                for item in items:
                    if item.get("ItemCode") == item_code:
                        logger.info(f"✅ Found item by code: {item_code} - {item.get('ItemName')}")
                        return item
            
            logger.warning(f"❌ Item not found by code: {item_code}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting item by code {item_code}: {e}")
            return None
    
    @cache_api_result(ttl_seconds=INVENTORY_CACHE_TTL)
    def get_inventory_report(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get inventory report with proper authentication handling"""
        try:
            if not self.auth_handler.ensure_auth():
                logger.warning("Not authenticated, cannot fetch inventory report")
                return []
            
            all_items = []
            page = 1
            per_page = min(limit, 500) if limit else 100
            
            while True:
                params = {"page": page, "per_page": per_page}
                if search:
                    params["search"] = search
                    
                url = f"{self.base_url}/inventory/report"
                self.parent._record_api_call()
                resp = self.session.get(url, params=params, timeout=15)
                
                if not self.auth_handler.check_auth(resp):
                    logger.warning("Authentication failed during inventory fetch")
                    break
                
                self.parent._debug_response("INVENTORY REPORT", resp)
                
                if resp.status_code != 200:
                    logger.error(f"Inventory report API error: {resp.status_code}")
                    break
                
                try:
                    data = resp.json()
                except Exception as e:
                    logger.error(f"Failed to parse inventory report JSON: {e}")
                    break
                
                items = self._parse_inventory_response(data)
                
                if not items:
                    break
                
                for item in items:
                    processed_item = {
                        "ItemCode": item.get("ItemCode") or item.get("item_code", ""),
                        "ItemName": item.get("ItemName") or item.get("item_name", ""),
                        "WhsCode": item.get("WhsCode") or item.get("whs_code", ""),
                        "CurrentOnHand": safe_float(item.get("CurrentOnHand") or item.get("OnHand")),
                        "CurrentIsCommited": safe_float(item.get("CurrentIsCommited") or item.get("IsCommited")),
                        "LastTransactionDate": item.get("LastTransactionDate", ""),
                        "PeriodOutQty": safe_float(item.get("PeriodOutQty")),
                        "Available": safe_float(item.get("CurrentOnHand") or item.get("OnHand")) - 
                                     safe_float(item.get("CurrentIsCommited") or item.get("IsCommited"))
                    }
                    all_items.append(processed_item)
                
                if len(items) < per_page:
                    break
                page += 1
                
                if limit and len(all_items) >= limit:
                    all_items = all_items[:limit]
                    break
            
            logger.info(f"✅ Retrieved {len(all_items)} inventory items")
            return all_items
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch inventory report: {e}", exc_info=True)
            return []
    
    def _parse_inventory_response(self, data: dict) -> List[Dict]:
        """Parse inventory response from various possible formats"""
        try:
            if data.get("ResultState") and data.get("ResponseData"):
                response_data = data["ResponseData"]
                
                if isinstance(response_data, dict) and "stocks" in response_data:
                    stocks = response_data["stocks"]
                    if isinstance(stocks, dict) and "data" in stocks:
                        return stocks["data"]
                elif isinstance(response_data, dict) and "data" in response_data:
                    return response_data["data"]
                elif isinstance(response_data, list):
                    return response_data
            else:
                if isinstance(data.get("data"), list):
                    return data["data"]
            
            return []
        except Exception as e:
            logger.error(f"Error parsing inventory response: {e}")
            return []
    
    def get_warehouses(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get warehouses from the correct API endpoint: /warehouse"""
        try:
            if not self.auth_handler.ensure_auth():
                logger.warning("Not authenticated, cannot fetch warehouses")
                return []
            
            url = f"{self.base_url}/warehouse"
            params = {"page": 1, "per_page": 100}
            if search:
                params["search"] = search
            
            logger.info(f"🏭 Fetching warehouses from: {url}")
            self.parent._record_api_call()
            resp = self.session.get(url, params=params, timeout=15)
            
            if not self.auth_handler.check_auth(resp):
                logger.warning("Authentication failed during warehouse fetch")
                return []
            
            self.parent._debug_response("WAREHOUSES", resp)
            
            if resp.status_code == 200:
                data = resp.json()
                warehouses = normalize_warehouse_response(data)
                return apply_limit(warehouses, limit)
            else:
                logger.error(f"Warehouse API error: {resp.status_code}")
                return []
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch warehouses: {e}")
            return []