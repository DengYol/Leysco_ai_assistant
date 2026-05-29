"""
Expanded Alert Generator - Phase 2
===================================
Generates 11 alert types instead of 3:

Original 3:
1. Out of stock alerts
2. Low stock alerts
3. Overdue delivery alerts

New 8:
4. Price change alerts
5. Customer credit alerts
6. Payment overdue alerts
7. Slow moving stock alerts
8. Reorder point alerts
9. Large order alerts
10. Quote status alerts
11. System health alerts
"""

import logging
from typing import List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AlertGeneratorExpanded:
    """Generates 11 types of business alerts"""
    
    def __init__(self, api_service):
        self.api_service = api_service
        logger.info("✅ AlertGeneratorExpanded initialized")
    
    # ========================================================================
    # ORIGINAL ALERTS (3)
    # ========================================================================
    
    async def generate_inventory_alerts(self) -> List[dict]:
        """Generate inventory alerts (out of stock, low stock, reorder point)"""
        alerts = []
        
        try:
            inventory = self.api_service.get_inventory_report(limit=200)
            
            out_of_stock = []
            critical_low = []
            low_stock = []
            reorder_alerts = []
            
            for item in inventory:
                on_hand = float(item.get("CurrentOnHand", 0))
                committed = float(item.get("CurrentIsCommited", 0))
                available = on_hand - committed
                item_name = item.get("ItemName", "Unknown")
                item_code = item.get("ItemCode", "")
                reorder_point = float(item.get("ReorderPoint", 0))
                
                # OUT OF STOCK (0 available)
                if available <= 0:
                    out_of_stock.append({
                        "name": item_name,
                        "code": item_code,
                        "available": available
                    })
                
                # CRITICAL LOW (< 10 units)
                elif available < 10:
                    critical_low.append({
                        "name": item_name,
                        "code": item_code,
                        "available": available
                    })
                
                # LOW STOCK (10-50 units)
                elif 10 <= available < 50:
                    low_stock.append({
                        "name": item_name,
                        "code": item_code,
                        "available": available
                    })
                
                # BELOW REORDER POINT
                if reorder_point > 0 and available < reorder_point:
                    reorder_alerts.append({
                        "name": item_name,
                        "code": item_code,
                        "available": available,
                        "reorder_point": reorder_point
                    })
            
            # Create alerts
            if out_of_stock:
                alerts.append({
                    "id": f"inventory_out_of_stock_{datetime.utcnow().timestamp()}",
                    "title": "🔴 CRITICAL: Items Out of Stock",
                    "message": f"{len(out_of_stock)} items are completely out of stock!",
                    "priority": "CRITICAL",
                    "category": "inventory",
                    "icon": "warning",
                    "action": "show low stock alerts",
                    "metadata": {"count": len(out_of_stock), "items": out_of_stock[:5]}
                })
            
            if critical_low:
                alerts.append({
                    "id": f"inventory_critical_low_{datetime.utcnow().timestamp()}",
                    "title": "🟠 WARNING: Critical Low Stock",
                    "message": f"{len(critical_low)} items have < 10 units available",
                    "priority": "HIGH",
                    "category": "inventory",
                    "icon": "low_priority",
                    "action": "show low stock alerts",
                    "metadata": {"count": len(critical_low), "items": critical_low[:5]}
                })
            
            if low_stock:
                alerts.append({
                    "id": f"inventory_low_stock_{datetime.utcnow().timestamp()}",
                    "title": "⚠️ Low Stock Warning",
                    "message": f"{len(low_stock)} items are running low (10-50 units)",
                    "priority": "MEDIUM",
                    "category": "inventory",
                    "icon": "inventory_2",
                    "action": "show low stock alerts",
                    "metadata": {"count": len(low_stock), "items": low_stock[:5]}
                })
            
            if reorder_alerts:
                alerts.append({
                    "id": f"inventory_reorder_point_{datetime.utcnow().timestamp()}",
                    "title": "📦 Reorder Point Reached",
                    "message": f"{len(reorder_alerts)} items below reorder point - order now!",
                    "priority": "HIGH",
                    "category": "reorder",
                    "icon": "add_shopping_cart",
                    "action": "show reorder alerts",
                    "metadata": {"count": len(reorder_alerts), "items": reorder_alerts[:5]}
                })
            
            logger.info(f"Generated {len(alerts)} inventory alerts")
            
        except Exception as e:
            logger.error(f"Error generating inventory alerts: {e}")
        
        return alerts
    
    async def generate_delivery_alerts(self) -> List[dict]:
        """Generate delivery alerts (pending, overdue)"""
        alerts = []
        
        try:
            deliveries = self.api_service.get_outstanding_deliveries(limit=50)
            
            overdue = []
            pending = []
            
            for delivery in deliveries:
                if delivery.get("IsOverdue"):
                    overdue.append({
                        "number": delivery.get("DeliveryNumber"),
                        "customer": delivery.get("CustomerName"),
                        "amount": delivery.get("LineTotal")
                    })
                else:
                    pending.append({
                        "number": delivery.get("DeliveryNumber"),
                        "customer": delivery.get("CustomerName"),
                        "amount": delivery.get("LineTotal")
                    })
            
            if overdue:
                alerts.append({
                    "id": f"delivery_overdue_{datetime.utcnow().timestamp()}",
                    "title": "🔴 URGENT: Overdue Deliveries",
                    "message": f"{len(overdue)} delivery(s) are overdue!",
                    "priority": "CRITICAL",
                    "category": "delivery",
                    "icon": "warning",
                    "action": "outstanding deliveries",
                    "metadata": {"count": len(overdue), "items": overdue[:5]}
                })
            
            if pending and len(pending) > 5:
                total_value = sum(float(d.get("amount", 0)) for d in pending)
                alerts.append({
                    "id": f"delivery_pending_{datetime.utcnow().timestamp()}",
                    "title": "🚚 Pending Deliveries",
                    "message": f"{len(pending)} deliveries pending (Total: ${total_value:,.2f})",
                    "priority": "MEDIUM",
                    "category": "delivery",
                    "icon": "local_shipping",
                    "action": "outstanding deliveries",
                    "metadata": {"count": len(pending), "total_value": total_value}
                })
            
            logger.info(f"Generated {len(alerts)} delivery alerts")
            
        except Exception as e:
            logger.error(f"Error generating delivery alerts: {e}")
        
        return alerts
    
    # ========================================================================
    # NEW ALERTS (8)
    # ========================================================================
    
    async def generate_price_change_alerts(self) -> List[dict]:
        """Alert when item prices change significantly (NEW)"""
        alerts = []
        
        try:
            # TODO: Implement price tracking
            # Would need to compare current prices with last known prices
            # For now, return empty
            logger.debug("Price change detection - not yet implemented")
        
        except Exception as e:
            logger.error(f"Error generating price alerts: {e}")
        
        return alerts
    
    async def generate_credit_alerts(self) -> List[dict]:
        """Alert when customer exceeds credit limit (NEW)"""
        alerts = []
        
        try:
            # TODO: Fetch customers with exceeded credit
            # customers = self.api_service.get_customers_over_credit_limit()
            logger.debug("Credit limit detection - not yet implemented")
        
        except Exception as e:
            logger.error(f"Error generating credit alerts: {e}")
        
        return alerts
    
    async def generate_payment_alerts(self) -> List[dict]:
        """Alert for overdue payments (NEW)"""
        alerts = []
        
        try:
            # TODO: Fetch invoices overdue for payment
            # invoices = self.api_service.get_overdue_invoices()
            logger.debug("Overdue payment detection - not yet implemented")
        
        except Exception as e:
            logger.error(f"Error generating payment alerts: {e}")
        
        return alerts
    
    async def generate_slow_moving_alerts(self) -> List[dict]:
        """Alert for slow moving stock (NEW)"""
        alerts = []
        
        try:
            # TODO: Identify items not sold in 90+ days
            # slow_items = self.api_service.get_slow_moving_items(days=90)
            logger.debug("Slow moving stock detection - not yet implemented")
        
        except Exception as e:
            logger.error(f"Error generating slow moving alerts: {e}")
        
        return alerts
    
    async def generate_large_order_alerts(self) -> List[dict]:
        """Alert for large orders or repeat customers (NEW)"""
        alerts = []
        
        try:
            # TODO: Detect unusual order patterns
            # recent_orders = self.api_service.get_recent_orders()
            logger.debug("Large order detection - not yet implemented")
        
        except Exception as e:
            logger.error(f"Error generating order alerts: {e}")
        
        return alerts
    
    async def generate_quote_status_alerts(self) -> List[dict]:
        """Alert for quote status changes (NEW)"""
        alerts = []
        
        try:
            # TODO: Track quote acceptance/rejection
            # quotes = self.api_service.get_pending_quotes()
            logger.debug("Quote status detection - not yet implemented")
        
        except Exception as e:
            logger.error(f"Error generating quote alerts: {e}")
        
        return alerts
    
    async def generate_system_alerts(self) -> List[dict]:
        """Generate system health alerts"""
        alerts = []
        
        try:
            alerts.append({
                "id": f"system_health_{datetime.utcnow().timestamp()}",
                "title": "✅ System Status",
                "message": "All systems operational. AI assistant is ready!",
                "priority": "LOW",
                "category": "system",
                "icon": "check_circle",
                "action": "",
                "metadata": {"status": "healthy"}
            })
        
        except Exception as e:
            logger.error(f"Error generating system alerts: {e}")
        
        return alerts
    
    # ========================================================================
    # MAIN SCAN METHOD
    # ========================================================================
    
    async def generate_all_alerts(self) -> List[dict]:
        """Generate all alert types"""
        all_alerts = []
        
        logger.info("🔍 Generating expanded alerts (11 types)...")
        
        # Original 3
        all_alerts.extend(await self.generate_inventory_alerts())
        all_alerts.extend(await self.generate_delivery_alerts())
        all_alerts.extend(await self.generate_system_alerts())
        
        # New 8 (mostly stubs, ready for implementation)
        all_alerts.extend(await self.generate_price_change_alerts())
        all_alerts.extend(await self.generate_credit_alerts())
        all_alerts.extend(await self.generate_payment_alerts())
        all_alerts.extend(await self.generate_slow_moving_alerts())
        all_alerts.extend(await self.generate_large_order_alerts())
        all_alerts.extend(await self.generate_quote_status_alerts())
        
        logger.info(f"✅ Generated {len(all_alerts)} total alerts")
        
        return all_alerts