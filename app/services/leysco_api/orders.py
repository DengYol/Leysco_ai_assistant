"""Sales order and customer order operations"""

import logging
import json
from typing import List, Dict, Optional
from datetime import datetime

from .utils import normalize_response, safe_float, is_html_response
from .cache import cache_api_result
from .constants import DELIVERY_CACHE_TTL

logger = logging.getLogger(__name__)


class OrdersHandler:
    """Handles sales orders and customer order operations"""
    
    def __init__(self, parent):
        self.parent = parent
        self.session = parent.session
        self.base_url = parent.base_url
        self.auth_handler = parent.auth_handler
    
    # =========================================================
    # ADD THESE MISSING METHODS
    # =========================================================
    
    def _record_cache_hit(self):
        """Record cache hit for statistics."""
        if hasattr(self.parent, '_record_cache_hit'):
            self.parent._record_cache_hit()
    
    def _record_cache_miss(self):
        """Record cache miss for statistics."""
        if hasattr(self.parent, '_record_cache_miss'):
            self.parent._record_cache_miss()
    
    def _record_api_call(self):
        """Record API call for statistics."""
        if hasattr(self.parent, '_record_api_call'):
            self.parent._record_api_call()
    
    def _record_error(self):
        """Record error for statistics."""
        if hasattr(self.parent, '_record_error'):
            self.parent._record_error()
    
    # =========================================================
    # EXISTING METHODS
    # =========================================================
    
    @cache_api_result(ttl_seconds=DELIVERY_CACHE_TTL)
    def get_open_sales_orders(self, customer_code: str = None, limit: int = 100) -> List[Dict]:
        """
        Fetch open sales orders with outstanding quantities from SAP Business One.
        Uses the confirmed working endpoint: /marketing/docs/17 with isDoc=1 and DocStatus=1.
        """
        try:
            if not self.auth_handler.ensure_auth():
                logger.warning("Not authenticated, cannot fetch open sales orders")
                return []

            # Ensure base_url doesn't have double slashes and includes /api/v1 if needed
            base = self.base_url.rstrip('/')
            if '/api/v1' not in base and 'api/v1' not in base:
                # Check if we need to add /api/v1
                if base.endswith('.com'):
                    url = f"{base}/api/v1/marketing/docs/17"
                else:
                    url = f"{base}/marketing/docs/17"
            else:
                url = f"{base}/marketing/docs/17"
            
            params = {
                "isDoc": 1,
                "page": 1,
                "per_page": limit,
                "DocStatus": 1,
                "IsICT": "N",
                "created_by": "",
            }
            if customer_code:
                params["CardCode"] = customer_code

            logger.info(f"📦 Fetching open sales orders from: {url}")
            self.parent._record_api_call()
            resp = self.session.get(url, params=params, timeout=30)

            if not self.auth_handler.check_auth(resp):
                logger.warning("Authentication failed fetching open sales orders")
                return []

            if resp.status_code != 200:
                logger.error(f"Open sales orders API error: {resp.status_code}")
                return []

            if is_html_response(resp.text):
                logger.warning("Received HTML response for open sales orders - token may be expired")
                return []

            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse open sales orders JSON: {e}")
                return []

            orders = self._parse_orders_response(data)

            if not orders:
                logger.info("No open sales orders found")
                return []

            # Flatten into line-item records
            formatted_orders = self._flatten_orders_to_line_items(orders, customer_code, limit)
            
            logger.info(f"✅ Processed {len(formatted_orders)} open line items from sales orders")
            return formatted_orders

        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch open sales orders: {e}", exc_info=True)
            return []
    
    @cache_api_result(ttl_seconds=DELIVERY_CACHE_TTL)
    def get_customer_orders(
        self,
        customer_code: str = None,
        customer_name: str = None,
        limit: int = 50,
        doc_status: str = "all",
        from_date: str = None,
        to_date: str = None
    ) -> List[Dict]:
        """Get customer orders from SAP Business One"""
        try:
            if not self.auth_handler.ensure_auth():
                return []
            
            # Resolve customer name to code if provided
            if customer_name and not customer_code:
                customer = self.parent.business_partners.resolve_customer(customer_name)
                if customer:
                    customer_code = customer.get("CardCode")
                    logger.info(f"Resolved customer '{customer_name}' to code: {customer_code}")
                else:
                    logger.warning(f"Could not resolve customer: {customer_name}")
                    return []
            
            if not customer_code:
                logger.warning("No customer code provided for orders fetch")
                return []
            
            # FIX: Use the correct endpoint with /api/v1 prefix
            # Check if base_url already has /api/v1
            base = self.base_url.rstrip('/')
            if '/api/v1' in base:
                url = f"{base}/marketing/docs/{customer_code}"
            elif base.endswith('.com'):
                url = f"{base}/api/v1/marketing/docs/{customer_code}"
            else:
                url = f"{base}/marketing/docs/{customer_code}"
            
            params = {}
            if from_date:
                params["FromDate"] = from_date
            if to_date:
                params["ToDate"] = to_date
            
            logger.info(f"📋 Fetching customer orders from: {url}")
            self.parent._record_api_call()
            resp = self.session.get(url, params=params, timeout=30)
            
            if not self.auth_handler.check_auth(resp):
                logger.warning(f"Authentication failed for orders fetch: {resp.status_code}")
                return []
            
            if resp.status_code == 404:
                logger.info(f"No orders found for customer {customer_code} (404 response)")
                return []
            
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch orders: {resp.status_code} - {resp.text[:200]}")
                return []
            
            if is_html_response(resp.text):
                logger.warning("Received HTML response - authentication may have expired")
                return []
            
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse orders JSON: {e}")
                return []
            
            # Parse the response - different possible structures
            orders = []
            if isinstance(data, dict):
                # Check for ResponseData structure
                if data.get("ResponseData"):
                    response_data = data["ResponseData"]
                    if isinstance(response_data, dict):
                        # Check for data array inside
                        if "data" in response_data:
                            orders = response_data["data"]
                        else:
                            orders = [response_data]
                    elif isinstance(response_data, list):
                        orders = response_data
                elif data.get("data"):
                    orders = data["data"]
                elif data.get("results"):
                    orders = data["results"]
                else:
                    # Assume the whole response is the order
                    orders = [data] if data.get("DocNum") else []
            elif isinstance(data, list):
                orders = data
            
            if not orders:
                logger.info(f"No orders found for {customer_name or customer_code}")
                return []
            
            # Filter and format orders
            filtered_orders = self._filter_and_format_orders(orders, doc_status)
            
            logger.info(f"✅ Retrieved {len(filtered_orders)} orders for {customer_name or customer_code}")
            return filtered_orders[:limit]
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch customer orders: {e}", exc_info=True)
            return []
    
    def _parse_orders_response(self, data: dict) -> List[Dict]:
        """Parse orders from API response"""
        orders = []
        if data.get("ResultState") and data.get("ResponseData"):
            response_data = data["ResponseData"]
            if isinstance(response_data, dict):
                if "data" in response_data:
                    orders = response_data["data"]
                elif "DocumentLines" in response_data:
                    orders = [response_data]
            elif isinstance(response_data, list):
                orders = response_data
        else:
            orders = normalize_response(data)
        return orders
    
    def _flatten_orders_to_line_items(self, orders: List[Dict], customer_code: str = None, limit: int = 100) -> List[Dict]:
        """Flatten orders into line-item records"""
        formatted_orders = []
        
        for order in orders[:limit]:
            doc_num = order.get("DocNum") or order.get("doc_num")
            doc_entry = order.get("DocEntry") or order.get("doc_entry")
            card_code = order.get("CardCode") or order.get("card_code") or customer_code
            card_name = order.get("CardName") or order.get("card_name") or "Unknown"
            doc_date = order.get("DocDate") or order.get("doc_date") or ""
            doc_due_date = order.get("DocDueDate") or order.get("doc_due_date") or ""

            items = (
                order.get("DocumentLines")
                or order.get("items")
                or order.get("Lines")
                or order.get("document_lines")
                or []
            )

            if not items and order.get("ItemCode"):
                items = [order]

            for item in items:
                item_code = item.get("ItemCode") or item.get("item_code")
                item_name = item.get("ItemName") or item.get("item_name")
                quantity = safe_float(item.get("Quantity") or item.get("quantity"))
                open_qty = safe_float(item.get("OpenQty") or item.get("open_qty") or item.get("OpenQuantity") or quantity)
                price = safe_float(item.get("Price") or item.get("price"))

                if open_qty > 0:
                    # Check if overdue
                    is_overdue = False
                    if doc_due_date:
                        try:
                            due_date = datetime.strptime(str(doc_due_date)[:10], "%Y-%m-%d")
                            if due_date < datetime.now():
                                is_overdue = True
                        except:
                            pass
                    
                    formatted_orders.append({
                        "DocNum": doc_num,
                        "DocEntry": doc_entry,
                        "CardCode": card_code,
                        "CardName": card_name,
                        "DocDate": doc_date,
                        "DocDueDate": doc_due_date,
                        "ItemCode": item_code,
                        "ItemName": item_name,
                        "Quantity": quantity,
                        "OpenQty": open_qty,
                        "Price": price,
                        "LineTotal": open_qty * price,
                        "Status": "Overdue" if is_overdue else "Open",
                        "IsOverdue": is_overdue,
                    })
        
        return formatted_orders
    
    def _filter_and_format_orders(self, orders: List[Dict], doc_status: str) -> List[Dict]:
        """Filter and format orders by status"""
        filtered_orders = []
        
        for order in orders:
            doc_num = order.get("DocNum")
            if not doc_num:
                continue
            
            # Determine order status
            has_open_items = False
            items = order.get("DocumentLines", [])
            for item in items:
                if safe_float(item.get("OpenQty", 0)) > 0:
                    has_open_items = True
                    break
            
            order_status = "open" if has_open_items else "closed"
            
            if doc_status != "all" and order_status != doc_status:
                continue
            
            formatted_order = {
                "DocNum": doc_num,
                "DocEntry": order.get("DocEntry"),
                "DocDate": order.get("DocDate", ""),
                "DocDueDate": order.get("DocDueDate", ""),
                "CardCode": order.get("CardCode"),
                "CardName": order.get("CardName", "Unknown"),
                "DocTotal": safe_float(order.get("DocTotal")),
                "Status": "Open" if has_open_items else "Closed",
                "Items": []
            }
            
            for item in items:
                formatted_order["Items"].append({
                    "ItemCode": item.get("ItemCode"),
                    "ItemName": item.get("ItemName"),
                    "Quantity": safe_float(item.get("Quantity")),
                    "OpenQty": safe_float(item.get("OpenQty")),
                    "Price": safe_float(item.get("Price")),
                    "LineTotal": safe_float(item.get("LineTotal"))
                })
            
            filtered_orders.append(formatted_order)
        
        return filtered_orders