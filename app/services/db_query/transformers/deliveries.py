"""Delivery data transformer"""

from typing import List, Dict
from datetime import datetime
from .base import BaseTransformer


class DeliveryTransformer(BaseTransformer):
    """Transforms raw delivery data into clean format"""
    
    @classmethod
    def transform(cls, raw_deliveries: List[Dict], max_items: int = 15) -> List[Dict]:
        """Transform delivery/order data with proper status extraction"""
        if not raw_deliveries:
            return []
        
        transformed = []
        total_value = 0
        overdue_count = 0
        
        for delivery in raw_deliveries[:max_items]:
            if isinstance(delivery, dict):
                # Extract basic fields
                doc_num = delivery.get("DocNum", delivery.get("doc_num", "N/A"))
                doc_date = delivery.get("DocDate", delivery.get("doc_date", ""))
                doc_due_date = delivery.get("DocDueDate", delivery.get("doc_due_date", ""))
                customer_name = delivery.get("CardName", delivery.get("customer_name", "Unknown"))
                customer_code = delivery.get("CardCode", delivery.get("customer_code", ""))
                
                # Normalize status
                status = cls._normalize_status(delivery.get("Status", delivery.get("status", "Open")))
                
                # Check if overdue
                is_overdue = cls._check_if_overdue(doc_due_date, status)
                if is_overdue:
                    overdue_count += 1
                    status = "Overdue"
                
                # Extract quantities
                open_qty = cls.safe_float(delivery.get("OpenQty", delivery.get("open_qty", 0)))
                quantity = cls.safe_float(delivery.get("Quantity", delivery.get("quantity", open_qty)))
                price = cls.safe_float(delivery.get("Price", delivery.get("price", 0)))
                
                # Calculate total value
                total_value_item = open_qty * price if open_qty and price else cls.safe_float(delivery.get("total_value", delivery.get("DocTotal", 0)))
                total_value += total_value_item
                
                delivery_item = {
                    "doc_num": cls.safe_str(doc_num),
                    "doc_date": doc_date[:10] if doc_date else "",
                    "doc_due_date": doc_due_date[:10] if doc_due_date else "",
                    "customer_name": customer_name,
                    "customer_code": customer_code,
                    "status": status,
                    "total_quantity": quantity,
                    "delivered_quantity": 0,
                    "pending_quantity": open_qty,
                    "completion_percentage": 0,
                    "item_count": 1,
                    "total_value": round(total_value_item, 2),
                    "is_completed_today": False,
                    "is_overdue": is_overdue,
                    "item_code": delivery.get("ItemCode", delivery.get("item_code", "")),
                    "item_name": delivery.get("ItemName", delivery.get("item_name", "")),
                    "price": round(price, 2)
                }
                
                # Calculate completion percentage if we have delivered quantity
                delivered = cls.safe_float(delivery.get("DeliveredQty", delivery.get("delivered_qty", 0)))
                if delivered and open_qty:
                    total = delivered + open_qty
                    if total > 0:
                        delivery_item["completion_percentage"] = round((delivered / total) * 100, 1)
                        delivery_item["delivered_quantity"] = delivered
                
                # Add items list if there are multiple items
                items = delivery.get("items", delivery.get("DocumentLines", []))
                if items and len(items) > 0:
                    delivery_item["items"] = []
                    delivery_item["item_count"] = len(items)
                    for item in items[:5]:
                        if isinstance(item, dict):
                            delivery_item["items"].append({
                                "item_code": item.get("ItemCode", item.get("item_code", "")),
                                "item_name": item.get("ItemName", item.get("item_name", "")),
                                "quantity": cls.safe_float(item.get("Quantity", item.get("quantity", 0))),
                                "delivered": cls.safe_float(item.get("DeliveredQty", item.get("delivered", 0))),
                                "pending": cls.safe_float(item.get("OpenQty", item.get("open_qty", 0)))
                            })
                
                transformed.append(delivery_item)
        
        # Add summary if truncated
        if len(raw_deliveries) > max_items:
            transformed.append({
                "_summary": True,
                "total": len(raw_deliveries),
                "displayed": max_items,
                "total_value": round(total_value, 2),
                "overdue_count": overdue_count,
                "message": f"Showing {max_items} of {len(raw_deliveries)} deliveries."
            })
        
        return transformed
    
    @classmethod
    def _normalize_status(cls, status: str) -> str:
        """Normalize status for consistent display"""
        if not status:
            return "Open"
        
        status_lower = status.lower()
        status_map = {
            "open": "Open",
            "overdue": "Overdue",
            "partial": "Partially Delivered",
            "partially delivered": "Partially Delivered",
            "completed": "Completed",
            "delivered": "Completed",
            "pending": "Pending",
            "cancelled": "Cancelled",
            "in transit": "In Transit",
            "in_transit": "In Transit"
        }
        
        return status_map.get(status_lower, status)
    
    @classmethod
    def _check_if_overdue(cls, due_date: str, status: str) -> bool:
        """Check if a delivery is overdue"""
        if not due_date or status == "Completed":
            return False
        try:
            due = datetime.strptime(str(due_date)[:10], "%Y-%m-%d")
            return due < datetime.now()
        except:
            return False