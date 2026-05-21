"""Delivery tracking and outstanding deliveries operations"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from .utils import safe_float, is_html_response
from .cache import cache_api_result
from .constants import DELIVERY_CACHE_TTL

logger = logging.getLogger(__name__)


class DeliveriesHandler:
    """Handles delivery tracking and outstanding deliveries"""
    
    def __init__(self, parent):
        self.parent = parent
        self.session = parent.session
        self.base_url = parent.base_url
        self.auth_handler = parent.auth_handler
    
    def _record_cache_hit(self):
        """Record cache hit for statistics."""
        if hasattr(self.parent, '_record_cache_hit'):
            self.parent._record_cache_hit()
    
    def _record_cache_miss(self):
        """Record cache miss for statistics."""
        if hasattr(self.parent, '_record_cache_miss'):
            self.parent._record_cache_miss()
    
    @cache_api_result(ttl_seconds=DELIVERY_CACHE_TTL)
    def get_outstanding_deliveries(
        self,
        customer_code: str = None,
        customer_name: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Fetch outstanding deliveries using multiple approaches.
        
        Approach 1: /marketing/docs/17 with DocStatus=1 (open orders)
        Approach 2: /marketing/docs/15 (deliveries endpoint)
        Approach 3: /deliveries endpoint
        """
        try:
            if not self.auth_handler.ensure_auth():
                logger.warning("Not authenticated, cannot fetch outstanding deliveries")
                return []

            # Resolve customer name → code if needed
            if customer_name and not customer_code:
                customer = self.parent.business_partners.resolve_customer(customer_name)
                if customer:
                    customer_code = customer.get("CardCode")
                    logger.info(f"✅ Resolved customer '{customer_name}' → CardCode: {customer_code}")

            # Approach 1: Sales Orders with DocStatus=1
            result = self._approach_1_sales_orders(customer_code, limit)
            if result:
                return result

            # Approach 2: Deliveries endpoint
            result = self._approach_2_deliveries_endpoint(customer_code, limit)
            if result:
                return result

            # Approach 3: Inventory fallback
            result = self._approach_3_inventory_fallback(customer_code, limit)
            if result:
                return result
            
            logger.info("No outstanding deliveries found using any approach")
            return []
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch outstanding deliveries: {e}", exc_info=True)
            return []
    
    def _approach_1_sales_orders(self, customer_code: str = None, limit: int = 100) -> List[Dict]:
        """Get outstanding deliveries from sales orders"""
        url = f"{self.base_url}/marketing/docs/17"
        params = {
            "isDoc": 1,
            "page": 1,
            "per_page": limit,
            "DocStatus": 1,
            "IsICT": "N",
        }
        if customer_code:
            params["CardCode"] = customer_code

        logger.info(f"📦 Approach 1: Fetching from {url}")
        self.parent._record_api_call()
        resp = self.session.get(url, params=params, timeout=30)

        if resp and not is_html_response(resp.text):
            try:
                data = resp.json()
                orders = self._parse_orders_response(data)
                if orders:
                    logger.info(f"✅ Found {len(orders)} outstanding orders via Approach 1")
                    return self._process_outstanding_orders(orders, customer_code, limit)
            except Exception as e:
                logger.warning(f"Approach 1 parsing error: {e}")
        
        return []
    
    def _approach_2_deliveries_endpoint(self, customer_code: str = None, limit: int = 100) -> List[Dict]:
        """Get outstanding deliveries from deliveries endpoint"""
        url = f"{self.base_url}/marketing/docs/15"
        params = {"page": 1, "per_page": limit}
        if customer_code:
            params["CardCode"] = customer_code
        
        logger.info(f"📦 Approach 2: Fetching from {url}")
        self.parent._record_api_call()
        resp = self.session.get(url, params=params, timeout=30)
        
        if resp and not is_html_response(resp.text):
            try:
                data = resp.json()
                deliveries = self._parse_deliveries_response(data)
                if deliveries:
                    logger.info(f"✅ Found {len(deliveries)} deliveries via Approach 2")
                    outstanding = [d for d in deliveries if d.get("DocStatus") != "C" and safe_float(d.get("OpenQty", 0)) > 0]
                    if outstanding:
                        return self._process_deliveries(outstanding, customer_code, limit)
            except Exception as e:
                logger.warning(f"Approach 2 parsing error: {e}")
        
        return []
    
    def _approach_3_inventory_fallback(self, customer_code: str = None, limit: int = 100) -> List[Dict]:
        """Fallback to inventory report"""
        logger.info(f"📦 Approach 3: Using inventory report fallback")
        inventory = self.parent.inventory.get_inventory_report(limit=limit)
        if inventory:
            outstanding_items = [
                item for item in inventory 
                if safe_float(item.get("CurrentIsCommited", 0)) > 0
            ][:limit]
            
            if outstanding_items:
                logger.info(f"✅ Found {len(outstanding_items)} items with pending commitments")
                return self._convert_inventory_to_outstanding(outstanding_items, customer_code)
        
        return []
    
    def _process_outstanding_orders(self, orders: List[Dict], customer_code: str = None, limit: int = 100) -> List[Dict]:
        """Process raw orders into outstanding delivery format"""
        outstanding = []
        
        for order in orders[:limit]:
            doc_num = order.get("DocNum")
            doc_entry = order.get("DocEntry")
            card_code = order.get("CardCode") or customer_code
            card_name = order.get("CardName", "Unknown")
            doc_date = order.get("DocDate", "")
            doc_due_date = order.get("DocDueDate", "")
            doc_total = safe_float(order.get("DocTotal"))
            
            items = order.get("document_lines", []) or order.get("DocumentLines", [])
            
            for item in items:
                item_code = item.get("ItemCode")
                item_name = item.get("ItemName", item_code)
                quantity = safe_float(item.get("Quantity"))
                open_qty = safe_float(item.get("OpenQty") or item.get("OpenQuantity") or quantity)
                price = safe_float(item.get("Price"))
                
                if open_qty > 0:
                    is_overdue = self._check_if_overdue(doc_due_date)
                    
                    outstanding.append({
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
                        "Status": "Overdue" if is_overdue else "Outstanding",
                        "IsOverdue": is_overdue,
                    })
        
        logger.info(f"Processed {len(outstanding)} outstanding line items")
        return outstanding
    
    def _process_deliveries(self, deliveries: List[Dict], customer_code: str = None, limit: int = 100) -> List[Dict]:
        """Process deliveries into outstanding format"""
        outstanding = []
        
        for delivery in deliveries[:limit]:
            doc_num = delivery.get("DocNum")
            card_code = delivery.get("CardCode") or customer_code
            card_name = delivery.get("CardName", "Unknown")
            doc_date = delivery.get("DocDate", "")
            doc_due_date = delivery.get("DocDueDate", "")
            
            items = delivery.get("document_lines", []) or delivery.get("DocumentLines", [])
            
            for item in items:
                item_code = item.get("ItemCode")
                item_name = item.get("ItemName", item_code)
                quantity = safe_float(item.get("Quantity"))
                open_qty = safe_float(item.get("OpenQty") or item.get("Quantity"))
                price = safe_float(item.get("Price"))
                
                if open_qty > 0:
                    is_overdue = self._check_if_overdue(doc_due_date)
                    
                    outstanding.append({
                        "DocNum": doc_num,
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
                        "Status": "Overdue" if is_overdue else "Pending",
                        "IsOverdue": is_overdue,
                    })
        
        return outstanding
    
    def _convert_inventory_to_outstanding(self, inventory_items: List[Dict], customer_code: str = None) -> List[Dict]:
        """Convert inventory items with commitments to outstanding delivery format"""
        outstanding = []
        
        for item in inventory_items[:50]:
            outstanding.append({
                "DocNum": None,
                "DocEntry": None,
                "CardCode": customer_code,
                "CardName": "Pending Delivery",
                "DocDate": datetime.now().strftime("%Y-%m-%d"),
                "DocDueDate": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                "ItemCode": item.get("ItemCode"),
                "ItemName": item.get("ItemName"),
                "Quantity": safe_float(item.get("CurrentIsCommited", 0)),
                "OpenQty": safe_float(item.get("CurrentIsCommited", 0)),
                "Price": 0,
                "LineTotal": 0,
                "Status": "Pending",
                "IsOverdue": False,
                "Note": "Based on inventory commitments"
            })
        
        return outstanding
    
    def _parse_orders_response(self, data: dict) -> List[Dict]:
        """Parse orders from API response"""
        orders = []
        if data.get("ResultState") and data.get("ResponseData"):
            response_data = data["ResponseData"]
            if isinstance(response_data, dict):
                orders = response_data.get("data", [])
            elif isinstance(response_data, list):
                orders = response_data
        return orders
    
    def _parse_deliveries_response(self, data: dict) -> List[Dict]:
        """Parse deliveries from API response"""
        deliveries = []
        if data.get("ResultState") and data.get("ResponseData"):
            response_data = data["ResponseData"]
            if isinstance(response_data, dict):
                deliveries = response_data.get("data", [])
            elif isinstance(response_data, list):
                deliveries = response_data
        return deliveries
    
    def _check_if_overdue(self, due_date: str) -> bool:
        """Check if a delivery is overdue"""
        if not due_date:
            return False
        try:
            due = datetime.strptime(str(due_date)[:10], "%Y-%m-%d")
            return due < datetime.now()
        except:
            return False