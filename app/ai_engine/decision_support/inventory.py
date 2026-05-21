"""Inventory health and reorder decision support"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta  # Add timedelta here

from .constants import THRESHOLDS, STOCK_STATUS, CACHE_TTL
from .utils import (
    mean, std_dev, sqrt, confidence_score, calculate_days_of_stock,
    get_stock_recommendation, get_health_rating, safe_float
)
from .cache import cached

logger = logging.getLogger(__name__)


class InventoryAnalyzer:
    """Handles inventory health analysis and reorder decisions"""
    
    def __init__(self, parent):
        self.parent = parent
        self.api = parent.api
        self.pricing = parent.pricing
    
    @cached("inventory_health")
    def analyze_inventory_health(
        self,
        warehouse_code: Optional[str] = None,
        include_recommendations: bool = True,
        limit: int = 500
    ) -> Dict[str, Any]:
        """Comprehensive inventory health analysis with proper API field mapping."""
        logger.info(f"📊 Analyzing inventory health for {warehouse_code or 'all warehouses'}")

        try:
            # Get inventory data
            inventory = self.api.get_inventory_report(limit=limit)
            
            if not inventory:
                return {
                    "error": "No inventory data available",
                    "message": "Unable to fetch inventory data at this time. Please try again later.",
                    "recommendations": ["Check API connection", "Verify warehouse code"]
                }

            velocity_map = self._get_sales_velocity_data()
            
            # Batch fetch prices for all items
            item_codes = []
            for item in inventory:
                item_code = item.get("ItemCode") or item.get("item_code")
                if item_code:
                    item_codes.append(item_code)
            
            price_map = self._batch_get_prices(item_codes)

            analysis = {
                "summary": {},
                "critical_items": [],
                "overstock_items": [],
                "slow_movers": [],
                "fast_movers": [],
                "reorder_recommendations": [],
                "risk_items": [],
                "opportunity_items": [],
                "health_score": 0,
                "priority_actions": [],
            }

            total_value = 0.0
            total_items = 0
            critical_count = 0
            low_count = 0
            overstock_count = 0
            healthy_count = 0
            out_of_stock_count = 0

            for item in inventory:
                if warehouse_code and item.get("WhsCode") != warehouse_code:
                    continue

                item_code = item.get("ItemCode") or item.get("item_code", "")
                item_name = item.get("ItemName") or item.get("item_name", item_code)
                
                # API uses CurrentOnHand, not OnHand
                on_hand = safe_float(item.get("CurrentOnHand") or item.get("OnHand") or item.get("on_hand"))
                committed = safe_float(item.get("CurrentIsCommited") or item.get("IsCommited") or item.get("is_commited"))
                available = on_hand - committed
                
                # Get unit price from price map
                unit_price = price_map.get(item_code, 0)
                item_value = on_hand * unit_price

                total_value += item_value
                total_items += 1

                # Get sales velocity (daily average)
                velocity = velocity_map.get(item_code, 0.0)
                days_of_stock = calculate_days_of_stock(available, velocity)

                # Determine stock status
                if available <= 0:
                    stock_status = "OUT_OF_STOCK"
                    out_of_stock_count += 1
                elif days_of_stock != float('inf') and days_of_stock < THRESHOLDS["critical_stock_days"]:
                    stock_status = "CRITICAL"
                    critical_count += 1
                elif days_of_stock != float('inf') and days_of_stock < THRESHOLDS["low_stock_days"]:
                    stock_status = "LOW"
                    low_count += 1
                elif days_of_stock != float('inf') and days_of_stock > THRESHOLDS["max_stock_days"] and velocity > 0:
                    stock_status = "OVERSTOCK"
                    overstock_count += 1
                else:
                    stock_status = "HEALTHY"
                    healthy_count += 1

                # Build item info dictionary
                item_info = {
                    "code": item_code,
                    "name": item_name,
                    "available": round(available, 1),
                    "on_hand": round(on_hand, 1),
                    "committed": round(committed, 1),
                    "daily_avg": round(velocity, 2),
                    "value": round(item_value, 2),
                    "unit_price": round(unit_price, 2),
                    "warehouse": item.get("WhsCode") or item.get("whs_code", "Unknown")
                }
                
                # Add days_left if applicable
                if days_of_stock != float('inf'):
                    item_info["days_left"] = round(days_of_stock, 1)
                else:
                    item_info["days_left"] = "N/A"

                # Categorize items
                if stock_status == "CRITICAL":
                    item_info["action"] = "ORDER IMMEDIATELY"
                    analysis["critical_items"].append(item_info)
                elif stock_status == "LOW":
                    item_info["action"] = "ORDER SOON"
                    analysis["risk_items"].append(item_info)
                elif stock_status == "OVERSTOCK":
                    item_info["action"] = "Consider promotion or reduced ordering"
                    analysis["overstock_items"].append(item_info)
                elif stock_status == "OUT_OF_STOCK":
                    item_info["action"] = "URGENT: Restock immediately"
                    analysis["risk_items"].append(item_info)

                # Slow/fast movers based on sales velocity
                if velocity > 0:
                    if velocity < 0.1:  # Less than 1 unit per 10 days
                        analysis["slow_movers"].append(item_info)
                    elif velocity > 10:  # More than 10 units per day
                        analysis["fast_movers"].append(item_info)

                # Reorder recommendations
                if velocity > 0 and available < (velocity * 14):  # Less than 2 weeks of stock
                    reorder_point = velocity * THRESHOLDS["reorder_point_multiplier"] * 7
                    urgency = "HIGH" if available < reorder_point * 0.5 else "MEDIUM"
                    analysis["reorder_recommendations"].append({
                        "code": item_code,
                        "name": item_name,
                        "current": round(available, 1),
                        "reorder_at": round(reorder_point),
                        "recommended_qty": round(reorder_point * 2),
                        "urgency": urgency,
                        "daily_avg": round(velocity, 2),
                    })

            # Calculate health score
            total_analyzed = critical_count + low_count + healthy_count + overstock_count + out_of_stock_count
            if total_analyzed > 0:
                weighted_score = (
                    critical_count * 20 +
                    low_count * 40 +
                    healthy_count * 90 +
                    overstock_count * 50 +
                    out_of_stock_count * 0
                ) / total_analyzed
                analysis["health_score"] = min(100, max(0, int(weighted_score)))

            # Priority actions
            if out_of_stock_count > 0:
                analysis["priority_actions"].append({
                    "priority": "HIGHEST",
                    "action": f"🚨 URGENT: {out_of_stock_count} items are OUT OF STOCK",
                    "details": "These items have zero available stock and need immediate replenishment"
                })
            
            if critical_count > 0:
                analysis["priority_actions"].append({
                    "priority": "HIGHEST",
                    "action": f"ORDER IMMEDIATELY: {critical_count} items critically low",
                    "details": "These items will run out in < 3 days"
                })
            
            if low_count > 5:
                analysis["priority_actions"].append({
                    "priority": "HIGH",
                    "action": f"Review {low_count} low stock items",
                    "details": "Place orders within the week"
                })
            
            if overstock_count > 10:
                analysis["priority_actions"].append({
                    "priority": "MEDIUM",
                    "action": f"Review {overstock_count} overstocked items",
                    "details": "Consider promotions or returns"
                })

            # Get top items for summary
            top_critical = analysis["critical_items"][:5]
            top_reorders = analysis["reorder_recommendations"][:5]

            analysis["summary"] = {
                "total_items": total_items,
                "total_inventory_value": round(total_value, 2),
                "critical_items_count": critical_count,
                "low_items_count": low_count,
                "healthy_items_count": healthy_count,
                "overstock_items_count": overstock_count,
                "out_of_stock_count": out_of_stock_count,
                "slow_movers_count": len(analysis["slow_movers"]),
                "fast_movers_count": len(analysis["fast_movers"]),
                "reorder_recommendations_count": len(analysis["reorder_recommendations"]),
                "warehouse": warehouse_code or "All Warehouses",
                "health_rating": get_health_rating(analysis["health_score"]),
                "top_critical_items": [
                    {"name": item["name"], "available": item["available"], "days_left": item["days_left"]}
                    for item in top_critical
                ],
                "top_reorder_items": [
                    {"name": item["name"], "current": item["current"], "recommended": item["recommended_qty"]}
                    for item in top_reorders
                ]
            }

            return analysis
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Error in analyze_inventory_health: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Inventory analysis failed: {str(e)}"
            }
    
    @cached("reorder_decisions")
    def get_reorder_decisions(
        self,
        filter_item_code: Optional[str] = None,
        days_ahead: int = 14
    ) -> Dict[str, Any]:
        """Get reorder recommendations with optimal quantities."""
        
        try:
            inventory = self.api.get_inventory_report(limit=500)
            if not inventory:
                return {
                    "error": "No inventory data available",
                    "message": "Unable to fetch inventory data for reorder analysis"
                }
            
            velocity_map = self._get_sales_velocity_data()
            
            decisions = {
                "analysis_type": "reorder_decisions",
                "analysis_date": datetime.now().isoformat(),
                "planning_horizon_days": days_ahead,
                "immediate_orders": [],
                "planned_orders": [],
                "monitor_items": [],
                "optimal_quantities": {},
                "total_reorder_cost": 0,
                "priority_summary": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
                "recommendations": [],
                "reorder_by_warehouse": {},
            }

            for item in inventory:
                item_code = item.get("ItemCode", "")
                if filter_item_code and item_code != filter_item_code:
                    continue

                item_name = item.get("ItemName", item_code)
                warehouse = item.get("WhsCode", "Unknown")
                
                on_hand = safe_float(item.get("CurrentOnHand") or item.get("OnHand"))
                committed = safe_float(item.get("CurrentIsCommited") or item.get("IsCommited"))
                available = on_hand - committed

                velocity = velocity_map.get(item_code, 0.0)
                
                # Skip items with no sales data unless they have committed orders
                if velocity == 0 and committed == 0:
                    continue
                
                if velocity == 0 and committed > 0:
                    velocity = committed / 30
                
                unit_price = self._get_average_price(item_code)
                if unit_price <= 0:
                    unit_price = 100
                
                days_left = calculate_days_of_stock(available, velocity) if velocity > 0 else float('inf')
                
                if velocity > 0:
                    ordering_cost = 500.0
                    holding_cost = unit_price * 0.25
                    annual_demand = velocity * 365
                    
                    if holding_cost > 0:
                        eoq = sqrt((2 * annual_demand * ordering_cost) / holding_cost)
                    else:
                        eoq = velocity * 30
                    
                    recommended_qty = max(velocity * days_ahead, eoq)
                    
                    if recommended_qty < 10:
                        recommended_qty = round(recommended_qty)
                    else:
                        recommended_qty = round(recommended_qty / 10) * 10
                else:
                    recommended_qty = 0
                
                # Calculate urgency
                needs_reorder = False
                urgency = "NONE"
                urgency_reason = ""
                
                if available <= 0:
                    needs_reorder = True
                    urgency = "CRITICAL"
                    urgency_reason = f"Item is out of stock (0 units available)"
                elif days_left != float('inf') and days_left < 3:
                    needs_reorder = True
                    urgency = "CRITICAL"
                    urgency_reason = f"Only {round(available, 1)} units left ({round(days_left, 1)} days of stock)"
                elif days_left != float('inf') and days_left < 7:
                    needs_reorder = True
                    urgency = "HIGH"
                    urgency_reason = f"Low stock: {round(available, 1)} units ({round(days_left, 1)} days left)"
                elif days_left != float('inf') and days_left < 14:
                    needs_reorder = True
                    urgency = "MEDIUM"
                    urgency_reason = f"Stock running low: {round(available, 1)} units"
                
                if needs_reorder:
                    order_cost = recommended_qty * unit_price
                    
                    order_item = {
                        "code": item_code,
                        "name": item_name,
                        "warehouse": warehouse,
                        "current_stock": round(on_hand, 1),
                        "committed": round(committed, 1),
                        "available": round(available, 1),
                        "daily_demand": round(velocity, 2),
                        "days_of_stock_left": round(days_left, 1) if days_left != float('inf') else "N/A",
                        "recommended_qty": recommended_qty,
                        "estimated_cost": round(order_cost),
                        "unit_price": round(unit_price, 2),
                        "urgency": urgency,
                        "urgency_reason": urgency_reason,
                    }
                    
                    if urgency in ["CRITICAL", "HIGH"]:
                        decisions["immediate_orders"].append(order_item)
                        decisions["priority_summary"][urgency] += 1
                        decisions["total_reorder_cost"] += order_cost
                    elif urgency == "MEDIUM" and len(decisions["planned_orders"]) < 10:
                        decisions["planned_orders"].append(order_item)
                        decisions["priority_summary"]["MEDIUM"] += 1
                    
                    # Group by warehouse
                    if warehouse not in decisions["reorder_by_warehouse"]:
                        decisions["reorder_by_warehouse"][warehouse] = []
                    decisions["reorder_by_warehouse"][warehouse].append(order_item)

            # Limit outputs
            decisions["immediate_orders"] = decisions["immediate_orders"][:5]
            decisions["planned_orders"] = decisions["planned_orders"][:5]
            
            # Generate recommendations
            recommendations = []
            if decisions["priority_summary"]["CRITICAL"] > 0:
                recommendations.append({
                    "priority": "CRITICAL",
                    "message": f"🚨 {decisions['priority_summary']['CRITICAL']} items are OUT OF STOCK or critically low",
                    "action": "Place purchase orders immediately"
                })
            if decisions["priority_summary"]["HIGH"] > 0:
                recommendations.append({
                    "priority": "HIGH",
                    "message": f"⚠️ {decisions['priority_summary']['HIGH']} items are running low",
                    "action": "Review and order within 24-48 hours"
                })
            if decisions["priority_summary"]["MEDIUM"] > 0:
                recommendations.append({
                    "priority": "MEDIUM",
                    "message": f"📋 {decisions['priority_summary']['MEDIUM']} items need attention soon",
                    "action": "Plan orders for next week's delivery cycle"
                })
            
            decisions["recommendations"] = recommendations
            
            decisions["summary"] = {
                "total_items_analyzed": len(inventory),
                "items_needing_reorder": decisions["priority_summary"]["CRITICAL"] + decisions["priority_summary"]["HIGH"] + decisions["priority_summary"]["MEDIUM"],
                "critical_count": decisions["priority_summary"]["CRITICAL"],
                "high_count": decisions["priority_summary"]["HIGH"],
                "medium_count": decisions["priority_summary"]["MEDIUM"],
                "estimated_total_cost": round(decisions["total_reorder_cost"], 2),
            }
            
            return decisions
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Error in get_reorder_decisions: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Reorder analysis failed: {str(e)}"
            }
    
    def _get_sales_velocity_data(self) -> Dict[str, float]:
        """Build a map of item_code → average daily units sold."""
        velocity_map: Dict[str, float] = {}
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            sales_data = self.api.get_sales_analysis(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )
            
            if sales_data and isinstance(sales_data, dict):
                items_data = sales_data.get("items") or sales_data.get("data") or []
                
                for item in items_data:
                    code = item.get("ItemCode") or item.get("item_code")
                    quantity = safe_float(item.get("Quantity") or item.get("quantity") or item.get("total_qty"))
                    if code and quantity > 0:
                        velocity_map[code] = round(quantity / 30, 4)
                
                if velocity_map:
                    logger.info(f"Loaded sales velocity for {len(velocity_map)} items")
                    return velocity_map
            
            # Fallback: Use inventory data
            inventory = self.api.get_inventory_report(limit=200)
            for item in inventory:
                code = item.get("ItemCode") or item.get("item_code")
                committed = safe_float(item.get("CurrentIsCommited") or item.get("IsCommited"))
                if code and committed > 0:
                    velocity_map[code] = round(committed / 30, 4)
                    
        except Exception as e:
            logger.warning(f"Could not build velocity map: {e}")
        
        return velocity_map
    
    def _batch_get_prices(self, item_codes: List[str]) -> Dict[str, float]:
        """Fetch prices for multiple items efficiently."""
        price_map = {}
        for code in item_codes[:100]:
            try:
                price = self._get_average_price(code)
                if price > 0:
                    price_map[code] = price
            except Exception:
                pass
        return price_map
    
    def _get_average_price(self, item_code: str) -> float:
        """Get average price for an item."""
        try:
            result = self.pricing.get_price(item_code)
            if result and isinstance(result, dict):
                price = result.get("price")
                if price and price > 0:
                    return float(price)
            return 0.0
        except Exception:
            return 0.0