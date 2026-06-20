"""Main DBQueryService class - orchestrates all database queries"""

import re
import logging
import time
import asyncio
from typing import List, Dict, Optional, Any

from app.services.leysco_api import create_api_service, LeyscoAPIService
from app.services.warehouse_service import create_warehouse_service, WarehouseService
from app.services.cache_service import get_cache_service

from .constants import DEFAULT_MAX_ITEMS, DEFAULT_PRICE_CACHE_TTL, SWAHILI_GREETINGS, SWAHILI_ERRORS
from .utils import is_already_transformed, extract_size_from_item_name, normalize_size_for_comparison
from .cache import cache_result, cache_price_lookup
from .fallback import get_fallback_inventory_report, get_fallback_turnover_data, get_fallback_slow_products
from .transformers import (
    ItemTransformer,
    CustomerTransformer,
    WarehouseTransformer,
    DeliveryTransformer,
    AnalyticsTransformer,
    InventoryTransformer,
    PriceTransformer
)
from .dispatcher import Dispatcher

logger = logging.getLogger(__name__)


class DBQueryService:
    """
    Translates (intent, entities) into LeyscoAPIService calls.
    Returns clean Python lists ready for llm.narrate().
    
    MODIFIED FOR PHASE 1: Accepts user_token and company_code parameters.
    """

    def __init__(self, user_token: str = None, company_code: str = None):
        """
        Initialize DBQueryService with user token and company code.
        
        Args:
            user_token: Bearer token from authenticated user
            company_code: Company code for multi-tenant URL resolution
        """
        self.user_token = user_token
        self.company_code = company_code
        
        # Create API service with user token and company code
        if user_token:
            self.api = create_api_service(user_token=user_token, company_code=company_code)
            self.warehouse_service = create_warehouse_service(
                user_token=user_token, 
                company_code=company_code
            )
            logger.info(f"DBQueryService initialized WITH user token and company_code={company_code}")
        else:
            logger.warning("DBQueryService initialized WITHOUT user token - API calls will fail")
            self.api = LeyscoAPIService()
            self.warehouse_service = WarehouseService()
        
        self.cache = get_cache_service()
        self.dispatcher = Dispatcher(self)
        self._skip_cache = False
        
        # Batch operation cache
        self._price_cache = {}
        self._price_cache_time = {}
        self._price_cache_ttl = DEFAULT_PRICE_CACHE_TTL
        
        # Stats tracking
        self._stats = {
            "api_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "avg_response_time": 0
        }
    
    def set_user_token(self, token: str):
        """Update user token for this instance."""
        self.user_token = token
        self.api.set_user_token(token)
        self.warehouse_service.set_user_token(token)
        logger.debug("DBQueryService user token updated")
    
    def set_company_code(self, company_code: str):
        """Update company code for this instance."""
        self.company_code = company_code
        self.api.set_company_code(company_code)
        self.warehouse_service.set_company_code(company_code)
        logger.debug(f"DBQueryService company code updated to: {company_code}")
    
    # -----------------------------------------------------------------------
    # STATS HELPERS
    # -----------------------------------------------------------------------
    
    def get_stats(self) -> Dict[str, Any]:
        """Get query service statistics."""
        return self._stats.copy()
    
    def _record_api_call(self, duration: float) -> None:
        """Record API call metrics."""
        self._stats["api_calls"] += 1
        current_avg = self._stats["avg_response_time"]
        total_calls = self._stats["api_calls"]
        self._stats["avg_response_time"] = ((current_avg * (total_calls - 1)) + duration) / total_calls
    
    def _record_cache_hit(self):
        self._stats["cache_hits"] += 1
    
    def _record_cache_miss(self):
        self._stats["cache_misses"] += 1
    
    def _record_error(self):
        self._stats["errors"] += 1
    
    # -----------------------------------------------------------------------
    # SAFE API CALL WRAPPER
    # -----------------------------------------------------------------------
    
    def _safe_float(self, value, default: float = 0.0) -> float:
        """Safely convert to float."""
        try:
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def _safe_api_call(self, api_method, *args, **kwargs) -> List[Dict]:
        """
        Safely call API methods with error handling.
        Returns empty list on failure instead of raising exceptions.
        """
        method_name = api_method.__name__ if hasattr(api_method, '__name__') else "unknown"
        start_time = time.time()
        
        try:
            result = api_method(*args, **kwargs)
            elapsed = time.time() - start_time
            self._record_api_call(elapsed)
            
            if elapsed > 10:  # Log slow queries
                logger.warning(f"Slow API call: {method_name} took {elapsed:.2f}s")
            
            return result if result is not None else []
            
        except Exception as e:
            self._record_error()
            error_str = str(e)
            if "404" in error_str or "Not Found" in error_str:
                logger.warning(f"{method_name}: Resource not found - {error_str}")
                return []
            elif "timeout" in error_str.lower() or "timed out" in error_str.lower():
                logger.error(f"Timeout in {method_name}: {error_str}")
                
                # Return fallback data for known methods
                if "inventory_report" in method_name:
                    return get_fallback_inventory_report()
                elif "inventory_turnover" in method_name:
                    return get_fallback_turnover_data()
                elif "slow_products" in method_name:
                    return get_fallback_slow_products()
                else:
                    return []
            else:
                logger.warning(f"API call failed in {method_name}: {e}")
                return []
    
    async def _safe_api_call_async(self, api_method, *args, **kwargs) -> List[Dict]:
        """Async safe API call with error handling."""
        return await asyncio.to_thread(self._safe_api_call, api_method, *args, **kwargs)
    
    # -----------------------------------------------------------------------
    # DATA TRANSFORMATION (with truncation)
    # -----------------------------------------------------------------------
    
    def _truncate_for_llm(self, data: list[dict], intent: str, max_items: int = DEFAULT_MAX_ITEMS) -> list[dict]:
        """Truncate data for LLM to prevent token limit issues."""
        if not data or len(data) <= max_items:
            return data
        
        logger.info(f"Truncating {intent} data from {len(data)} to {max_items} items")
        
        if is_already_transformed(data):
            sample = data[:max_items]
            if not any('_summary' in item for item in sample):
                sample.append({"_summary": True, "message": f"Showing {max_items} of {len(data)} items."})
            return sample
        
        # Use appropriate transformer based on intent
        intent_transformers = {
            "GET_WAREHOUSES": lambda d: WarehouseTransformer.transform(d, max_items),
            "GET_ITEMS": lambda d: ItemTransformer.transform(d, max_items),
            "GET_SELLABLE_ITEMS": lambda d: ItemTransformer.transform(d, max_items),
            "GET_INVENTORY_ITEMS": lambda d: ItemTransformer.transform(d, max_items),
            "GET_PURCHASABLE_ITEMS": lambda d: ItemTransformer.transform(d, max_items),
            "GET_ITEM_DETAILS": lambda d: ItemTransformer.transform(d, max_items),
            "GET_STOCK_LEVELS": lambda d: ItemTransformer.transform(d, max_items),
            "GET_CUSTOMERS": lambda d: CustomerTransformer.transform(d, max_items),
            "GET_LOW_STOCK_ALERTS": lambda d: ItemTransformer.transform_low_stock(d, max_items),
            "GET_OUTSTANDING_DELIVERIES": lambda d: DeliveryTransformer.transform(d, max_items),
            "GET_DELIVERY_HISTORY": lambda d: DeliveryTransformer.transform(d, max_items),
            "TRACK_DELIVERY": lambda d: DeliveryTransformer.transform(d, max_items),
            "GET_SALES_ANALYTICS": lambda d: AnalyticsTransformer.transform(d, "last_30_days"),
        }
        
        if intent in intent_transformers:
            return intent_transformers[intent](data)
        
        sample = data[:max_items]
        sample.append({"_summary": True, "message": f"Showing {max_items} of {len(data)} total items."})
        return sample
    
    # -----------------------------------------------------------------------
    # MAIN QUERY ENTRY POINT
    # -----------------------------------------------------------------------
    
    def query(self, intent: str, entities: dict, language: str = "en") -> list[dict] | None:
        """Main query entry point - routes intent to appropriate handler."""
        
        # Check if this intent should be processed here
        if not self.dispatcher.should_process(intent):
            return None
        
        # Extract entities
        item = (entities.get("item_name") or "").strip()
        customer = (entities.get("customer_name") or "").strip()
        warehouse = (entities.get("warehouse") or "").strip()
        limit = int(entities.get("quantity") or 20)
        
        logger.info(f"DB query | {intent} | item='{item}' | customer='{customer}' | warehouse='{warehouse}'")
        
        try:
            data = self.dispatcher.dispatch(intent, item, customer, warehouse, limit, language)
            
            if data and isinstance(data, list):
                # Add language metadata
                for d in data:
                    if isinstance(d, dict) and '_summary' not in d:
                        d['_language'] = language
            
            # Truncate large datasets
            if data and isinstance(data, list) and len(data) > 10:
                if not is_already_transformed(data):
                    data = self._truncate_for_llm(data, intent, max_items=12)
                else:
                    if len(data) > 12:
                        has_summary = any('_summary' in item for item in data[:12])
                        data = data[:12]
                        if not has_summary:
                            data.append({"_summary": True, "message": "Showing 12 items."})
            
            return data
            
        except Exception as e:
            logger.error(f"DBQueryService error for {intent}: {e}")
            return []
    
    async def query_async(self, intent: str, entities: dict, language: str = "en") -> list[dict] | None:
        """Async version of query."""
        return await asyncio.to_thread(self.query, intent, entities, language)
    
    # ========================================================================
    # FIX: ADD get_items METHOD WITH SORTING SUPPORT
    # ========================================================================
    
    def get_items(
        self, 
        limit: int = 20, 
        sort_by: str = None, 
        sort_order: str = "DESC",
        search: str = None,
        **kwargs
    ) -> List[Dict]:
        """
        Get items with optional sorting.
        
        Args:
            limit: Maximum number of items to return
            sort_by: Field to sort by (e.g., "OnHand", "ItemName")
            sort_order: "ASC" or "DESC"
            search: Optional search term to filter items
            **kwargs: Additional filters
            
        Returns:
            List of item dictionaries with full data including OnHand
        """
        logger.info(f"📦 get_items: limit={limit}, sort_by={sort_by}, sort_order={sort_order}, search={search}")
        
        try:
            # Fetch items from API with search if provided
            if search:
                items = self._safe_api_call(self.api.get_items, search=search, limit=limit)
            else:
                items = self._safe_api_call(self.api.get_items, limit=limit)
            
            if not items:
                logger.warning("No items returned from API")
                return []
            
            logger.info(f"✅ Retrieved {len(items)} raw items from API")
            
            # Normalize item data
            normalized_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                
                # Ensure OnHand field exists
                if "OnHand" not in item:
                    # Try alternative field names
                    if "CurrentOnHand" in item:
                        item["OnHand"] = item["CurrentOnHand"]
                    elif "OnHandQty" in item:
                        item["OnHand"] = item["OnHandQty"]
                    elif "Quantity" in item:
                        item["OnHand"] = item["Quantity"]
                    elif "Stock" in item:
                        item["OnHand"] = item["Stock"]
                    else:
                        item["OnHand"] = 0
                
                # Ensure OnHand is a number
                if isinstance(item["OnHand"], str):
                    try:
                        item["OnHand"] = float(item["OnHand"].replace(',', ''))
                    except (ValueError, TypeError):
                        item["OnHand"] = 0
                
                # Ensure item_group exists
                if "item_group" not in item:
                    item["item_group"] = {}
                
                # Ensure full_name exists
                if "full_name" not in item:
                    item["full_name"] = f"{item.get('ItemCode', '')} -- {item.get('ItemName', '')}"
                
                normalized_items.append(item)
            
            # Apply sorting if specified
            if sort_by and normalized_items:
                if sort_by == "OnHand":
                    normalized_items.sort(
                        key=lambda x: float(x.get('OnHand', 0)) if x.get('OnHand') is not None else float('inf'),
                        reverse=(sort_order.upper() == "DESC")
                    )
                elif sort_by == "ItemName":
                    normalized_items.sort(
                        key=lambda x: x.get('ItemName', '').lower(),
                        reverse=(sort_order.upper() == "DESC")
                    )
                elif sort_by == "ItemCode":
                    normalized_items.sort(
                        key=lambda x: x.get('ItemCode', '').lower(),
                        reverse=(sort_order.upper() == "DESC")
                    )
                logger.info(f"✅ Sorted items by {sort_by} ({sort_order})")
            
            # Apply limit
            if limit and len(normalized_items) > limit:
                normalized_items = normalized_items[:limit]
            
            logger.info(f"✅ Returning {len(normalized_items)} items")
            return normalized_items
            
        except Exception as e:
            logger.error(f"Error in get_items: {e}", exc_info=True)
            return []
    
    # ========================================================================
    # FIX: ADD get_low_stock_items METHOD
    # ========================================================================
    
    def get_low_stock_items(self, threshold: int = 100, limit: int = 50) -> List[Dict]:
        """
        Get items with low stock (below threshold).
        
        Args:
            threshold: Stock threshold (items with stock below this are considered low)
            limit: Maximum number of items to return
            
        Returns:
            List of low stock items sorted by stock (lowest first)
        """
        logger.info(f"🔍 get_low_stock_items: threshold={threshold}, limit={limit}")
        
        try:
            # Fetch items with higher limit to filter
            items = self.get_items(limit=limit * 2, sort_by="OnHand", sort_order="ASC")
            
            if not items:
                logger.warning("No items returned from get_items")
                return []
            
            # Filter items with stock below threshold
            low_stock = []
            for item in items:
                on_hand = item.get('OnHand', 0)
                if isinstance(on_hand, (int, float)) and on_hand < threshold:
                    low_stock.append(item)
            
            # If no items below threshold, return the lowest stock items
            if not low_stock and items:
                # Take the lowest stock items (already sorted by OnHand ASC)
                low_stock = items[:min(20, len(items))]
                if low_stock:
                    max_stock = max([item.get('OnHand', 0) for item in low_stock])
                    logger.info(f"⚠️ No items below {threshold}, returning {len(low_stock)} lowest stock items (max: {max_stock})")
            
            logger.info(f"✅ Found {len(low_stock)} low stock items")
            return low_stock
            
        except Exception as e:
            logger.error(f"Error in get_low_stock_items: {e}", exc_info=True)
            return []
    
    # -----------------------------------------------------------------------
    # OPTIMIZED: resolve_and_price with intelligent item prioritization
    # -----------------------------------------------------------------------
    
    @cache_price_lookup(ttl_seconds=3600)
    def resolve_and_price(self, item_name: str, customer_name: str | None = None) -> list[dict]:
        """
        Full SAP-style price lookup — returns items with valid prices.
        OPTIMIZED: Prioritizes exact matches, size matches, and sellable items.
        
        BEHAVIOR:
        - If user specifies a size (e.g., "vegimax 30ml"), returns ONLY the exact match
        - If user specifies an exact item code, returns that specific item
        - If user specifies a generic name (no size/code), returns ALL matching items with prices
        - Continues searching through all prioritized items to find priced ones
        """
        if not item_name:
            logger.warning("resolve_and_price: empty item_name")
            return [{
                "error": True,
                "message": "Please specify an item name. For example: 'bei ya vegimax' or 'vegimax ni pesa ngapi?'",
                "suggestions": ["bei ya vegimax", "vegimax bei gani", "show price of cabbage"]
            }]

        logger.info(f"Price lookup for: '{item_name}'")
        
        # Check if the search term itself looks like an item code (e.g., KAVGX002)
        is_exact_code = bool(re.match(r'^[A-Z0-9]{6,12}$', item_name.upper()))
        if is_exact_code:
            logger.info(f"   Detected exact item code: {item_name}")
        
        # Extract size requirement
        required_size = None
        exact_size_required = False
        
        size_match = re.search(r'(\d+(?:\.\d+)?)\s*(ml|ML|mL|kg|KG|g|G|l|L)', item_name)
        if size_match:
            required_size = normalize_size_for_comparison(f"{size_match.group(1)}{size_match.group(2)}")
            exact_size_required = True
            logger.info(f"   Size required: {required_size} (exact match required)")
        
        # Get items from API
        items = self._safe_api_call(self.api.get_items, search=item_name, limit=50)
        
        if not items:
            logger.info(f"   No items found for '{item_name}'")
            return [{
                "error": True,
                "message": f"No item '{item_name}' found.",
                "suggestions": ["vegimax", "cabbage", "tomato"]
            }]
        
        # Prioritize items
        prioritized_items = PriceTransformer.prioritize_items(
            items, item_name, required_size, exact_size_required
        )
        logger.info(f"   Prioritized to {len(prioritized_items)} most relevant items")
        
        # Resolve customer if provided
        resolved_customer = None
        if customer_name:
            logger.info(f"   Price step 2 — resolve customer: '{customer_name}'")
            customer = self._safe_api_call(self.api.resolve_customer, customer_name)
            if customer:
                resolved_customer = customer.get("CardName", customer_name)
                logger.info(f"   Customer resolved: {resolved_customer}")
            else:
                logger.warning(f"   Customer '{customer_name}' not found — using default pricing")
        
        # Get prices for prioritized items
        results = []
        priced_items_found = 0
        
        for item in prioritized_items:
            item_code = item.get("ItemCode") or item.get("itemCode") or item.get("code")
            item_display = item.get("ItemName") or item.get("itemName") or item_code
            item_size = extract_size_from_item_name(item_display)
            
            if not item_code:
                continue
            
            # Skip non-sellable items
            if item.get("SellItem") != "Y":
                logger.debug(f"   Skipping non-sellable item: {item_display}")
                continue
            
            price_result = self.api.get_item_price(
                item_code=item_code,
                customer_name=resolved_customer,
            )
            
            has_price = price_result and price_result.get("found") and price_result.get("price", 0) > 0
            
            if has_price:
                priced_items_found += 1
                result_item = {
                    "ItemCode": item_code,
                    "ItemName": item_display,
                    "Price": price_result.get("price"),
                    "Currency": price_result.get("currency", "KES"),
                    "PriceListName": price_result.get("price_list_name", ""),
                    "IsGrossPrice": price_result.get("is_gross_price", False),
                    "UomEntry": price_result.get("uom_entry", ""),
                    "Note": price_result.get("note", ""),
                    "Customer": resolved_customer or "Standard pricing",
                }
                
                # For exact size or exact code, break after finding the first priced match
                if exact_size_required or is_exact_code:
                    if exact_size_required and required_size:
                        if item_size == required_size:
                            results.append(result_item)
                            logger.info(f"   Found EXACT SIZE MATCH: {item_display} @ KES {price_result.get('price')}")
                            break
                        else:
                            logger.debug(f"   Found priced item but size mismatch: {item_display} (size={item_size}) vs required={required_size}")
                            results.append(result_item)
                    else:
                        # Exact code match
                        results.append(result_item)
                        logger.info(f"   Found exact item code match: {item_display} @ KES {price_result.get('price')}")
                        break
                else:
                    # Generic search - collect ALL priced items
                    results.append(result_item)
                    logger.info(f"   Found priced item: {item_display} @ KES {price_result.get('price')}")
                    # Continue to find all priced items
            else:
                # No price found - continue searching for other items
                logger.info(f"   Item has no price: {item_display}")
                # If we have an exact code match but no price, we need to return it anyway
                if is_exact_code and item_code.upper() == item_name.upper():
                    results.append({
                        "ItemCode": item_code,
                        "ItemName": item_display,
                        "Price": None,
                        "Note": f"{item_display} exists but has no price configured.",
                        "Customer": resolved_customer or "Standard pricing",
                        "Available": True,
                        "HasPrice": False
                    })
                    logger.info(f"   Found exact code match with no price: {item_display}")
                    break
        
        # Filter exact size matches if needed
        if exact_size_required and required_size and not is_exact_code:
            exact_matches = [
                r for r in results 
                if extract_size_from_item_name(r.get("ItemName", "")) == required_size
            ]
            if exact_matches:
                results = exact_matches
                logger.info(f"   Filtered to {len(results)} exact size matches")
        
        # If no priced items found but we have results (unpriced items), return them
        if priced_items_found == 0 and results:
            logger.info(f"   No priced items found, showing {len(results)} unpriced items")
        
        # If truly no results at all, fallback to first sellable item as unpriced
        if not results and prioritized_items:
            for item in prioritized_items[:3]:
                if item.get("SellItem") == "Y":
                    results.append({
                        "ItemCode": item.get("ItemCode"),
                        "ItemName": item.get("ItemName"),
                        "Price": None,
                        "Note": f"{item.get('ItemName')} exists but has no price configured.",
                        "Customer": resolved_customer or "Standard pricing",
                        "Available": True,
                        "HasPrice": False
                    })
                    break
        
        logger.info(f"   resolve_and_price: {len(results)} result(s) with {priced_items_found} priced items")
        return results
    
    # -----------------------------------------------------------------------
    # HELPER METHODS
    # -----------------------------------------------------------------------
    
    def get_item_by_name(self, name: str, limit: int = 10) -> list[dict]:
        """Get items by name with stock data."""
        raw = self._safe_api_call(self.api.get_items, search=name, limit=limit)
        if raw:
            inventory = self._safe_api_call(self.api.get_inventory_report, search=name, limit=limit)
            inventory_dict = {inv.get("ItemCode"): inv for inv in inventory}
            for r in raw:
                item_code = r.get("ItemCode")
                if item_code and item_code in inventory_dict:
                    inv_data = inventory_dict[item_code]
                    r["CurrentOnHand"] = inv_data.get("CurrentOnHand", 0)
                    r["CurrentIsCommited"] = inv_data.get("CurrentIsCommited", 0)
        return ItemTransformer.transform(raw, max_items=limit)
    
    def get_customer_by_name(self, name: str, limit: int = 5) -> list[dict]:
        """Get customers by name."""
        raw = self._safe_api_call(self.api.get_customers, search=name, limit=limit)
        return CustomerTransformer.transform(raw, max_items=limit)
    
    def health_check(self) -> bool:
        """Check if the service is healthy."""
        try:
            warehouses = self.warehouse_service.search_warehouses()
            return len(warehouses) > 0
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    def clear_cache(self):
        """Clear all caches."""
        self._price_cache.clear()
        self._price_cache_time.clear()
        self.cache.clear()
        if hasattr(self, 'warehouse_service'):
            self.warehouse_service.clear_cache()
        logger.info("DBQueryService cache cleared")
    
    def get_swahili_price_prompt(self, item_name: str) -> str:
        """Get Swahili price prompt."""
        return f"bei ya {item_name}"
    
    def get_swahili_greeting(self) -> str:
        """Get random Swahili greeting."""
        import random
        return random.choice(SWAHILI_GREETINGS)
    
    def get_swahili_error_message(self, error_type: str) -> str:
        """Get Swahili error message."""
        return SWAHILI_ERRORS.get(error_type, "Hitilafu imetokea. Tafadhali jaribu tena.")


# =========================================================
# Factory function to create DBQueryService with user token and company code
# =========================================================

def create_db_query_service(user_token: str = None, company_code: str = None) -> DBQueryService:
    """
    Create a DBQueryService instance with the user's token and company code.
    
    Args:
        user_token: The authenticated user's Bearer token
        company_code: Company code for multi-tenant URL resolution
    
    Returns:
        Configured DBQueryService instance
    """
    if not user_token:
        logger.warning("Creating DB query service without user token - operations may fail")
    
    logger.info(f"✅ create_db_query_service called WITH user token and company_code={company_code}")
    return DBQueryService(user_token=user_token, company_code=company_code)