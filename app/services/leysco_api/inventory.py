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
        """
        Get items from item masterdata.
        Uses the correct endpoint: /api/v1/item_masterdata
        """
        try:
            if not self.auth_handler.ensure_auth():
                return []
            
            # FIXED: Use correct endpoint with /api/v1 prefix
            # Remove trailing /api/v1 from base_url if present to avoid double slash
            base = self.base_url.rstrip('/')
            # If base_url already contains /api/v1, don't add it again
            if base.endswith('/api/v1'):
                url = f"{base}/item_masterdata"
            else:
                url = f"{base}/api/v1/item_masterdata"
            
            params = {"page": 1, "per_page": min(limit, 100) if limit else 50}
            if search:
                params["search"] = search
            
            logger.info(f"📦 Fetching items from: {url}")
            self.parent._record_api_call()
            resp = self.session.get(url, params=params, timeout=15)
            
            if not self.auth_handler.check_auth(resp):
                return []
            
            self.parent._debug_response("ITEMS", resp)
            
            if resp.status_code == 200:
                data = resp.json()
                items = self._parse_items_response(data)
                logger.info(f"✅ Retrieved {len(items)} items")
                return apply_limit(items, limit)
            else:
                logger.warning(f"Items API returned {resp.status_code}")
                return []
                
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch items: {e}")
            return []
    
    def _parse_items_response(self, data: dict) -> List[Dict]:
        """
        Parse items response from /api/v1/item_masterdata.
        
        Response format:
        {
            "ResultState": true,
            "ResultCode": 1200,
            "ResultDesc": "Operation Was Successful",
            "ResponseData": {
                "current_page": 1,
                "data": [
                    {
                        "id": 36847,
                        "ItemName": "CRR F PAN HD TAP SCREW ST",
                        "ItemCode": "SZN3200340",
                        ...
                    }
                ]
            }
        }
        """
        try:
            items = []
            
            # Check for the Leysco API response wrapper
            if data.get("ResultState") and data.get("ResponseData"):
                response_data = data["ResponseData"]
                if isinstance(response_data, dict):
                    # Extract data array from ResponseData
                    items = response_data.get("data", [])
                elif isinstance(response_data, list):
                    items = response_data
            else:
                # Fallback for other response formats
                if isinstance(data, dict):
                    items = data.get("data", [])
                elif isinstance(data, list):
                    items = data
            
            # Normalize each item to consistent format
            normalized = []
            for item in items:
                if isinstance(item, dict):
                    normalized.append({
                        "ItemCode": item.get("ItemCode", ""),
                        "ItemName": item.get("ItemName", ""),
                        "SellItem": item.get("SellItem", "Y"),
                        "PurchaseItem": item.get("PurchaseItem", "Y"),
                        "ItemGroup": item.get("ItemGroup", ""),
                        "UnitPrice": safe_float(item.get("UnitPrice")),
                        "CurrentOnHand": safe_float(item.get("CurrentOnHand", 0)),
                        "id": item.get("id"),
                    })
            
            logger.debug(f"Parsed {len(normalized)} items from response")
            return normalized
            
        except Exception as e:
            logger.error(f"Error parsing items response: {e}")
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
            
            # Try multiple possible inventory endpoints
            inventory_endpoints = [
                "/api/v1/inventory/report",
                "/inventory/report",
                "/api/v1/InventoryPostings",
            ]
            
            for inv_endpoint in inventory_endpoints:
                try:
                    # Construct URL properly
                    base = self.base_url.rstrip('/')
                    if base.endswith('/api/v1') and inv_endpoint.startswith('/api/v1'):
                        url = f"{base}{inv_endpoint[6:]}"  # Remove duplicate /api/v1
                    else:
                        url = f"{base}{inv_endpoint}"
                    
                    params = {"page": page, "per_page": per_page}
                    if search:
                        params["search"] = search
                    
                    logger.info(f"📊 Fetching inventory from: {url}")
                    self.parent._record_api_call()
                    resp = self.session.get(url, params=params, timeout=15)
                    
                    if not self.auth_handler.check_auth(resp):
                        continue
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        items = self._parse_inventory_response(data)
                        
                        if items:
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
                            
                            logger.info(f"✅ Retrieved {len(all_items)} inventory items from {inv_endpoint}")
                            break
                    
                except Exception as e:
                    logger.debug(f"Failed to fetch inventory from {inv_endpoint}: {e}")
                    continue
            
            return all_items[:limit] if limit else all_items
            
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
        """Get warehouses from the correct API endpoint"""
        try:
            if not self.auth_handler.ensure_auth():
                logger.warning("Not authenticated, cannot fetch warehouses")
                return []
            
            # Try multiple possible warehouse endpoints
            warehouse_endpoints = [
                "/warehouse",
                "/api/v1/warehouse",
                "/warehouses",
                "/api/v1/warehouses",
            ]
            
            for wh_endpoint in warehouse_endpoints:
                try:
                    base = self.base_url.rstrip('/')
                    if base.endswith('/api/v1') and wh_endpoint.startswith('/api/v1'):
                        url = f"{base}{wh_endpoint[6:]}"
                    else:
                        url = f"{base}{wh_endpoint}"
                    
                    params = {"page": 1, "per_page": 100}
                    if search:
                        params["search"] = search
                    
                    logger.info(f"🏭 Fetching warehouses from: {url}")
                    self.parent._record_api_call()
                    resp = self.session.get(url, params=params, timeout=15)
                    
                    if not self.auth_handler.check_auth(resp):
                        continue
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        warehouses = normalize_warehouse_response(data)
                        if warehouses:
                            logger.info(f"✅ Retrieved {len(warehouses)} warehouses from {wh_endpoint}")
                            return apply_limit(warehouses, limit)
                            
                except Exception as e:
                    logger.debug(f"Failed to fetch warehouses from {wh_endpoint}: {e}")
                    continue
            
            logger.warning("No warehouse endpoints returned data")
            return []
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch warehouses: {e}")
            return []