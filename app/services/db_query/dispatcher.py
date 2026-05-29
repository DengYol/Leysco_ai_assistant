"""
Dispatcher - Routes intents to appropriate query handlers
"""

import logging
from typing import Dict, List, Any, Optional

from .transformers import (
    CustomerTransformer,
    DeliveryTransformer,
    AnalyticsTransformer,
    PriceTransformer,
)
from .constants import DELIVERY_INTENTS, PRICE_INTENTS

logger = logging.getLogger(__name__)


class Dispatcher:
    """
    Routes intents to specific query methods.
    FALLBACK: If no specific handler exists, returns None (let caller handle).
    """

    def __init__(self, service):
        """Initialize with reference to the DBQueryService instance."""
        self.service = service

    def should_process(self, intent: str) -> bool:
        """
        Determine if this intent should be processed by DBQueryService.
        Returns True for intents that DBQueryService can handle directly.
        """
        db_handled_intents = {
            # Customer intents
            "GET_CUSTOMERS",
            "GET_CUSTOMER_DETAILS",
            "GET_CUSTOMER_ORDERS",
            "GET_CUSTOMER_INVOICES",
            "GET_OUTSTANDING_INVOICES",
            "GET_CUSTOMER_HEALTH",
            "GET_CUSTOMER_BALANCE",

            # Delivery intents
            "GET_OUTSTANDING_DELIVERIES",
            "TRACK_DELIVERY",
            "GET_DELIVERY_HISTORY",

            # Item/Stock intents
            "GET_ITEMS",
            "GET_SELLABLE_ITEMS",
            "GET_PURCHASABLE_ITEMS",
            "GET_INVENTORY_ITEMS",
            "GET_ITEM_DETAILS",
            "GET_STOCK_LEVELS",
            "GET_WAREHOUSES",
            "GET_WAREHOUSE_STOCK",
            "GET_LOW_STOCK_ALERTS",

            # Price intents
            "GET_ITEM_PRICE",
            "GET_CUSTOMER_PRICE",

            # Invoice intents
            "GET_AR_INVOICES",
            "GET_AP_INVOICES",
            "GET_OVERDUE_INVOICES",
            "GET_CUSTOMER_BALANCE",

            # Purchase intents
            "GET_PURCHASE_ORDERS",
            "GET_PURCHASE_REQUESTS",
            "GET_GOODS_RECEIPT_PO",

            # Inventory intents
            "GET_INVENTORY_VALUATION",
            "GET_REORDER_REPORT",
        }

        action_router_intents = {
            "CREATE_QUOTATION",
            "CREATE_PURCHASE_ORDER",
            "CREATE_GOODS_ISSUE",
            "CREATE_GOODS_RECEIPT",
            "CREATE_STOCK_TRANSFER",
            "CONVERT_QUOTATION_TO_ORDER",
            "POST_INVOICE",
            "SEND_PAYMENT_REMINDER",
            "APPROVE_PURCHASE_ORDER",
            "ALLOCATE_STOCK",
            "CHECK_CREDIT_LIMIT",
            "CHECK_STOCK_AVAILABILITY",
            "RECOMMEND_ITEMS",
            "RECOMMEND_CUSTOMERS",
            "GET_CROSS_SELL",
            "GET_UPSELL",
            "GET_SEASONAL_RECOMMENDATIONS",
            "GET_TRENDING_PRODUCTS",
            "GET_TOP_SELLING_ITEMS",
            "GET_SLOW_MOVING_ITEMS",
            "GET_SALES_ANALYTICS",
            "ANALYZE_INVENTORY_HEALTH",
            "GET_REORDER_DECISIONS",
            "ANALYZE_PRICING_OPPORTUNITIES",
            "ANALYZE_CUSTOMER_BEHAVIOR",
            "FORECAST_DEMAND",
        }

        if intent in db_handled_intents:
            return True
        if intent in action_router_intents:
            return False

        return False

    def dispatch(
        self,
        intent: str,
        item: str,
        customer: str,
        warehouse: str,
        limit: int,
        language: str = "en"
    ) -> Optional[List[Dict]]:
        """
        Route intent to appropriate handler method.
        Returns None if no handler exists (caller should fall back to ActionRouter).
        """
        logger.info(f"Dispatching intent: {intent}")

        # =========================================================
        # Invoice Intents
        # =========================================================
        if intent == "GET_AR_INVOICES":
            return self._get_ar_invoices(customer, limit)

        if intent == "GET_AP_INVOICES":
            return self._get_ap_invoices(customer, limit)

        if intent == "GET_OVERDUE_INVOICES":
            return self._get_overdue_invoices(customer, limit)

        if intent == "GET_CUSTOMER_BALANCE":
            return self._get_customer_balance(customer)

        # =========================================================
        # Purchase Intents
        # =========================================================
        if intent == "GET_PURCHASE_ORDERS":
            return self._get_purchase_orders(customer, limit)

        if intent == "GET_PURCHASE_REQUESTS":
            return self._get_purchase_requests(limit)

        if intent == "GET_GOODS_RECEIPT_PO":
            return self._get_goods_receipt(customer, limit)

        # =========================================================
        # Inventory Intents
        # =========================================================
        if intent == "GET_INVENTORY_VALUATION":
            return self._get_inventory_valuation()

        if intent == "GET_REORDER_REPORT":
            return self._get_reorder_report(limit)

        # =========================================================
        # Customer Intents
        # =========================================================
        if intent == "GET_CUSTOMERS":
            return self._get_customers(customer, limit)

        if intent == "GET_CUSTOMER_DETAILS":
            return self._get_customer_details(customer)

        if intent == "GET_CUSTOMER_ORDERS":
            return self._get_customer_orders(customer, limit)

        if intent == "GET_CUSTOMER_INVOICES":
            return self._get_customer_invoices(customer, limit)

        if intent == "GET_OUTSTANDING_INVOICES":
            return self._get_customer_invoices(customer, limit, only_outstanding=True)

        if intent == "GET_CUSTOMER_HEALTH":
            return self._get_customer_health(customer)

        # =========================================================
        # Delivery Intents
        # =========================================================
        if intent == "GET_OUTSTANDING_DELIVERIES":
            return self._get_outstanding_deliveries(customer, limit)

        if intent == "TRACK_DELIVERY":
            return self._track_delivery(item)

        if intent == "GET_DELIVERY_HISTORY":
            return self._get_delivery_history(customer, limit)

        # =========================================================
        # Item/Stock Intents
        # =========================================================
        if intent == "GET_ITEMS":
            return self._get_items(item, limit)

        if intent == "GET_SELLABLE_ITEMS":
            return self._get_sellable_items(item, limit)

        if intent == "GET_PURCHASABLE_ITEMS":
            return self._get_purchasable_items(item, limit)

        if intent == "GET_INVENTORY_ITEMS":
            return self._get_inventory_items(item, limit)

        if intent == "GET_ITEM_DETAILS":
            return self._get_item_details(item)

        if intent == "GET_STOCK_LEVELS":
            return self._get_stock_levels(item, limit)

        if intent == "GET_WAREHOUSES":
            return self._get_warehouses()

        if intent == "GET_WAREHOUSE_STOCK":
            return self._get_warehouse_stock(warehouse, limit)

        if intent == "GET_LOW_STOCK_ALERTS":
            return self._get_low_stock_alerts(warehouse, limit)

        # =========================================================
        # Price Intents
        # =========================================================
        if intent == "GET_ITEM_PRICE":
            return self._get_item_price(item)

        if intent == "GET_CUSTOMER_PRICE":
            return self._get_customer_price(item, customer)

        # =========================================================
        # Unknown
        # =========================================================
        logger.warning(f"No optimized dispatch for intent: {intent}")
        return None

    # =========================================================
    # Invoice Handlers
    # FIX: replaced self.service.api.get(...) with direct session
    # calls matching the pattern used throughout OrdersHandler.
    # LeyscoAPIService has no generic .get() method — all HTTP
    # requests must go through self.service.api.session directly.
    # =========================================================

    def _get_ar_invoices(self, customer_code: str = None, limit: int = 50) -> List[Dict]:
        """Get A/R invoices (SAP doc type 13)"""
        try:
            if not self.service.api.auth_handler.ensure_auth():
                return []

            url = f"{self.service.api.base_url}/marketing/docs/13"
            params = {"page": 1, "per_page": limit}
            if customer_code:
                params["CardCode"] = customer_code

            self.service.api._record_api_call()
            resp = self.service.api.session.get(url, params=params, timeout=30)

            if resp.status_code != 200:
                logger.error(f"AR invoices API error: {resp.status_code}")
                return []

            data = resp.json()
            result = data.get("ResponseData", {})
            if isinstance(result, dict):
                return result.get("data", [])
            if isinstance(result, list):
                return result
            return []

        except Exception as e:
            logger.error(f"Failed to get AR invoices: {e}")
            return []

    def _get_ap_invoices(self, vendor_code: str = None, limit: int = 50) -> List[Dict]:
        """Get A/P invoices (SAP doc type 18)"""
        try:
            if not self.service.api.auth_handler.ensure_auth():
                return []

            url = f"{self.service.api.base_url}/purchase/invoices/18"
            params = {"page": 1, "per_page": limit}
            if vendor_code:
                params["CardCode"] = vendor_code

            self.service.api._record_api_call()
            resp = self.service.api.session.get(url, params=params, timeout=30)

            if resp.status_code != 200:
                logger.error(f"AP invoices API error: {resp.status_code}")
                return []

            data = resp.json()
            result = data.get("ResponseData", {})
            if isinstance(result, dict):
                return result.get("data", [])
            if isinstance(result, list):
                return result
            return []

        except Exception as e:
            logger.error(f"Failed to get AP invoices: {e}")
            return []

    def _get_overdue_invoices(self, customer_code: str = None, limit: int = 50) -> List[Dict]:
        """Get overdue A/R invoices by filtering on due date"""
        from datetime import datetime

        invoices = self._get_ar_invoices(customer_code, limit)
        overdue = []
        today = datetime.now().date()

        for inv in invoices:
            due_date_str = inv.get("DocDueDate", "")
            if due_date_str:
                try:
                    due_date = datetime.strptime(due_date_str[:10], "%Y-%m-%d").date()
                    if due_date < today:
                        inv["days_overdue"] = (today - due_date).days
                        overdue.append(inv)
                except Exception:
                    pass

        return sorted(overdue, key=lambda x: x.get("days_overdue", 0), reverse=True)

    def _get_customer_balance(self, customer_code: str) -> List[Dict]:
        """Get customer outstanding balance from open A/R invoices"""
        invoices = self._get_ar_invoices(customer_code)
        open_invoices = [inv for inv in invoices if inv.get("DocStatus") != "C"]
        total_balance = sum(float(inv.get("DocTotal", 0)) for inv in open_invoices)

        return [{
            "customer_code": customer_code,
            "open_invoice_count": len(open_invoices),
            "total_balance": total_balance,
            "currency": "KES",
            "invoices": open_invoices,
        }]

    # =========================================================
    # Purchase Handlers
    # FIX: same pattern — direct session calls, no .get() on api.
    # =========================================================

    def _get_purchase_orders(self, vendor_code: str = None, limit: int = 50) -> List[Dict]:
        """Get purchase orders (SAP doc type 22)"""
        try:
            if not self.service.api.auth_handler.ensure_auth():
                return []

            url = f"{self.service.api.base_url}/purchase/orders/22"
            params = {"page": 1, "per_page": limit}
            if vendor_code:
                params["CardCode"] = vendor_code

            self.service.api._record_api_call()
            resp = self.service.api.session.get(url, params=params, timeout=30)

            if resp.status_code != 200:
                logger.error(f"Purchase orders API error: {resp.status_code}")
                return []

            data = resp.json()
            result = data.get("ResponseData", {})
            if isinstance(result, dict):
                return result.get("data", [])
            if isinstance(result, list):
                return result
            return []

        except Exception as e:
            logger.error(f"Failed to get purchase orders: {e}")
            return []

    def _get_purchase_requests(self, limit: int = 50) -> List[Dict]:
        """Get purchase requests"""
        try:
            if not self.service.api.auth_handler.ensure_auth():
                return []

            url = f"{self.service.api.base_url}/purchase/requests"
            params = {"page": 1, "per_page": limit}

            self.service.api._record_api_call()
            resp = self.service.api.session.get(url, params=params, timeout=30)

            if resp.status_code != 200:
                logger.error(f"Purchase requests API error: {resp.status_code}")
                return []

            data = resp.json()
            result = data.get("ResponseData", {})
            if isinstance(result, dict):
                return result.get("data", [])
            if isinstance(result, list):
                return result
            return []

        except Exception as e:
            logger.error(f"Failed to get purchase requests: {e}")
            return []

    def _get_goods_receipt(self, po_num: str = None, limit: int = 50) -> List[Dict]:
        """Get goods receipt POs (SAP doc type 20)"""
        try:
            if not self.service.api.auth_handler.ensure_auth():
                return []

            url = f"{self.service.api.base_url}/purchase/goods-receipt/20"
            params = {"page": 1, "per_page": limit}
            if po_num:
                params["po_num"] = po_num

            self.service.api._record_api_call()
            resp = self.service.api.session.get(url, params=params, timeout=30)

            if resp.status_code != 200:
                logger.error(f"Goods receipt API error: {resp.status_code}")
                return []

            data = resp.json()
            result = data.get("ResponseData", {})
            if isinstance(result, dict):
                return result.get("data", [])
            if isinstance(result, list):
                return result
            return []

        except Exception as e:
            logger.error(f"Failed to get goods receipts: {e}")
            return []

    # =========================================================
    # Inventory Valuation & Reorder
    # =========================================================

    def _get_inventory_valuation(self) -> List[Dict]:
        """Get inventory valuation report"""
        try:
            inventory = self.service._safe_api_call(self.service.api.get_inventory_report, limit=200)

            total_value = 0
            items = []
            for item in inventory:
                on_hand = float(item.get("CurrentOnHand", 0))
                price = float(item.get("AvgPrice", 0)) or float(item.get("LastPrice", 0))
                value = on_hand * price
                total_value += value
                items.append({
                    "ItemCode": item.get("ItemCode"),
                    "ItemName": item.get("ItemName"),
                    "OnHand": on_hand,
                    "AvgPrice": price,
                    "Value": value,
                })

            return [{
                "total_value": total_value,
                "item_count": len(items),
                "items": sorted(items, key=lambda x: x["Value"], reverse=True)[:50],
            }]

        except Exception as e:
            logger.error(f"Failed to get inventory valuation: {e}")
            return []

    def _get_reorder_report(self, limit: int = 50) -> List[Dict]:
        """Get items that need reordering"""
        try:
            inventory = self.service._safe_api_call(self.service.api.get_inventory_report, limit=200)

            reorder_items = []
            for item in inventory:
                on_hand = float(item.get("CurrentOnHand", 0))
                min_stock = float(item.get("MinStock", 0)) or 10

                if 0 < on_hand <= min_stock:
                    reorder_items.append({
                        "ItemCode": item.get("ItemCode"),
                        "ItemName": item.get("ItemName"),
                        "OnHand": on_hand,
                        "ReorderPoint": min_stock,
                        "Shortfall": min_stock - on_hand,
                        "Warehouse": item.get("WhsCode"),
                    })

            return sorted(reorder_items, key=lambda x: x["Shortfall"], reverse=True)[:limit]

        except Exception as e:
            logger.error(f"Failed to get reorder report: {e}")
            return []

    # =========================================================
    # Customer Handlers
    # =========================================================

    def _get_customers(self, search: str, limit: int) -> List[Dict]:
        return self.service.api.get_customers(search=search, limit=limit)

    def _get_customer_details(self, customer_name: str) -> List[Dict]:
        customer = self.service.api.resolve_customer(customer_name)
        return [customer] if customer else []

    def _get_customer_orders(self, customer_name: str, limit: int) -> List[Dict]:
        customer = self.service.api.resolve_customer(customer_name)
        if not customer:
            return []
        return self.service.api.get_customer_orders(
            customer_code=customer.get("CardCode"), limit=limit
        )

    def _get_customer_invoices(
        self, customer_name: str, limit: int, only_outstanding: bool = False
    ) -> List[Dict]:
        customer = self.service.api.resolve_customer(customer_name)
        if not customer:
            return []

        invoices = self._get_ar_invoices(customer.get("CardCode"), limit)

        if only_outstanding:
            invoices = [inv for inv in invoices if inv.get("DocStatus") != "C"]

        return invoices

    def _get_customer_health(self, customer_name: str) -> List[Dict]:
        from app.services.customer_health_service import create_customer_health_service

        health_service = create_customer_health_service(
            user_token=self.service.user_token,
            company_code=self.service.company_code,
        )
        result = health_service.score(customer_name=customer_name)
        return [result] if not result.get("error") else []

    # =========================================================
    # Delivery Handlers
    # =========================================================

    def _get_outstanding_deliveries(self, customer_name: str, limit: int) -> List[Dict]:
        if customer_name:
            customer = self.service.api.resolve_customer(customer_name)
            if customer:
                return self.service.api.get_outstanding_deliveries(
                    customer_code=customer.get("CardCode"), limit=limit
                )
        return self.service.api.get_outstanding_deliveries(limit=limit)

    def _track_delivery(self, delivery_num: str) -> List[Dict]:
        if not delivery_num:
            return []
        return self.service.api.get_delivery_details(delivery_num) or []

    def _get_delivery_history(self, customer_name: str, limit: int) -> List[Dict]:
        if customer_name:
            customer = self.service.api.resolve_customer(customer_name)
            if customer:
                return self.service.api.get_delivery_history(
                    customer_code=customer.get("CardCode"), limit=limit
                )
        return []

    # =========================================================
    # Item/Stock Handlers
    # =========================================================

    def _get_items(self, search: str, limit: int) -> List[Dict]:
        return self.service.api.get_items(search=search, limit=limit)

    def _get_sellable_items(self, search: str, limit: int) -> List[Dict]:
        items = self.service.api.get_items(search=search, limit=limit)
        return [i for i in items if i.get("SellItem") == "Y"]

    def _get_purchasable_items(self, search: str, limit: int) -> List[Dict]:
        items = self.service.api.get_items(search=search, limit=limit)
        return [i for i in items if i.get("PurchaseItem") == "Y"]

    def _get_inventory_items(self, search: str, limit: int) -> List[Dict]:
        return self.service._safe_api_call(
            self.service.api.get_inventory_report, search=search, limit=limit
        )

    def _get_item_details(self, item_code: str) -> List[Dict]:
        item = self.service.api.get_item_by_code(item_code)
        return [item] if item else []

    def _get_stock_levels(self, item_name: str, limit: int) -> List[Dict]:
        return self.service._safe_api_call(
            self.service.api.get_inventory_report, search=item_name, limit=limit
        )

    def _get_warehouses(self) -> List[Dict]:
        return self.service.warehouse_service.get_warehouses()

    def _get_warehouse_stock(self, warehouse_name: str, limit: int) -> List[Dict]:
        return self.service.warehouse_service.get_warehouse_stock(warehouse_name)

    def _get_low_stock_alerts(self, warehouse_name: str, limit: int) -> List[Dict]:
        return self.service.warehouse_service.get_low_stock_alerts(warehouse_name)

    # =========================================================
    # Price Handlers
    # =========================================================

    def _get_item_price(self, item_name: str) -> List[Dict]:
        result = self.service.resolve_and_price(item_name=item_name)
        return result if isinstance(result, list) else []

    def _get_customer_price(self, item_name: str, customer_name: str) -> List[Dict]:
        result = self.service.resolve_and_price(
            item_name=item_name, customer_name=customer_name
        )
        return result if isinstance(result, list) else []