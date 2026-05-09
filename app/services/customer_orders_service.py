"""
app/services/customer_orders_service.py
========================================
Customer Orders Service - Handles customer order operations
Optimized with caching and async support

FIXED: Properly uses API's get_customer_orders method
FIXED: Enhanced customer resolution with logging
FIXED: Better error handling and empty result returns
"""

import logging
import asyncio
import hashlib
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from functools import lru_cache, wraps

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# Cache TTLs
ORDERS_CACHE_TTL = 300        # 5 minutes for orders
ORDER_DETAILS_CACHE_TTL = 600  # 10 minutes for order details
RECENT_ORDERS_CACHE_TTL = 300  # 5 minutes for recent orders


def cache_orders(ttl_seconds: int = ORDERS_CACHE_TTL, key_prefix: str = ""):
    """
    Decorator to cache order results.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            cache = get_cache_service()
            
            # Generate cache key
            cache_str = f"{key_prefix or func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            cache_key = hashlib.md5(cache_str.encode()).hexdigest()
            
            # Check cache
            cached = cache.get(cache_key, {}, "")
            if cached is not None:
                logger.debug(f"📦 Orders cache hit: {func.__name__}")
                return cached.get("data")
            
            # Execute function
            result = func(self, *args, **kwargs)
            
            # Cache result
            if result:
                cache.set(cache_key, {}, "", {"data": result})
            
            return result
        return wrapper
    return decorator


class CustomerOrdersService:
    """
    Service for managing customer orders.
    Provides methods to fetch, analyze, and manage customer orders.
    Optimized with caching and async support.
    """

    def __init__(self, api, pricing):
        self.api = api
        self.pricing = pricing
        
        # Stats tracking
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "errors": 0
        }

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

    # =========================================================
    # CORE ORDER METHODS (FIXED)
    # =========================================================

    @cache_orders(ttl_seconds=ORDERS_CACHE_TTL)
    def get_customer_orders(
        self,
        customer_name: str,
        limit: int = 10,
        doc_status: str = "all",
        include_details: bool = False
    ) -> List[Dict]:
        """
        Get orders for a specific customer.
        Optimized with caching.
        
        Args:
            customer_name: Name of the customer
            limit: Maximum number of orders to return
            doc_status: Order status ('open', 'closed', 'all')
            include_details: Whether to include line items (default False for performance)
        
        Returns:
            List of orders with details
        """
        try:
            self._record_api_call()
            logger.info(f"📋 Fetching orders for customer: {customer_name}")
            
            if not customer_name:
                logger.warning("No customer name provided")
                return []
            
            # First resolve customer to get CardCode
            customer = self.api.resolve_customer(customer_name)
            if not customer:
                logger.warning(f"⚠️ Customer '{customer_name}' not found - checking partial match")
                # Try partial match search
                customers = self.api.get_customers(search=customer_name, limit=5)
                if customers:
                    customer = customers[0]
                    logger.info(f"✅ Found customer via partial match: {customer.get('CardName')}")
                else:
                    logger.warning(f"⚠️ No customer found for '{customer_name}'")
                    return []
            
            customer_code = customer.get("CardCode")
            customer_name_display = customer.get("CardName", customer_name)
            logger.info(f"✅ Resolved customer: {customer_name_display} (Code: {customer_code})")
            
            # Get orders from API
            orders = self.api.get_customer_orders(
                customer_code=customer_code,
                limit=limit,
                doc_status=doc_status,
                from_date=None,
                to_date=None
            )
            
            if not orders:
                logger.info(f"No orders found for {customer_name_display}")
                
                # Return helpful message as empty list with note
                return []  # The UI will handle empty result
            
            # Enhance orders with additional info (without line items for performance)
            enhanced_orders = []
            for order in orders:
                enhanced_order = self._enhance_order(order, customer)
                
                # Remove line items if not requested (for performance)
                if not include_details and "Items" in enhanced_order:
                    del enhanced_order["Items"]
                elif "Items" in enhanced_order:
                    # Limit line items to first 5 for performance
                    enhanced_order["Items"] = enhanced_order["Items"][:5]
                    enhanced_order["ItemsCount"] = len(order.get("Items", []))
                
                enhanced_orders.append(enhanced_order)
            
            logger.info(f"✅ Found {len(enhanced_orders)} orders for {customer_name_display}")
            return enhanced_orders
            
        except Exception as e:
            self._record_error()
            logger.error(f"❌ Error fetching customer orders: {e}", exc_info=True)
            return []

    async def get_customer_orders_async(
        self,
        customer_name: str,
        limit: int = 10,
        doc_status: str = "all",
        include_details: bool = False
    ) -> List[Dict]:
        """Async version of get_customer_orders."""
        return await asyncio.to_thread(
            self.get_customer_orders, customer_name, limit, doc_status, include_details
        )

    @cache_orders(ttl_seconds=ORDER_DETAILS_CACHE_TTL)
    def get_order_details(self, order_number: str) -> Optional[Dict]:
        """
        Get detailed information for a specific order.
        Optimized with caching (10 minute TTL).
        
        Args:
            order_number: The order document number
        
        Returns:
            Order details or None if not found
        """
        try:
            self._record_api_call()
            logger.info(f"🔍 Fetching order #{order_number}")
            
            # First try to find in customer orders
            order = None
            
            # Look for order in recent orders
            recent_orders = self.get_recent_orders(days=90, limit=200)
            for o in recent_orders:
                if str(o.get("DocNum")) == str(order_number):
                    order = o
                    break
            
            if order:
                logger.info(f"✅ Found order #{order_number} in recent orders")
                return self._enhance_order(order, {})
            
            # Try to get by document number via API
            try:
                # Search for document by number
                documents = self.api.search_documents(
                    doc_type=17,  # Sales Orders
                    doc_num=order_number,
                    per_page=1
                )
                if documents:
                    order = documents[0]
                    logger.info(f"✅ Found order #{order_number} via API search")
                    return self._enhance_order(order, {})
            except Exception as e:
                logger.debug(f"Could not search documents by number: {e}")
            
            logger.warning(f"⚠️ Order #{order_number} not found")
            return None
            
        except Exception as e:
            self._record_error()
            logger.error(f"❌ Error fetching order details: {e}")
            return None

    async def get_order_details_async(self, order_number: str) -> Optional[Dict]:
        """Async version of get_order_details."""
        return await asyncio.to_thread(self.get_order_details, order_number)

    @cache_orders(ttl_seconds=RECENT_ORDERS_CACHE_TTL)
    def get_recent_orders(self, days: int = 30, limit: int = 20) -> List[Dict]:
        """
        Get recent orders across all customers.
        Optimized with caching (5 minute TTL).
        
        Args:
            days: Number of days to look back
            limit: Maximum number of orders to return
        
        Returns:
            List of recent orders
        """
        try:
            self._record_api_call()
            logger.info(f"📋 Fetching recent orders from last {days} days")
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Use get_customer_orders with all customers approach
            # Get customers first to fetch their recent orders
            customers = self.api.get_customers(limit=50)
            
            all_orders = []
            for customer in customers[:30]:  # Limit to 30 customers for performance
                try:
                    customer_code = customer.get("CardCode")
                    orders = self.api.get_customer_orders(
                        customer_code=customer_code,
                        limit=10,
                        doc_status="all"
                    )
                    
                    for order in orders:
                        doc_date_str = order.get("DocDate")
                        if doc_date_str:
                            try:
                                doc_date = datetime.strptime(doc_date_str[:10], "%Y-%m-%d")
                                if doc_date >= start_date:
                                    all_orders.append(order)
                            except:
                                pass
                except Exception as e:
                    logger.debug(f"Error fetching orders for customer {customer.get('CardName')}: {e}")
                    continue
            
            # Sort by date (newest first) and limit
            all_orders.sort(key=lambda x: x.get("DocDate", ""), reverse=True)
            recent_orders = all_orders[:limit]
            
            # Enhance each order
            enhanced_orders = []
            for order in recent_orders:
                enhanced_orders.append(self._enhance_order(order, {}))
            
            logger.info(f"✅ Found {len(enhanced_orders)} recent orders")
            return enhanced_orders
            
        except Exception as e:
            self._record_error()
            logger.error(f"❌ Error fetching recent orders: {e}")
            return []

    async def get_recent_orders_async(self, days: int = 30, limit: int = 20) -> List[Dict]:
        """Async version of get_recent_orders."""
        return await asyncio.to_thread(self.get_recent_orders, days, limit)

    # =========================================================
    # ORDER ANALYTICS (Optimized)
    # =========================================================

    @cache_orders(ttl_seconds=ORDERS_CACHE_TTL)
    def get_order_summary(self, customer_name: str) -> Dict[str, Any]:
        """
        Get order summary statistics for a customer.
        Optimized with caching.
        
        Args:
            customer_name: Name of the customer
        
        Returns:
            Dictionary with order statistics
        """
        try:
            self._record_api_call()
            orders = self.get_customer_orders(customer_name, limit=100, doc_status="all", include_details=False)
            
            if not orders:
                return {
                    "customer": customer_name,
                    "found": False,
                    "total_orders": 0,
                    "total_value": 0,
                    "average_order_value": 0,
                    "open_orders": 0,
                    "closed_orders": 0,
                    "recent_orders": []
                }
            
            total_value = sum(float(o.get("DocTotal", 0)) for o in orders)
            open_orders = sum(1 for o in orders if o.get("StatusText") == "Open")
            closed_orders = sum(1 for o in orders if o.get("StatusText") == "Closed")
            
            # Get recent orders (last 5)
            recent = sorted(orders, key=lambda x: x.get("DocDate", ""), reverse=True)[:5]
            
            return {
                "customer": customer_name,
                "found": True,
                "total_orders": len(orders),
                "total_value": round(total_value, 2),
                "average_order_value": round(total_value / len(orders) if orders else 0, 2),
                "open_orders": open_orders,
                "closed_orders": closed_orders,
                "recent_orders": [
                    {
                        "order_number": o.get("DocNum"),
                        "date": o.get("DocDate"),
                        "total": o.get("DocTotal"),
                        "status": o.get("StatusText")
                    }
                    for o in recent
                ]
            }
            
        except Exception as e:
            self._record_error()
            logger.error(f"❌ Error calculating order summary: {e}")
            return {"error": str(e), "customer": customer_name, "found": False}

    async def get_order_summary_async(self, customer_name: str) -> Dict[str, Any]:
        """Async version of get_order_summary."""
        return await asyncio.to_thread(self.get_order_summary, customer_name)

    @cache_orders(ttl_seconds=ORDER_DETAILS_CACHE_TTL)
    def get_order_items(self, order_number: str) -> List[Dict]:
        """
        Get line items for a specific order.
        Optimized with caching.
        
        Args:
            order_number: The order document number
        
        Returns:
            List of items in the order
        """
        try:
            self._record_api_call()
            order = self.get_order_details(order_number)
            if order:
                items = order.get("Items", [])
                
                # Enhance items with formatted values
                for item in items:
                    item["LineTotalFormatted"] = f"KES {float(item.get('LineTotal', 0)):,.2f}"
                    item["PriceFormatted"] = f"KES {float(item.get('Price', 0)):,.2f}"
                
                return items
            
            return []
            
        except Exception as e:
            self._record_error()
            logger.error(f"❌ Error fetching order items: {e}")
            return []

    async def get_order_items_async(self, order_number: str) -> List[Dict]:
        """Async version of get_order_items."""
        return await asyncio.to_thread(self.get_order_items, order_number)

    # =========================================================
    # BATCH OPERATIONS
    # =========================================================

    def get_multiple_order_details(self, order_numbers: List[str]) -> Dict[str, Dict]:
        """
        Get details for multiple orders in batch.
        
        Args:
            order_numbers: List of order document numbers
        
        Returns:
            Dict mapping order_number to order details
        """
        if not order_numbers:
            return {}
        
        results = {}
        
        # Try to get from cache first
        cache = get_cache_service()
        uncached = []
        
        for order_num in order_numbers:
            cache_key = f"order_details:{order_num}"
            cached = cache.get(cache_key, {}, "")
            if cached is not None:
                self._record_cache_hit()
                results[order_num] = cached.get("data")
            else:
                self._record_cache_miss()
                uncached.append(order_num)
        
        # Fetch uncached orders
        if uncached:
            for order_num in uncached:
                try:
                    details = self.get_order_details(order_num)
                    if details:
                        results[order_num] = details
                except Exception as e:
                    logger.error(f"Error fetching order {order_num}: {e}")
        
        return results

    def _batch_get_prices(self, item_codes: List[str]) -> Dict[str, Dict]:
        """Batch fetch prices for multiple items."""
        price_map = {}
        
        for item_code in item_codes:
            try:
                price_result = self.pricing.get_price(item_code)
                if price_result and price_result.get("found"):
                    price_map[item_code] = {
                        "price": price_result.get("price"),
                        "price_list": price_result.get("price_list_name"),
                        "found": True
                    }
                else:
                    price_map[item_code] = {"price": None, "found": False}
            except Exception as e:
                logger.debug(f"Could not get price for {item_code}: {e}")
                price_map[item_code] = {"price": None, "found": False}
        
        return price_map

    # =========================================================
    # HELPER METHODS (Optimized)
    # =========================================================
    
    def _enhance_order(self, order: Dict, customer: Dict) -> Dict:
        """Enhance order with additional calculated fields."""
        enhanced = {
            "DocNum": order.get("DocNum"),
            "DocEntry": order.get("DocEntry"),
            "DocDate": order.get("DocDate"),
            "DocDueDate": order.get("DocDueDate"),
            "DocTotal": float(order.get("DocTotal", 0)),
            "CardCode": order.get("CardCode"),
            "CardName": order.get("CardName", "Unknown"),
        }
        
        # Add customer info from provided customer
        if customer:
            enhanced["CustomerName"] = customer.get("CardName", enhanced["CardName"])
            enhanced["CustomerCode"] = customer.get("CardCode", enhanced["CardCode"])
        
        # Add status text
        doc_status = order.get("DocStatus") or order.get("Status")
        if doc_status in [1, "1", "bost_Open", "Open", "open", "O", "O"]:
            enhanced["StatusText"] = "Open"
        elif doc_status in [2, "2", "bost_Close", "Closed", "closed", "C", "c"]:
            enhanced["StatusText"] = "Closed"
        elif doc_status in [3, "3", "Cancelled", "cancelled"]:
            enhanced["StatusText"] = "Cancelled"
        else:
            # Check for status from API
            api_status = order.get("Status")
            if api_status:
                enhanced["StatusText"] = api_status
            else:
                enhanced["StatusText"] = str(doc_status) if doc_status else "Unknown"
        
        # Add formatted dates
        doc_date = enhanced["DocDate"]
        if doc_date:
            try:
                if isinstance(doc_date, str):
                    dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
                    enhanced["DocDateFormatted"] = dt.strftime("%b %d, %Y")
                else:
                    enhanced["DocDateFormatted"] = str(doc_date)[:10]
            except (ValueError, TypeError):
                enhanced["DocDateFormatted"] = str(doc_date)
        
        # Add items if present
        items = order.get("Items") or order.get("DocumentLines") or []
        if items:
            enhanced["Items"] = []
            enhanced["ItemCount"] = len(items)
            for item in items:
                enhanced["Items"].append({
                    "ItemCode": item.get("ItemCode"),
                    "ItemName": item.get("ItemName") or item.get("ItemDescription", "Unknown"),
                    "Quantity": float(item.get("Quantity", 0)),
                    "OpenQty": float(item.get("OpenQty", 0)),
                    "Price": float(item.get("Price", 0)),
                    "LineTotal": float(item.get("LineTotal", 0)),
                })
        
        return enhanced
    
    # =========================================================
    # CACHE MANAGEMENT
    # =========================================================
    
    def clear_cache(self):
        """Clear all caches."""
        # Clear Redis cache
        cache = get_cache_service()
        logger.info("Customer orders service cache cleared")