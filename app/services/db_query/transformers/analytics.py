"""Sales analytics data transformer"""

from typing import List, Dict
from .base import BaseTransformer


class AnalyticsTransformer(BaseTransformer):
    """Transforms sales analytics data into clean format"""
    
    @classmethod
    def transform(cls, raw_data: List[Dict], period: str = "last_30_days") -> List[Dict]:
        """Transform sales analytics data for LLM narration"""
        if not raw_data:
            from ..fallback import get_fallback_sales_analytics
            return get_fallback_sales_analytics()
        
        # If data is already transformed, return as is
        if cls._is_already_transformed(raw_data):
            return raw_data
        
        # Check if data has expected structure
        if isinstance(raw_data, list) and len(raw_data) > 0:
            first_item = raw_data[0]
            if "summary" in first_item and "top_products" in first_item:
                return raw_data
        
        # Calculate aggregates from raw data
        total_revenue = 0
        total_transactions = 0
        unique_customers = set()
        total_items_sold = 0
        product_sales = {}
        
        for sale in raw_data:
            try:
                revenue = cls.safe_float(sale.get("total_amount", sale.get("DocTotal", 0)))
                total_revenue += revenue
                total_transactions += 1
                
                customer_id = sale.get("customer_id") or sale.get("CardCode")
                if customer_id:
                    unique_customers.add(customer_id)
                
                quantity = cls.safe_float(sale.get("quantity", sale.get("Quantity", 0)))
                total_items_sold += quantity
                
                # Aggregate product sales
                product_name = sale.get("item_name", sale.get("ItemName", "Unknown"))
                if product_name:
                    if product_name not in product_sales:
                        product_sales[product_name] = {"quantity": 0, "revenue": 0}
                    product_sales[product_name]["quantity"] += quantity
                    product_sales[product_name]["revenue"] += revenue
                    
            except (ValueError, TypeError):
                continue
        
        avg_order_value = total_revenue / total_transactions if total_transactions > 0 else 0
        
        # Get top products
        top_products = []
        for product, data in sorted(product_sales.items(), key=lambda x: x[1]["revenue"], reverse=True)[:5]:
            top_products.append({
                "name": product,
                "quantity": int(data["quantity"]),
                "revenue": round(data["revenue"], 2)
            })
        
        result = [{
            "analysis_type": "sales_analytics",
            "period": period,
            "summary": {
                "total_revenue": round(total_revenue, 2),
                "total_transactions": total_transactions,
                "average_order_value": round(avg_order_value, 2),
                "unique_customers": len(unique_customers),
                "total_items_sold": int(total_items_sold)
            },
            "top_products": top_products,
            "data_points": len(raw_data),
            "note": f"Sales data for the {period.replace('_', ' ')}"
        }]
        
        return result
    
    @classmethod
    def transform_summary(cls, raw_data: List[Dict], period: str = "last_30_days") -> List[Dict]:
        """Transform sales analytics into summary format (faster, fewer details)"""
        if not raw_data:
            from ..fallback import get_fallback_sales_analytics
            return get_fallback_sales_analytics()
        
        if cls._is_already_transformed(raw_data):
            return raw_data
        
        total_revenue = 0
        total_transactions = 0
        for sale in raw_data:
            try:
                total_revenue += cls.safe_float(sale.get("total_amount", sale.get("DocTotal", 0)))
                total_transactions += 1
            except (ValueError, TypeError):
                continue
        
        avg_order = total_revenue / total_transactions if total_transactions > 0 else 0
        
        return [{
            "analysis_type": "sales_analytics_summary",
            "period": period,
            "total_revenue": round(total_revenue, 2),
            "total_transactions": total_transactions,
            "average_order_value": round(avg_order, 2),
            "data_points": len(raw_data)
        }]
    
    @classmethod
    def _is_already_transformed(cls, data: list) -> bool:
        """Check if data is already transformed"""
        if not data or not isinstance(data, list):
            return False
        first_item = data[0]
        if not isinstance(first_item, dict):
            return False
        return "summary" in first_item and "top_products" in first_item