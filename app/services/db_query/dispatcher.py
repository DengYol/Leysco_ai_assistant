"""Intent dispatch logic - routes intents to appropriate handlers"""

import logging
import re
from typing import List, Dict, Optional

from .constants import ACTION_ROUTER_INTENTS, KNOWLEDGE_BASE_INTENTS
from .transformers import (
    ItemTransformer,
    CustomerTransformer,
    WarehouseTransformer,
    DeliveryTransformer,
    AnalyticsTransformer,
    InventoryTransformer
)
from .fallback import get_fallback_warehouses, get_fallback_deliveries, get_fallback_sales_analytics

logger = logging.getLogger(__name__)


class Dispatcher:
    """Handles intent dispatch to appropriate API calls"""
    
    def __init__(self, parent):
        self.parent = parent
        self.api = parent.api
        self.warehouse_service = parent.warehouse_service
    
    def should_process(self, intent: str) -> bool:
        """Check if this intent should be processed here."""
        # Customer details should be processed by DB query, not action router
        if intent == "GET_CUSTOMER_DETAILS":
            return True
        
        # Warehouse stock should be processed by DB query
        if intent == "GET_WAREHOUSE_STOCK":
            return True
        
        if intent in ACTION_ROUTER_INTENTS:
            logger.info(f"🎯 {intent} handled by action router - skipping DB query")
            return False
        
        if intent in KNOWLEDGE_BASE_INTENTS:
            logger.info(f"📚 {intent} handled by knowledge base")
            return False
        
        return True
    
    # ------------------------------------------------------------------
    # WAREHOUSE RESOLUTION: name/alias → SAP WhsCode
    # ------------------------------------------------------------------

    def _resolve_warehouse_code(self, warehouse: str) -> Optional[str]:
        """
        Dynamically resolve a human-readable warehouse name/alias to its
        SAP WhsCode by querying the warehouse list.

        Strategy (in order):
        1. Exact match on WhsCode  (e.g. "KDISPAT1")
        2. Exact match on WhsName  (e.g. "Dispatch Warehouse")
        3. WhsCode starts-with     (e.g. "kdispat" → "KDISPAT1")
        4. WhsName contains        (e.g. "dispatch" inside "Dispatch Warehouse")
        5. WhsCode contains        (e.g. "dispat" inside "KDISPAT1")

        Returns the resolved WhsCode string, or the original value if no
        match is found (allows the service layer to handle it gracefully).
        """
        if not warehouse:
            return None

        query = warehouse.strip()
        query_upper = query.upper()
        query_lower = query.lower()

        try:
            # Fetch all warehouses (WarehouseService caches this internally)
            warehouses = self.parent._safe_api_call(self.api.get_warehouses)
            if not warehouses:
                logger.warning("_resolve_warehouse_code: no warehouses returned from API")
                return query  # fall through to service layer

            # 1. Exact WhsCode match (already a code — pass through quickly)
            for wh in warehouses:
                if (wh.get("WhsCode") or "").upper() == query_upper:
                    logger.info(f"Warehouse exact code match: '{query}' → '{wh['WhsCode']}'")
                    return wh["WhsCode"]

            # 2. Exact WhsName match
            for wh in warehouses:
                if (wh.get("WhsName") or "").upper() == query_upper:
                    logger.info(f"Warehouse exact name match: '{query}' → '{wh['WhsCode']}'")
                    return wh["WhsCode"]

            # 3. WhsCode starts-with (handles partial codes)
            for wh in warehouses:
                if (wh.get("WhsCode") or "").upper().startswith(query_upper):
                    logger.info(f"Warehouse code starts-with match: '{query}' → '{wh['WhsCode']}'")
                    return wh["WhsCode"]

            # 4. WhsName contains (most common: "dispatch" inside "Dispatch Warehouse")
            for wh in warehouses:
                if query_lower in (wh.get("WhsName") or "").lower():
                    logger.info(f"Warehouse name contains match: '{query}' → '{wh['WhsCode']}'")
                    return wh["WhsCode"]

            # 5. WhsCode contains (e.g. "dispat" inside "KDISPAT1")
            for wh in warehouses:
                if query_upper in (wh.get("WhsCode") or "").upper():
                    logger.info(f"Warehouse code contains match: '{query}' → '{wh['WhsCode']}'")
                    return wh["WhsCode"]

            # No match found — log and return original so the service layer
            # can decide what to do (return empty rather than crash)
            logger.warning(
                f"_resolve_warehouse_code: no match found for '{query}' "
                f"among {[wh.get('WhsCode') for wh in warehouses]}"
            )
            return query

        except Exception as e:
            logger.error(f"_resolve_warehouse_code error: {e}")
            return query  # safe fallback

    # ------------------------------------------------------------------
    # ASYNC / SYNC DISPATCH
    # ------------------------------------------------------------------

    async def dispatch_async(self, intent: str, item: str, customer: str,
                              warehouse: str, limit: int, language: str) -> Optional[List[Dict]]:
        """Async dispatch to appropriate handler"""
        import asyncio
        return await asyncio.to_thread(self.dispatch, intent, item, customer, warehouse, limit, language)
    
    def dispatch(self, intent: str, item: str, customer: str,
                 warehouse: str, limit: int, language: str) -> Optional[List[Dict]]:
        """Dispatch intent to the right API method"""
        
        # Customer Details (specific customer) - HIGH PRIORITY
        if intent == "GET_CUSTOMER_DETAILS":
            return self._handle_customer_details(customer, limit)
        
        # Warehouse Stock - NEW
        if intent == "GET_WAREHOUSE_STOCK":
            return self._handle_warehouse_stock(warehouse, item, limit)
        
        # Sales Analytics
        if intent == "GET_SALES_ANALYTICS":
            return self._handle_sales_analytics(item, customer, limit)
        
        # Price queries
        if intent in ["GET_ITEM_PRICE", "GET_ITEM_BASE_PRICE", "GET_CUSTOMER_PRICE"]:
            return self.parent.resolve_and_price(
                item_name=item,
                customer_name=customer if intent == "GET_CUSTOMER_PRICE" else None
            )
        
        # Items
        if intent in ["GET_ITEMS", "GET_SELLABLE_ITEMS", "GET_INVENTORY_ITEMS"]:
            return self._handle_items(item, limit)
        
        # Customers (listing)
        if intent == "GET_CUSTOMERS":
            return self._handle_customers(customer, limit)
        
        # Stock levels
        if intent == "GET_STOCK_LEVELS":
            return self._handle_stock_levels(item, limit)
        
        # Warehouses
        if intent == "GET_WAREHOUSES":
            return self._handle_warehouses(warehouse, limit)
        
        # Low stock alerts
        if intent == "GET_LOW_STOCK_ALERTS":
            return self._handle_low_stock_alerts(warehouse, item, limit)
        
        # Outstanding deliveries
        if intent == "GET_OUTSTANDING_DELIVERIES":
            return self._handle_outstanding_deliveries(customer, limit)
        
        logger.warning(f"No optimized dispatch for intent: {intent}")
        return []
    
    # ------------------------------------------------------------------
    # INTENT HANDLERS
    # ------------------------------------------------------------------

    def _handle_warehouse_stock(self, warehouse: str, item: str, limit: int) -> List[Dict]:
        """Handle warehouse stock intent - get stock for a specific warehouse"""
        logger.info(f"Getting stock for warehouse: {warehouse or 'all'}, item: {item or 'all'}")
        
        # Clean warehouse name - remove common prefixes like "stock of"
        clean_warehouse = warehouse
        if clean_warehouse:
            prefixes_to_remove = [
                r'^stock\s+of\s+',
                r'^inventory\s+at\s+',
                r'^items\s+in\s+',
                r'^available\s+in\s+',
                r'^stock\s+in\s+',
            ]
            for prefix in prefixes_to_remove:
                clean_warehouse = re.sub(prefix, '', clean_warehouse, flags=re.IGNORECASE)
            clean_warehouse = clean_warehouse.strip()
        
        # Resolve warehouse name to code
        resolved_whscode = self._resolve_warehouse_code(clean_warehouse) if clean_warehouse else None
        
        if clean_warehouse and not resolved_whscode:
            # Try searching by the original warehouse parameter
            resolved_whscode = self._resolve_warehouse_code(warehouse) if warehouse else None
        
        if clean_warehouse and not resolved_whscode:
            logger.warning(f"Could not resolve warehouse: '{clean_warehouse}' (original: '{warehouse}')")
        else:
            logger.info(f"Resolved warehouse: '{clean_warehouse}' → '{resolved_whscode}'")
        
        # Fetch inventory
        try:
            # If specific item requested, search by item
            search_term = item if item else ""
            inventory = self.parent._safe_api_call(
                self.api.get_inventory_report, 
                search=search_term, 
                limit=min(limit, 100) if limit > 0 else 100
            )
            
            if not inventory:
                logger.info(f"No inventory found for warehouse: {resolved_whscode or 'all'}")
                return []
            
            # Filter by warehouse if specific warehouse was requested
            if resolved_whscode:
                filtered = [
                    inv for inv in inventory 
                    if inv.get("WhsCode", "").upper() == resolved_whscode.upper()
                ]
                logger.info(f"Filtered {len(filtered)}/{len(inventory)} items for warehouse {resolved_whscode}")
            else:
                filtered = inventory
            
            # Transform to clean format
            if filtered:
                return ItemTransformer.transform(filtered, max_items=min(limit, 50) if limit > 0 else 50)
            else:
                logger.info(f"No items found in warehouse: {resolved_whscode or 'all'}")
                return []
            
        except Exception as e:
            logger.error(f"Error getting warehouse stock: {e}")
            return []

    def _handle_customer_details(self, customer: str, limit: int) -> List[Dict]:
        """Handle customer details intent - fetch specific customer by name"""
        logger.info(f"Getting customer details for: {customer}")
        
        if not customer:
            logger.warning("No customer name provided for GET_CUSTOMER_DETAILS")
            return []
        
        # Clean customer name - remove common prefixes
        clean_customer = customer.strip()
        prefixes_to_remove = [
            r'^customer\s+details?\s+(?:for|of|about)\s+',
            r'^details?\s+of\s+customer\s+',
            r'^show\s+me\s+customer\s+details?\s+(?:for|of)\s+',
            r'^get\s+customer\s+details?\s+(?:for|of)\s+',
            r'^check\s+customer\s+details?\s+(?:for|of)\s+',
        ]
        for prefix in prefixes_to_remove:
            clean_customer = re.sub(prefix, '', clean_customer, flags=re.IGNORECASE)
        clean_customer = clean_customer.strip()
        
        logger.info(f"Cleaned customer name: '{clean_customer}'")
        
        # Try to find customer by name or code
        customer_data = None
        
        # First, try direct customer code match
        if re.match(r'^[A-Z]{2,3}\d{4,8}$', clean_customer.upper()):
            logger.info(f"Looking up customer by code: {clean_customer.upper()}")
            customers = self.parent._safe_api_call(self.api.get_customers, search=clean_customer, limit=5)
            if customers:
                # Find exact code match
                for cust in customers:
                    if cust.get("CardCode", "").upper() == clean_customer.upper():
                        customer_data = cust
                        break
                if not customer_data and customers:
                    customer_data = customers[0]
        
        # If not found by code, search by name
        if not customer_data:
            logger.info(f"Searching for customer by name: {clean_customer}")
            customers = self.parent._safe_api_call(self.api.get_customers, search=clean_customer, limit=10)
            
            if customers:
                # Try exact match first (case-insensitive)
                exact_match = None
                for cust in customers:
                    cust_name = cust.get("CardName", "")
                    # Remove common suffixes for better matching
                    name_for_compare = re.sub(r'\s+(?:Ltd|Limited|Inc|Corp|LLC|Co|Supplies|Supply|Agrovet|Agri|Traders|Enterprises)$', '', cust_name, flags=re.IGNORECASE).strip()
                    search_for_compare = re.sub(r'\s+(?:Ltd|Limited|Inc|Corp|LLC|Co|Supplies|Supply|Agrovet|Agri|Traders|Enterprises)$', '', clean_customer, flags=re.IGNORECASE).strip()
                    
                    if name_for_compare.lower() == search_for_compare.lower():
                        exact_match = cust
                        break
                
                if exact_match:
                    customer_data = exact_match
                    logger.info(f"Exact customer name match found: {customer_data.get('CardName')}")
                else:
                    # Use the first (closest) match
                    customer_data = customers[0]
                    logger.info(f"Using closest match: {customer_data.get('CardName')} (searched for: {clean_customer})")
        
        if customer_data:
            logger.info(f"Found customer: {customer_data.get('CardName')} ({customer_data.get('CardCode')})")
            # Add additional customer details for better response
            result = CustomerTransformer.transform([customer_data], max_items=1)
            
            # Enhance with additional fields if available
            if result:
                result[0]["card_code"] = customer_data.get("CardCode")
                result[0]["balance"] = customer_data.get("CurrentAccountBalance") or customer_data.get("Balance")
                result[0]["credit_limit"] = customer_data.get("CreditLimit")
                result[0]["phone"] = customer_data.get("Phone1") or customer_data.get("Phone2")
                result[0]["email"] = customer_data.get("EmailAddress")
                result[0]["city"] = customer_data.get("City")
                result[0]["country"] = customer_data.get("Country")
            
            return result
        
        logger.warning(f"No customer found matching: '{customer}'")
        return []
    
    def _handle_sales_analytics(self, item: str, customer: str, limit: int) -> List[Dict]:
        """Handle sales analytics intent"""
        logger.info(f"Getting sales analytics for period: {item or 'last_30_days'}")
        
        # Determine period
        period = "last_30_days"
        if item:
            item_lower = item.lower()
            if "week" in item_lower or "7 days" in item_lower:
                period = "last_7_days"
            elif "month" in item_lower or "30 days" in item_lower:
                period = "last_30_days"
            elif "quarter" in item_lower or "90 days" in item_lower:
                period = "last_90_days"
            elif "year" in item_lower or "365 days" in item_lower:
                period = "last_365_days"
        
        # Resolve customer code
        customer_code = None
        if customer:
            customers = self.parent._safe_api_call(self.api.get_customers, search=customer, limit=1)
            if customers:
                customer_code = customers[0].get("CardCode")
                logger.info(f"Filtering sales by customer: {customer} ({customer_code})")
        
        # Extract item filter
        item_filter = None
        if item and not any(x in item.lower() for x in ["week", "month", "quarter", "year", "day", "days"]):
            item_filter = item
            logger.info(f"Filtering sales by item: {item_filter}")
        
        try:
            raw_data = self.parent._safe_api_call(
                self.api.get_sales_analytics,
                period=period,
                limit=limit,
                customer_code=customer_code,
                item_code=item_filter
            )
            
            if raw_data:
                logger.info(f"Found sales analytics data from API")
                return AnalyticsTransformer.transform(raw_data, period)
            else:
                logger.info("No sales data found from API, using fallback")
                return get_fallback_sales_analytics()
                
        except Exception as e:
            logger.error(f"Error getting sales analytics: {e}")
            return get_fallback_sales_analytics()
    
    def _handle_items(self, item: str, limit: int) -> List[Dict]:
        """Handle items intent with stock data enrichment"""
        logger.info(f"Fetching items matching: '{item}'")
        
        raw = self.parent._safe_api_call(self.api.get_items, search=item, limit=min(limit, 50))
        
        if raw:
            # Enhance with stock data
            inventory = self.parent._safe_api_call(self.api.get_inventory_report, search=item, limit=min(limit, 50))
            inventory_dict = {inv.get("ItemCode"): inv for inv in inventory}
            logger.info(f"Loaded {len(raw)} items, {len(inventory_dict)} inventory records")
            
            for r in raw:
                item_code = r.get("ItemCode")
                if item_code and item_code in inventory_dict:
                    inv_data = inventory_dict[item_code]
                    r["CurrentOnHand"] = inv_data.get("CurrentOnHand", 0)
                    r["CurrentIsCommited"] = inv_data.get("CurrentIsCommited", 0)
                    r["LastTransactionDate"] = inv_data.get("LastTransactionDate", "")
                    r["WhsCode"] = inv_data.get("WhsCode", "")
            
            return ItemTransformer.transform(raw, max_items=15)
        
        logger.warning(f"No items found matching '{item}'")
        return []
    
    def _handle_customers(self, customer: str, limit: int) -> List[Dict]:
        """Handle customers intent - list customers"""
        raw = self.parent._safe_api_call(self.api.get_customers, search=customer, limit=min(limit, 30))
        return CustomerTransformer.transform(raw, max_items=15)
    
    def _handle_stock_levels(self, item: str, limit: int) -> List[Dict]:
        """Handle stock levels intent"""
        logger.info(f"Getting stock levels for: {item or 'all items'}")
        raw = self.parent._safe_api_call(self.api.get_inventory_report, search=item, limit=min(limit, 50))
        
        if raw:
            logger.info(f"Found {len(raw)} stock records")
            return ItemTransformer.transform(raw, max_items=15)
        
        logger.warning(f"No stock data found for: {item}")
        return []
    
    def _handle_warehouses(self, warehouse: str, limit: int) -> List[Dict]:
        """Handle warehouses intent"""
        logger.info(f"Fetching warehouses...")
        
        try:
            warehouses_summary = self.warehouse_service.get_all_warehouses_summary()
            
            if warehouses_summary and len(warehouses_summary) > 0:
                logger.info(f"Found {len(warehouses_summary)} warehouses from WarehouseService")
                return WarehouseTransformer.transform_from_summary(warehouses_summary, max_items=12)
            else:
                warehouses = self.warehouse_service.search_warehouses(query=warehouse if warehouse else "")
                if warehouses:
                    logger.info(f"Found {len(warehouses)} warehouses from search")
                    return WarehouseTransformer.transform(warehouses, max_items=12)
                else:
                    logger.warning("No warehouse data from API, using fallback")
                    return WarehouseTransformer.transform(get_fallback_warehouses(), max_items=12)
                    
        except Exception as e:
            logger.error(f"Error fetching warehouses: {e}")
            raw = self.parent._safe_api_call(self.api.get_warehouses, search=warehouse)
            if raw:
                return WarehouseTransformer.transform(raw, max_items=12)
            else:
                return WarehouseTransformer.transform(get_fallback_warehouses(), max_items=12)
    
    def _handle_low_stock_alerts(self, warehouse: str, item: str, limit: int) -> List[Dict]:
        """
        Handle low stock alerts intent.

        When a warehouse filter is provided by the user (e.g. "dispatch"),
        we first resolve it to a SAP WhsCode (e.g. "KDISPAT1") dynamically
        before querying WarehouseService — avoiding hardcoded alias maps.
        """
        # Resolve human name → SAP WhsCode
        resolved_whscode = self._resolve_warehouse_code(warehouse) if warehouse else None

        logger.info(
            f"Getting low stock alerts for warehouse: {resolved_whscode or 'all'}"
            + (f" (resolved from: '{warehouse}')" if warehouse and resolved_whscode != warehouse else "")
        )
        
        try:
            if resolved_whscode:
                alerts = self.warehouse_service.get_low_stock_alerts(
                    whscode=resolved_whscode, threshold_pct=0.1, min_available=100
                )
            else:
                alerts = self.warehouse_service.get_low_stock_alerts(threshold_pct=0.1, min_available=100)
            
            if alerts:
                logger.info(f"Found {len(alerts)} low stock alerts from WarehouseService")
                formatted_alerts = []
                for alert in alerts:
                    formatted_alerts.append({
                        "ItemCode": alert.get("ItemCode"),
                        "ItemName": alert.get("ItemName"),
                        "CurrentOnHand": alert.get("OnHand", 0),
                        "CurrentIsCommited": alert.get("Committed", 0),
                        "Available": alert.get("Available", 0),
                        "AlertLevel": alert.get("Severity", "LOW"),
                        "WhsCode": alert.get("WhsCode"),
                    })
                return ItemTransformer.transform_low_stock(formatted_alerts, max_items=20)
            else:
                logger.info("No low stock alerts found")
                return []
                
        except Exception as e:
            logger.error(f"Error getting low stock alerts: {e}")
            # Fallback: query inventory directly and compute alerts in-place
            raw = self.parent._safe_api_call(self.api.get_inventory_report, search=item, limit=200)
            
            if not raw:
                return []
            
            # Apply warehouse filter on raw data if we have a resolved code
            if resolved_whscode:
                raw = [
                    itm for itm in raw
                    if (itm.get("WhsCode") or "").upper() == resolved_whscode.upper()
                ]

            low_stock_items = []
            for inv_item in raw:
                on_hand = self.parent._safe_float(inv_item.get("CurrentOnHand", 0))
                committed = self.parent._safe_float(inv_item.get("CurrentIsCommited", 0))
                available = on_hand - committed
                
                if available <= 0 or available < 10:
                    alert_level = "CRITICAL"
                elif available < 50:
                    alert_level = "LOW"
                elif available < 100:
                    alert_level = "MEDIUM"
                else:
                    continue
                
                low_stock_items.append({
                    "ItemCode": inv_item.get("ItemCode"),
                    "ItemName": inv_item.get("ItemName"),
                    "CurrentOnHand": on_hand,
                    "CurrentIsCommited": committed,
                    "Available": available,
                    "AlertLevel": alert_level,
                    "WhsCode": inv_item.get("WhsCode"),
                })
            
            logger.info(f"Found {len(low_stock_items)} items with low stock alerts (fallback path)")
            return ItemTransformer.transform_low_stock(low_stock_items, max_items=20)
    
    def _handle_outstanding_deliveries(self, customer: str, limit: int) -> List[Dict]:
        """Handle outstanding deliveries intent"""
        logger.info(f"Getting outstanding deliveries for customer: {customer or 'all'}")
        
        # Clean customer name
        clean_customer = customer
        if clean_customer:
            prefixes_to_remove = [
                r'^outstanding\s+deliveries?\s+for\s+',
                r'^deliveries?\s+for\s+',
                r'^show\s+me\s+deliveries?\s+for\s+',
            ]
            for prefix in prefixes_to_remove:
                clean_customer = re.sub(prefix, '', clean_customer, flags=re.IGNORECASE)
            clean_customer = clean_customer.strip()
        
        # Resolve customer code
        customer_code = None
        if clean_customer:
            customers = self.parent._safe_api_call(self.api.get_customers, search=clean_customer, limit=5)
            if customers:
                customer_code = customers[0].get("CardCode")
                logger.info(f"Resolved customer '{clean_customer}' to code: {customer_code}")
            else:
                logger.warning(f"Customer '{clean_customer}' not found")
        
        try:
            raw = self.parent._safe_api_call(
                self.api.get_outstanding_deliveries,
                customer_code=customer_code,
                limit=limit
            )
            
            if raw:
                logger.info(f"Found {len(raw)} outstanding deliveries")
                return DeliveryTransformer.transform(raw, max_items=15)
            else:
                logger.info("No outstanding deliveries found")
                return get_fallback_deliveries()
                
        except Exception as e:
            logger.error(f"Error getting outstanding deliveries: {e}")
            return get_fallback_deliveries()