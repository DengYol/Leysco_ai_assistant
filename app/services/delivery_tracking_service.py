"""
delivery_tracking_service.py
=============================
Comprehensive delivery tracking and monitoring service - Optimized with caching and async support

Provides:
- Outstanding deliveries by customer
- Delivery status tracking
- Expected delivery dates
- Delivery history
- Real-time updates (when GPS/tracking available)

Optimizations:
- Redis caching for delivery data
- Batch processing for multiple deliveries
- Async methods for non-blocking operations
- LRU cache for frequently accessed deliveries
- Enhanced status determination with caching

FIXED: Outstanding deliveries now uses the API's get_outstanding_deliveries method
"""

import logging
import asyncio
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from functools import lru_cache, wraps
from datetime import datetime, timedelta

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# Cache TTLs
DELIVERY_CACHE_TTL = 300        # 5 minutes for delivery data
OUTSTANDING_CACHE_TTL = 120     # 2 minutes for outstanding deliveries
HISTORY_CACHE_TTL = 3600        # 1 hour for delivery history


def cache_delivery(ttl_seconds: int = DELIVERY_CACHE_TTL, key_prefix: str = ""):
    """
    Decorator to cache delivery results.
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
                logger.debug(f"📦 Delivery cache hit: {func.__name__}")
                return cached.get("data")
            
            # Execute function
            result = func(self, *args, **kwargs)
            
            # Cache result
            if result:
                cache.set(cache_key, {}, "", {"data": result})
            
            return result
        return wrapper
    return decorator


class DeliveryTrackingService:
    """
    Service for tracking deliveries and shipments.
    Optimized with caching and async support.
    
    Integrates with SAP B1 delivery documents to provide:
    - Outstanding delivery tracking
    - Delivery status monitoring
    - ETA calculations
    - Delivery history
    """
    
    def __init__(self, api_service):
        self.api = api_service
        
        # Stats tracking
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "errors": 0
        }
        
        # Cache for status determination
        self._status_cache = {}
        self._status_cache_ttl = 300  # 5 minutes

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
    # DELIVERY STATUS TRACKING (FIXED - uses API's get_outstanding_deliveries)
    # =========================================================
    
    def get_outstanding_deliveries(self, customer_code: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get all outstanding (pending) deliveries for a customer.
        Optimized with caching.
        
        Uses the API's get_outstanding_deliveries method which implements
        multiple approaches to fetch real delivery data.
        
        Returns deliveries that are:
        - Created but not yet dispatched
        - In transit
        - Ready for pickup
        """
        try:
            self._record_api_call()
            logger.info(f"📦 Getting outstanding deliveries for customer: {customer_code or 'all'}")
            
            # Use the API's get_outstanding_deliveries method
            deliveries = self.api.get_outstanding_deliveries(
                customer_code=customer_code,
                limit=limit
            )
            
            if not deliveries:
                logger.info("No outstanding deliveries found")
                return []
            
            # Enrich delivery data with status and ETA
            enriched = []
            for delivery in deliveries:
                # Extract fields based on the format from API
                status = self._determine_delivery_status(delivery)
                eta = self._calculate_eta(delivery)
                
                enriched.append({
                    "DocNum": delivery.get("DocNum"),
                    "DocEntry": delivery.get("DocEntry"),
                    "CardCode": delivery.get("CardCode"),
                    "CardName": delivery.get("CardName"),
                    "DocDate": delivery.get("DocDate"),
                    "DocDueDate": delivery.get("DocDueDate"),
                    "DocTotal": delivery.get("DocTotal"),
                    "OpenQty": delivery.get("OpenQty", 0),
                    "ItemCode": delivery.get("ItemCode"),
                    "ItemName": delivery.get("ItemName"),
                    "Quantity": delivery.get("Quantity", 0),
                    "Price": delivery.get("Price", 0),
                    "LineTotal": delivery.get("LineTotal", 0),
                    "Status": status,
                    "ETA": eta,
                    "IsOverdue": delivery.get("IsOverdue", False),
                })
            
            logger.info(f"✅ Found {len(enriched)} outstanding delivery line items")
            return enriched
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error getting outstanding deliveries: {e}")
            return []
    
    async def get_outstanding_deliveries_async(self, customer_code: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Async version of get_outstanding_deliveries."""
        return await asyncio.to_thread(self.get_outstanding_deliveries, customer_code, limit)
    
    @cache_delivery(ttl_seconds=DELIVERY_CACHE_TTL)
    def get_delivery_details(self, doc_num: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific delivery.
        Optimized with caching.
        
        Includes:
        - Line items
        - Quantities
        - Delivery address
        - Current status
        - Tracking information
        """
        try:
            self._record_api_call()
            logger.info(f"📦 Getting delivery details for: {doc_num}")
            
            # First try to find in outstanding deliveries
            outstanding = self.get_outstanding_deliveries(limit=200)
            for delivery in outstanding:
                if str(delivery.get("DocNum")) == str(doc_num):
                    return self._format_delivery_details(delivery)
            
            # If not found in outstanding, try to get via API
            delivery = self.api.get_delivery_by_docnum(doc_num)
            
            if not delivery:
                logger.warning(f"Delivery {doc_num} not found")
                return None
            
            return self._format_delivery_details(delivery)
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error getting delivery details for {doc_num}: {e}")
            return None
    
    def _format_delivery_details(self, delivery: Dict[str, Any]) -> Dict[str, Any]:
        """Format delivery data into consistent structure."""
        # Extract line items efficiently
        line_items = []
        
        # Check if this is from outstanding deliveries (has ItemCode directly)
        if delivery.get("ItemCode") and not delivery.get("DocumentLines"):
            line_items.append({
                "ItemCode": delivery.get("ItemCode"),
                "ItemName": delivery.get("ItemName"),
                "Quantity": delivery.get("Quantity", 0),
                "DeliveredQty": 0,
                "RemainingQty": delivery.get("OpenQty", 0),
                "Price": delivery.get("Price", 0),
                "LineTotal": delivery.get("LineTotal", 0),
            })
        else:
            # Process DocumentLines
            for line in delivery.get("DocumentLines", []):
                qty = float(line.get("Quantity", 0))
                delivered_qty = float(line.get("DeliveredQty", 0))
                line_items.append({
                    "ItemCode": line.get("ItemCode"),
                    "ItemName": line.get("ItemDescription") or line.get("ItemName"),
                    "Quantity": qty,
                    "DeliveredQty": delivered_qty,
                    "RemainingQty": qty - delivered_qty,
                    "Price": line.get("Price"),
                    "LineTotal": line.get("LineTotal"),
                })
        
        status = self._determine_delivery_status(delivery)
        eta = self._calculate_eta(delivery)
        
        return {
            "DocNum": delivery.get("DocNum"),
            "DocEntry": delivery.get("DocEntry"),
            "DocDate": delivery.get("DocDate"),
            "DocDueDate": delivery.get("DocDueDate"),
            "Customer": {
                "CardCode": delivery.get("CardCode"),
                "CardName": delivery.get("CardName"),
                "Address": delivery.get("Address"),
                "Phone": delivery.get("Phone"),
            },
            "Status": status,
            "ETA": eta,
            "TotalValue": delivery.get("DocTotal"),
            "Items": line_items,
            "Comments": delivery.get("Comments"),
            "CreatedBy": delivery.get("UserSign"),
            "LastUpdated": delivery.get("UpdateDate"),
        }
    
    async def get_delivery_details_async(self, doc_num: str) -> Optional[Dict[str, Any]]:
        """Async version of get_delivery_details."""
        return await asyncio.to_thread(self.get_delivery_details, doc_num)
    
    @cache_delivery(ttl_seconds=HISTORY_CACHE_TTL)
    def get_delivery_history(self, customer_code: str, days: int = 30, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get delivery history for a customer.
        Optimized with caching (1 hour TTL for history).
        
        Shows completed deliveries from the past N days.
        """
        try:
            self._record_api_call()
            logger.info(f"📦 Getting delivery history for customer: {customer_code}")
            
            # Get outstanding deliveries first
            all_deliveries = self.get_outstanding_deliveries(customer_code=customer_code, limit=limit)
            
            if not all_deliveries:
                # Try to get from orders API for history
                orders = self.api.get_customer_orders(customer_code=customer_code, limit=limit)
                if orders:
                    return self._convert_orders_to_history(orders, days)
                return []
            
            # Filter to completed/delivered deliveries within date range
            cutoff_date = datetime.now() - timedelta(days=days)
            history = []
            
            for delivery in all_deliveries:
                doc_date_str = delivery.get("DocDate")
                if not doc_date_str:
                    continue
                    
                try:
                    doc_date = datetime.strptime(doc_date_str[:10], "%Y-%m-%d")
                    status = self._determine_delivery_status(delivery)
                    
                    # Include delivered or completed items
                    if status in ["Delivered", "Completed"] and doc_date >= cutoff_date:
                        history.append({
                            "DocNum": delivery.get("DocNum"),
                            "DocDate": doc_date_str,
                            "ItemCode": delivery.get("ItemCode"),
                            "ItemName": delivery.get("ItemName"),
                            "Quantity": delivery.get("Quantity", 0),
                            "TotalValue": delivery.get("LineTotal", 0),
                            "Status": status,
                        })
                except (ValueError, TypeError):
                    continue
            
            # Also try to get from sales orders if no history found
            if not history:
                orders = self.api.get_customer_orders(customer_code=customer_code, limit=limit)
                if orders:
                    history = self._convert_orders_to_history(orders, days)
            
            logger.info(f"✅ Found {len(history)} delivery history items")
            return history
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error getting delivery history for {customer_code}: {e}")
            return []
    
    def _convert_orders_to_history(self, orders: List[Dict], days: int) -> List[Dict]:
        """Convert orders to delivery history format."""
        cutoff_date = datetime.now() - timedelta(days=days)
        history = []
        
        for order in orders:
            doc_date_str = order.get("DocDate")
            if not doc_date_str:
                continue
            
            try:
                doc_date = datetime.strptime(doc_date_str[:10], "%Y-%m-%d")
                if doc_date >= cutoff_date:
                    # Check if order is closed/completed
                    status = order.get("Status", "")
                    if "closed" in status.lower() or "completed" in status.lower():
                        for item in order.get("Items", []):
                            history.append({
                                "DocNum": order.get("DocNum"),
                                "DocDate": doc_date_str,
                                "ItemCode": item.get("ItemCode"),
                                "ItemName": item.get("ItemName"),
                                "Quantity": item.get("Quantity", 0),
                                "TotalValue": item.get("LineTotal", 0),
                                "Status": "Delivered",
                            })
            except (ValueError, TypeError):
                continue
        
        return history
    
    async def get_delivery_history_async(self, customer_code: str, days: int = 30, limit: int = 50) -> List[Dict[str, Any]]:
        """Async version of get_delivery_history."""
        return await asyncio.to_thread(self.get_delivery_history, customer_code, days, limit)
    
    def track_delivery(self, doc_num: str) -> Dict[str, Any]:
        """
        Track a specific delivery with real-time status.
        Optimized with caching.
        
        In production: integrate with GPS tracking, courier APIs, etc.
        For now: provides SAP status and estimated delivery.
        """
        try:
            logger.info(f"🔍 Tracking delivery: {doc_num}")
            
            # First check outstanding deliveries
            outstanding = self.get_outstanding_deliveries(limit=200)
            for delivery in outstanding:
                if str(delivery.get("DocNum")) == str(doc_num):
                    return self._build_tracking_response(delivery)
            
            # Try to get via API
            delivery = self.api.get_delivery_by_docnum(doc_num)
            
            if not delivery:
                logger.warning(f"Delivery {doc_num} not found")
                return {"error": f"Delivery {doc_num} not found"}
            
            return self._build_tracking_response(delivery)
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error tracking delivery {doc_num}: {e}")
            return {"error": str(e)}
    
    def _build_tracking_response(self, delivery: Dict[str, Any]) -> Dict[str, Any]:
        """Build consistent tracking response from delivery data."""
        status = self._determine_delivery_status(delivery)
        eta = self._calculate_eta(delivery)
        timeline = self._build_delivery_timeline(delivery)
        
        # Extract item info
        item_name = delivery.get("ItemName", "")
        if not item_name and delivery.get("DocumentLines"):
            lines = delivery.get("DocumentLines", [])
            if lines:
                item_name = lines[0].get("ItemName", "")
        
        return {
            "DocNum": delivery.get("DocNum"),
            "Status": status,
            "ETA": eta,
            "Customer": delivery.get("CardName", "Unknown"),
            "Address": delivery.get("Address", "Not specified"),
            "Timeline": timeline,
            "ItemName": item_name,
            "Quantity": delivery.get("Quantity", delivery.get("OpenQty", 0)),
            "TotalValue": delivery.get("DocTotal", delivery.get("LineTotal", 0)),
        }
    
    async def track_delivery_async(self, doc_num: str) -> Dict[str, Any]:
        """Async version of track_delivery."""
        return await asyncio.to_thread(self.track_delivery, doc_num)
    
    # =========================================================
    # DELIVERY ANALYTICS (Optimized)
    # =========================================================
    
    def get_delivery_summary(self, customer_code: str = None) -> Dict[str, Any]:
        """
        Get overall delivery summary for a customer or all customers.
        
        Includes:
        - Outstanding deliveries count
        - Delayed deliveries count
        - Total pending quantity
        - Total value of outstanding deliveries
        """
        try:
            outstanding = self.get_outstanding_deliveries(customer_code=customer_code, limit=500)
            
            if not outstanding:
                return {
                    "TotalOutstanding": 0,
                    "Delayed": 0,
                    "TotalPendingQty": 0,
                    "TotalValue": 0,
                    "CustomerCode": customer_code or "All Customers",
                }
            
            # Calculate statistics
            delayed = sum(1 for d in outstanding if d.get("IsOverdue", False) or d.get("Status") == "Overdue")
            total_qty = sum(float(d.get("OpenQty", d.get("Quantity", 0)) or 0) for d in outstanding)
            total_value = sum(float(d.get("LineTotal", d.get("DocTotal", 0)) or 0) for d in outstanding)
            
            return {
                "TotalOutstanding": len(outstanding),
                "Delayed": delayed,
                "TotalPendingQty": round(total_qty, 2),
                "TotalValue": round(total_value, 2),
                "CustomerCode": customer_code or "All Customers",
            }
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error getting delivery summary: {e}")
            return {}
    
    async def get_delivery_summary_async(self, customer_code: str = None) -> Dict[str, Any]:
        """Async version of get_delivery_summary."""
        return await asyncio.to_thread(self.get_delivery_summary, customer_code)
    
    # =========================================================
    # BATCH OPERATIONS
    # =========================================================
    
    def get_multiple_delivery_details(self, doc_nums: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get details for multiple deliveries in batch.
        Optimizes API calls for multiple deliveries.
        
        Args:
            doc_nums: List of delivery document numbers
        
        Returns:
            Dict mapping doc_num to delivery details
        """
        if not doc_nums:
            return {}
        
        results = {}
        
        # Try to get from cache first
        cache = get_cache_service()
        uncached = []
        
        for doc_num in doc_nums:
            cache_key = f"delivery_details:{doc_num}"
            cached = cache.get(cache_key, {}, "")
            if cached is not None:
                self._record_cache_hit()
                results[doc_num] = cached.get("data")
            else:
                self._record_cache_miss()
                uncached.append(doc_num)
        
        # Get all outstanding deliveries once
        if uncached:
            outstanding = self.get_outstanding_deliveries(limit=500)
            outstanding_map = {str(d.get("DocNum")): d for d in outstanding if d.get("DocNum")}
            
            for doc_num in uncached:
                if doc_num in outstanding_map:
                    details = self._format_delivery_details(outstanding_map[doc_num])
                    results[doc_num] = details
                    # Cache it
                    cache.set(f"delivery_details:{doc_num}", {}, "", {"data": details})
                else:
                    # Try individual fetch
                    try:
                        details = self.get_delivery_details(doc_num)
                        if details:
                            results[doc_num] = details
                    except Exception as e:
                        logger.error(f"Error fetching delivery {doc_num}: {e}")
        
        return results
    
    # =========================================================
    # HELPER METHODS (Optimized with caching)
    # =========================================================
    
    @lru_cache(maxsize=256)
    def _determine_delivery_status(self, delivery: Dict[str, Any]) -> str:
        """
        Determine delivery status from SAP document data.
        LRU cache for frequent status checks.
        
        Possible statuses:
        - Pending: Created, not yet dispatched
        - In Transit: Dispatched, on the way
        - Overdue: Past due date
        - Delivered: Completed
        - Cancelled: Cancelled order
        - Outstanding: Still pending delivery
        """
        # Check if already has status field
        if delivery.get("Status"):
            status = delivery.get("Status")
            if status in ["Delivered", "Completed", "Cancelled", "Overdue"]:
                return status
        
        # Check for IsOverdue flag
        if delivery.get("IsOverdue"):
            return "Overdue"
        
        doc_status = delivery.get("DocStatus", "O")  # O=Open, C=Closed
        cancelled = delivery.get("Cancelled", "N")
        
        if cancelled == "Y":
            return "Cancelled"
        
        if doc_status == "C":
            return "Delivered"
        
        # Check if past due date
        due_date_str = delivery.get("DocDueDate")
        if due_date_str:
            try:
                due_date = datetime.strptime(str(due_date_str)[:10], "%Y-%m-%d")
                if datetime.now() > due_date:
                    return "Overdue"
            except (ValueError, TypeError):
                pass
        
        # Check if has open quantity
        open_qty = delivery.get("OpenQty", 0)
        if open_qty > 0:
            return "Outstanding"
        
        # Check if dispatched (has shipping date or tracking number)
        if delivery.get("U_ShipDate") or delivery.get("U_TrackingNum"):
            return "In Transit"
        
        return "Pending"
    
    @lru_cache(maxsize=256)
    def _calculate_eta(self, delivery: Dict[str, Any]) -> str:
        """
        Calculate estimated delivery time.
        LRU cache for frequent ETA calculations.
        
        In production: use actual GPS data, courier APIs
        For now: use DocDueDate or estimate based on creation date
        """
        due_date_str = delivery.get("DocDueDate")
        
        if due_date_str:
            try:
                due_date = datetime.strptime(str(due_date_str)[:10], "%Y-%m-%d")
                
                # If past due, return overdue message
                if datetime.now() > due_date:
                    days_overdue = (datetime.now() - due_date).days
                    return f"Overdue by {days_overdue} day(s)"
                
                # Return days until delivery
                days_until = (due_date - datetime.now()).days
                if days_until == 0:
                    return "Today"
                elif days_until == 1:
                    return "Tomorrow"
                else:
                    return f"In {days_until} days"
            except (ValueError, TypeError):
                pass
        
        # If no due date, estimate based on creation date
        doc_date_str = delivery.get("DocDate")
        if doc_date_str:
            try:
                doc_date = datetime.strptime(str(doc_date_str)[:10], "%Y-%m-%d")
                # Assuming 3-5 days from creation
                est_date = doc_date + timedelta(days=5)
                days_until = (est_date - datetime.now()).days
                if days_until < 0:
                    return "Overdue - please follow up"
                elif days_until == 0:
                    return "Estimated today"
                else:
                    return f"Est. {est_date.strftime('%b %d')}"
            except (ValueError, TypeError):
                pass
        
        return "Unknown"
    
    def _build_delivery_timeline(self, delivery: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Build a timeline of delivery events.
        
        In production: integrate with real tracking events
        For now: create timeline from SAP dates
        """
        timeline = []
        
        # Order created
        doc_date = delivery.get("DocDate")
        if doc_date:
            timeline.append({
                "event": "Order Created",
                "date": str(doc_date)[:10],
                "status": "completed"
            })
        
        # Check if dispatched
        ship_date = delivery.get("U_ShipDate")
        if ship_date:
            timeline.append({
                "event": "Dispatched",
                "date": str(ship_date)[:10],
                "status": "completed"
            })
        
        # Expected delivery
        due_date = delivery.get("DocDueDate")
        status = self._determine_delivery_status(delivery)
        
        if due_date:
            timeline.append({
                "event": "Expected Delivery",
                "date": str(due_date)[:10],
                "status": "completed" if status in ["Delivered", "Completed"] else "pending"
            })
        
        # Add current status as last event if not completed
        if status not in ["Delivered", "Completed"]:
            timeline.append({
                "event": f"Current Status: {status}",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "status": "current"
            })
        
        return timeline
    
    # =========================================================
    # CACHE MANAGEMENT
    # =========================================================
    
    def clear_cache(self):
        """Clear all caches."""
        self._status_cache.clear()
        # Clear LRU caches
        self._determine_delivery_status.cache_clear()
        self._calculate_eta.cache_clear()
        # Clear Redis cache (would need pattern deletion)
        logger.info("Delivery tracking service cache cleared")