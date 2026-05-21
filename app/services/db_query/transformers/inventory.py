"""Inventory health data transformer"""

from typing import List, Dict, Optional
from .base import BaseTransformer


class InventoryTransformer(BaseTransformer):
    """Transforms inventory data into health analysis format"""
    
    @classmethod
    def transform_health(cls, inventory_data: List[Dict], turnover_data: Optional[List] = None,
                         slow_products: Optional[List] = None) -> List[Dict]:
        """Transform inventory data into comprehensive health analysis"""
        inventory = inventory_data if inventory_data else []
        turnover = turnover_data if turnover_data else []
        slow = slow_products if slow_products else []
        
        if not inventory:
            return [{
                "analysis_type": "inventory_health",
                "error": True,
                "message": "Unable to fetch inventory data at this time.",
                "suggestions": ["Try again in a few minutes", "Check a specific item instead"]
            }]
        
        total_items = len(inventory)
        total_value = 0
        out_of_stock_count = 0
        critical_count = 0
        low_count = 0
        healthy_count = 0
        overstock_count = 0
        
        analyzed_items = []
        total_on_hand = 0
        total_committed = 0
        
        for inv in inventory[:500]:
            on_hand = cls.safe_float(inv.get("CurrentOnHand", inv.get("OnHand", 0)))
            committed = cls.safe_float(inv.get("CurrentIsCommited", inv.get("IsCommited", 0)))
            available = on_hand - committed
            
            total_on_hand += on_hand
            total_committed += committed
            
            # Estimate value
            price = cls.safe_float(inv.get("Price", 0))
            if price <= 0:
                price = 500 if "VEG" in inv.get("ItemCode", "") else 100
            item_value = on_hand * price
            total_value += item_value
            
            # Stock status classification
            if on_hand == 0:
                out_of_stock_count += 1
                status = "OUT OF STOCK"
                severity = "critical"
            elif available < 5:
                critical_count += 1
                status = "CRITICAL"
                severity = "critical"
            elif available < 20:
                low_count += 1
                status = "LOW"
                severity = "warning"
            elif available < 100:
                healthy_count += 1
                status = "HEALTHY"
                severity = "good"
            else:
                overstock_count += 1
                status = "OVERSTOCK"
                severity = "warning"
            
            # Collect critical and low items
            if available < 20 and len(analyzed_items) < 15:
                analyzed_items.append({
                    "ItemCode": inv.get("ItemCode"),
                    "ItemName": inv.get("ItemName"),
                    "OnHand": round(on_hand, 1),
                    "Committed": round(committed, 1),
                    "Available": round(available, 1),
                    "Status": status,
                    "Severity": severity
                })
        
        # Calculate health score
        out_of_stock_penalty = min(50, (out_of_stock_count / max(total_items, 1)) * 100)
        low_stock_penalty = min(30, (low_count / max(total_items, 1)) * 60)
        overstock_penalty = min(20, (overstock_count / max(total_items, 1)) * 40)
        
        health_score = max(0, 100 - (out_of_stock_penalty + low_stock_penalty + overstock_penalty))
        
        # Sort analyzed items
        severity_order = {"critical": 0, "warning": 1, "good": 2}
        analyzed_items.sort(key=lambda x: (severity_order.get(x.get("Severity", "good"), 3), x.get("Available", 999)))
        
        # Generate recommendations
        recommendations = []
        if out_of_stock_count > 0:
            recommendations.append(f"{out_of_stock_count} items are out of stock - Review reorder points and supplier lead times")
        if critical_count > 0:
            recommendations.append(f"{critical_count} items are critically low (<5 units available) - Immediate reorder required")
        if low_count > 0:
            recommendations.append(f"{low_count} items are running low (<20 units available) - Schedule replenishment soon")
        if overstock_count > 0:
            recommendations.append(f"{overstock_count} items have excess stock (>100 units) - Consider promotions or markdowns")
        
        if not recommendations:
            recommendations.append("Inventory levels are well balanced - Continue monitoring")
        
        # Determine health status
        if health_score < 40:
            health_status = "Critical"
        elif health_score < 60:
            health_status = "Poor"
        elif health_score < 80:
            health_status = "Fair"
        else:
            health_status = "Good"
        
        result = {
            "analysis_type": "inventory_health",
            "health_score": round(health_score, 1),
            "health_status": health_status,
            "summary": {
                "total_items": total_items,
                "total_value": round(total_value, 2),
                "total_on_hand": round(total_on_hand, 1),
                "total_committed": round(total_committed, 1),
                "total_available": round(total_on_hand - total_committed, 1),
                "out_of_stock": out_of_stock_count,
                "critical_items": critical_count,
                "low_items": low_count,
                "healthy_items": healthy_count,
                "overstock_items": overstock_count
            },
            "critical_samples": analyzed_items[:10],
            "recommendations": recommendations,
            "note": f"Analyzed {min(500, total_items)} items. Health score based on stock availability and balance."
        }
        
        if turnover:
            result["turnover_available"] = True
        
        if slow:
            result["slow_movers"] = [
                {"code": item.get("ItemCode", ""), "name": item.get("ItemName", ""), "turnover": item.get("TurnoverRate", 0)}
                for item in slow[:3]
            ]
        
        return [result]