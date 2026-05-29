"""
Proactive Insights Engine - Surfaces contextual intelligence
Suggests actions based on data patterns and business rules
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from app.services.sap_document_service import SAPDocumentService, create_sap_document_service
from app.services.business_rules import BusinessRulesEngine, create_business_rules_engine

logger = logging.getLogger(__name__)


class ProactiveInsightsEngine:
    """
    Provides proactive intelligence based on data analysis:
    - Overdue invoice alerts
    - Low stock warnings
    - Follow-up suggestions
    - Seasonal trends
    """
    
    def __init__(self, user_token: str = None, company_code: str = None):
        self.user_token = user_token
        self.company_code = company_code
        self.sap_docs = create_sap_document_service(user_token, company_code)
        self.rules = create_business_rules_engine(user_token, company_code)
    
    def get_insights_for_customer(self, customer_code: str, customer_name: str = None) -> List[str]:
        """
        Get proactive insights for a specific customer
        """
        insights = []
        
        # Check overdue invoices
        overdue = self.sap_docs.get_overdue_invoices(customer_code, days_overdue=1)
        if overdue:
            total_overdue = sum(inv.get("DocTotal", 0) for inv in overdue)
            count = len(overdue)
            insights.append(f"🔴 Customer has {count} overdue invoice(s) totaling KES {total_overdue:,.2f}")
        
        # Check open quotations
        quotations = self.sap_docs.get_quotations(customer_code=customer_code, status="open")
        if quotations:
            old_quotes = [q for q in quotations if self._is_older_than_days(q, 7)]
            if old_quotes:
                insights.append(f"📋 {len(old_quotes)} quotation(s) older than 7 days pending follow-up")
        
        # Check recent order activity
        orders = self.sap_docs.get_sales_orders(customer_code=customer_code, limit=5)
        if orders:
            last_order = orders[0]
            order_date = last_order.get("DocDate", "")
            if order_date:
                days_since = (datetime.now() - datetime.strptime(order_date[:10], "%Y-%m-%d")).days
                if days_since > 30:
                    insights.append(f"📦 No orders in {days_since} days - re-engagement opportunity")
        
        return insights
    
    def get_insights_for_item(self, item_code: str, item_name: str = None) -> List[str]:
        """
        Get proactive insights for a specific item
        """
        insights = []
        
        # Check stock level
        stock_check = self.rules.check_stock_availability([{"ItemCode": item_code, "Quantity": 1}])
        if stock_check and not stock_check[0].passed:
            insights.append(f"⚠️ {item_code} is out of stock or low")
        elif stock_check and stock_check[0].data:
            available = stock_check[0].data.get("available", 0)
            on_hand = stock_check[0].data.get("on_hand", 0)
            if available < on_hand * 0.1 and on_hand > 0:
                insights.append(f"📊 {item_code} stock is critically low ({available} units available)")
        
        # Check if trending (based on recent orders)
        recent_orders = self._get_recent_orders_for_item(item_code, days=30)
        if len(recent_orders) > 10:
            insights.append(f"🔥 {item_code} is trending - 30 day period")
        
        return insights
    
    def get_insights_for_warehouse(self, warehouse_code: str) -> List[str]:
        """
        Get proactive insights for a warehouse
        """
        insights = []
        
        # Check low stock items
        low_stock = self._get_low_stock_items(warehouse_code, threshold=10)
        if low_stock:
            insights.append(f"⚠️ Warehouse {warehouse_code} has {len(low_stock)} items with low stock (<10 units)")
        
        # Check slow movers
        slow_movers = self._get_slow_moving_items(warehouse_code, days=90)
        if slow_movers:
            insights.append(f"📊 {len(slow_movers)} items in {warehouse_code} haven't moved in 90 days")
        
        return insights
    
    def get_insights_for_document(self, doc_type: str, doc_num: str) -> List[str]:
        """
        Get proactive insights for a specific document
        """
        insights = []
        
        if doc_type == "quotation":
            quote = self.sap_docs.get_quotation(doc_num)
            if quote:
                days_old = self._get_days_old(quote.get("DocDate", ""))
                if days_old > 7:
                    insights.append(f"⏰ Quotation {doc_num} is {days_old} days old - consider follow-up")
        
        elif doc_type == "sales_order":
            order = self.sap_docs.get_sales_order(doc_num)
            if order:
                # Check if delivery is due
                due_date = order.get("DocDueDate", "")
                if due_date:
                    days_to_due = (datetime.strptime(due_date[:10], "%Y-%m-%d") - datetime.now()).days
                    if 0 <= days_to_due <= 3:
                        insights.append(f"🚚 Order {doc_num} delivery due in {days_to_due} days")
                    elif days_to_due < 0:
                        insights.append(f"⚠️ Order {doc_num} delivery is overdue by {abs(days_to_due)} days")
        
        elif doc_type == "ar_invoice":
            invoice = self.sap_docs.get_ar_invoice(doc_num)
            if invoice:
                due_date = invoice.get("DocDueDate", "")
                if due_date:
                    days_overdue = (datetime.now() - datetime.strptime(due_date[:10], "%Y-%m-%d")).days
                    if days_overdue > 0:
                        insights.append(f"💰 Invoice {doc_num} is {days_overdue} days overdue")
        
        return insights
    
    # =========================================================
    # PRIVATE METHODS
    # =========================================================
    
    def _is_older_than_days(self, doc: Dict, days: int) -> bool:
        doc_date = doc.get("DocDate", "")
        if not doc_date:
            return False
        try:
            doc_datetime = datetime.strptime(doc_date[:10], "%Y-%m-%d")
            return (datetime.now() - doc_datetime).days > days
        except:
            return False
    
    def _get_days_old(self, date_str: str) -> int:
        if not date_str:
            return 0
        try:
            doc_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
            return (datetime.now() - doc_date).days
        except:
            return 0
    
    def _get_recent_orders_for_item(self, item_code: str, days: int = 30) -> List:
        """Get recent orders containing this item"""
        cutoff = datetime.now() - timedelta(days=days)
        orders = self.sap_docs.get_sales_orders(limit=50)
        recent = []
        for order in orders:
            order_date_str = order.get("DocDate", "")
            if order_date_str:
                try:
                    order_date = datetime.strptime(order_date_str[:10], "%Y-%m-%d")
                    if order_date >= cutoff:
                        lines = order.get("DocumentLines", [])
                        if any(line.get("ItemCode") == item_code for line in lines):
                            recent.append(order)
                except:
                    pass
        return recent
    
    def _get_low_stock_items(self, warehouse: str, threshold: int = 10) -> List:
        """Get items with stock below threshold"""
        try:
            inventory = self.sap_docs.api.get_inventory_report()
            low = []
            for item in inventory:
                if warehouse and item.get("WhsCode") != warehouse:
                    continue
                on_hand = float(item.get("CurrentOnHand", 0))
                if 0 < on_hand <= threshold:
                    low.append({
                        "ItemCode": item.get("ItemCode"),
                        "ItemName": item.get("ItemName"),
                        "OnHand": on_hand
                    })
            return low
        except:
            return []
    
    def _get_slow_moving_items(self, warehouse: str, days: int = 90) -> List:
        """Get items that haven't moved in N days"""
        # This would require movement history - placeholder for now
        return []


def create_proactive_insights_engine(user_token: str = None, company_code: str = None) -> ProactiveInsightsEngine:
    """Factory function for ProactiveInsightsEngine"""
    return ProactiveInsightsEngine(user_token=user_token, company_code=company_code)