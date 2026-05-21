"""Proactive notification service for AI assistant - Manager focused"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio

from app.services.cache_service import get_cache_service
from app.services.leysco_api import create_api_service

logger = logging.getLogger(__name__)


class AINotification:
    """Notification model for proactive alerts"""
    
    def __init__(self, id: str, title: str, message: str, priority: str, 
                 action: str = "", category: str = "general", icon: str = "notifications",
                 actionable: bool = True):
        self.id = id
        self.title = title
        self.message = message
        self.priority = priority  # HIGH, MEDIUM, LOW
        self.action = action
        self.category = category
        self.icon = icon
        self.actionable = actionable
        self.created_at = datetime.now().isoformat()
        self.is_read = False
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "priority": self.priority,
            "action": self.action,
            "category": self.category,
            "icon": self.icon,
            "actionable": self.actionable,
            "created_at": self.created_at,
            "is_read": self.is_read
        }
    
    def get_icon(self) -> str:
        icons = {
            "warning": "warning",
            "info": "info",
            "notifications": "notifications",
            "inventory": "inventory_2",
            "delivery": "local_shipping",
            "analytics": "analytics",
            "pricing": "attach_money",
            "quotations": "receipt_long",
            "customer": "people",
            "alert": "error_outline"
        }
        return icons.get(self.category, "notifications")
    
    def get_priority_color(self) -> int:
        colors = {
            "HIGH": 0xFFEF4444,  # Red - Critical
            "MEDIUM": 0xFFF59E0B,  # Orange - Warning
            "LOW": 0xFF3B82F6  # Blue - Info
        }
        return colors.get(self.priority, 0xFF6B7280)
    
    def get_localized_message(self, language: str = "en") -> str:
        return self.message


class NotificationService:
    """Service for generating proactive notifications - Manager focused"""
    
    def __init__(self):
        self.cache = get_cache_service()
        self._notifications_cache = {}  # user_id -> list of notifications
        self._last_scan = {}
    
    async def scan_for_user(
        self,
        user_id: int,
        user_role: str,
        tenant_code: str,
        user_token: str,
        assigned_customers: List[str] = None
    ) -> List[AINotification]:
        """Scan for notifications for a specific user"""
        notifications = []
        
        try:
            # Create API service with user token
            api_service = create_api_service(user_token=user_token)
            
            logger.info(f"🔍 Scanning for notifications for user {user_id} (role: {user_role})")
            
            # HIGH PRIORITY - Critical alerts for managers
            high_priority_alerts = await self._check_critical_alerts(api_service, user_role)
            notifications.extend(high_priority_alerts)
            
            # MEDIUM PRIORITY - Important business alerts
            medium_priority_alerts = await self._check_important_alerts(api_service, user_role)
            notifications.extend(medium_priority_alerts)
            
            # LOW PRIORITY - Informational alerts
            low_priority_alerts = await self._check_informational_alerts(api_service, user_role)
            notifications.extend(low_priority_alerts)
            
            # Sort by priority
            notifications.sort(key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(x.priority, 3))
            
            # Store notifications in cache
            self._notifications_cache[user_id] = notifications
            self._last_scan[user_id] = datetime.now()
            
            high_count = len([n for n in notifications if n.priority == "HIGH"])
            medium_count = len([n for n in notifications if n.priority == "MEDIUM"])
            low_count = len([n for n in notifications if n.priority == "LOW"])
            
            logger.info(f"✅ Generated {len(notifications)} notifications for user {user_id} (H:{high_count}, M:{medium_count}, L:{low_count})")
            
        except Exception as e:
            logger.error(f"Error scanning notifications for user {user_id}: {e}", exc_info=True)
        
        return notifications
    
    async def _check_critical_alerts(self, api_service, user_role: str) -> List[AINotification]:
        """Check for critical alerts - HIGH priority"""
        notifications = []
        
        try:
            # 1. Out of Stock Items (Critical)
            inventory = api_service.get_inventory_report(limit=200)
            out_of_stock = []
            critical_low = []
            
            for item in inventory:
                on_hand = float(item.get("CurrentOnHand", 0))
                committed = float(item.get("CurrentIsCommited", 0))
                available = on_hand - committed
                item_name = item.get("ItemName", "Unknown")
                
                if available <= 0:
                    out_of_stock.append({"name": item_name, "available": available})
                elif available < 10:
                    critical_low.append({"name": item_name, "available": available})
            
            if out_of_stock:
                notification = AINotification(
                    id=f"out_of_stock_{datetime.now().timestamp()}",
                    title="🔴 CRITICAL: Items Out of Stock",
                    message=f"{len(out_of_stock)} item(s) are completely out of stock! Immediate action required.",
                    priority="HIGH",
                    action="show low stock alerts",
                    category="alert",
                    icon="warning",
                    actionable=True
                )
                notifications.append(notification)
                
                # Add top 3 out of stock items as details
                for item in out_of_stock[:3]:
                    notification = AINotification(
                        id=f"out_of_stock_{item['name']}_{datetime.now().timestamp()}",
                        title="📦 Out of Stock",
                        message=f"{item['name']} has 0 units available. Reorder immediately!",
                        priority="HIGH",
                        action=f"check stock for {item['name']}",
                        category="alert",
                        icon="warning",
                        actionable=True
                    )
                    notifications.append(notification)
            
            elif critical_low:
                notification = AINotification(
                    id=f"critical_low_{datetime.now().timestamp()}",
                    title="🟠 CRITICAL: Very Low Stock",
                    message=f"{len(critical_low)} item(s) have less than 10 units left! Order urgently.",
                    priority="HIGH",
                    action="show low stock alerts",
                    category="alert",
                    icon="warning",
                    actionable=True
                )
                notifications.append(notification)
            
            # 2. Overdue Deliveries (Critical for managers)
            deliveries = api_service.get_outstanding_deliveries(limit=50)
            overdue_count = sum(1 for d in deliveries if d.get("IsOverdue", False))
            
            if overdue_count > 0:
                notification = AINotification(
                    id=f"overdue_deliveries_{datetime.now().timestamp()}",
                    title="🔴 URGENT: Overdue Deliveries",
                    message=f"{overdue_count} delivery(s) are overdue! Customer satisfaction at risk.",
                    priority="HIGH",
                    action="outstanding deliveries",
                    category="delivery",
                    icon="warning",
                    actionable=True
                )
                notifications.append(notification)
            
            # 3. Negative Inventory (Technical issue)
            negative_inventory = []
            for item in inventory:
                on_hand = float(item.get("CurrentOnHand", 0))
                if on_hand < 0:
                    negative_inventory.append(item.get("ItemName", "Unknown"))
            
            if negative_inventory:
                notification = AINotification(
                    id=f"negative_inventory_{datetime.now().timestamp()}",
                    title="🔴 ERROR: Negative Inventory Detected",
                    message=f"{len(negative_inventory)} item(s) have negative stock levels! Investigate immediately.",
                    priority="HIGH",
                    action="show inventory health",
                    category="alert",
                    icon="error_outline",
                    actionable=True
                )
                notifications.append(notification)
            
        except Exception as e:
            logger.error(f"Error checking critical alerts: {e}")
        
        return notifications
    
    async def _check_important_alerts(self, api_service, user_role: str) -> List[AINotification]:
        """Check for important alerts - MEDIUM priority"""
        notifications = []
        
        try:
            # 1. Low Stock Warning (Medium priority)
            inventory = api_service.get_inventory_report(limit=200)
            low_stock = []
            
            for item in inventory:
                on_hand = float(item.get("CurrentOnHand", 0))
                committed = float(item.get("CurrentIsCommited", 0))
                available = on_hand - committed
                
                if 10 <= available < 50:
                    low_stock.append({
                        "name": item.get("ItemName", "Unknown"),
                        "available": available
                    })
            
            if low_stock:
                notification = AINotification(
                    id=f"low_stock_warning_{datetime.now().timestamp()}",
                    title="⚠️ Low Stock Warning",
                    message=f"{len(low_stock)} item(s) are running low (<50 units). Plan reorders soon.",
                    priority="MEDIUM",
                    action="show low stock alerts",
                    category="inventory",
                    icon="inventory_2",
                    actionable=True
                )
                notifications.append(notification)
                
                # Add top 3 low stock items
                for item in low_stock[:3]:
                    notification = AINotification(
                        id=f"low_stock_{item['name']}_{datetime.now().timestamp()}",
                        title="📦 Low Stock Alert",
                        message=f"{item['name']} only has {item['available']:.0f} units left. Consider reordering.",
                        priority="MEDIUM",
                        action=f"check stock for {item['name']}",
                        category="inventory",
                        icon="inventory_2",
                        actionable=True
                    )
                    notifications.append(notification)
            
            # 2. Slow Moving Items (Manager only)
            if user_role == "manager":
                slow_items = api_service.get_slow_moving_items(limit=10, days=90)
                critical_slow = [i for i in slow_items if i.get("Severity") == "critical"]
                
                if critical_slow:
                    notification = AINotification(
                        id=f"slow_moving_critical_{datetime.now().timestamp()}",
                        title="🐢 Critical Slow Movers",
                        message=f"{len(critical_slow)} item(s) have very low turnover. Consider markdowns or bundling.",
                        priority="MEDIUM",
                        action="show slow moving items",
                        category="analytics",
                        icon="analytics",
                        actionable=True
                    )
                    notifications.append(notification)
            
            # 3. Stale Quotations (Manager only)
            if user_role == "manager":
                notification = AINotification(
                    id=f"quotation_followup_{datetime.now().timestamp()}",
                    title="📄 Pending Quotations",
                    message="Some quotations need follow-up. Check which ones are still pending.",
                    priority="MEDIUM",
                    action="show follow-up quotations",
                    category="quotations",
                    icon="receipt_long",
                    actionable=True
                )
                notifications.append(notification)
            
            # 4. Outstanding Deliveries Summary (not overdue, but pending)
            deliveries = api_service.get_outstanding_deliveries(limit=50)
            pending_deliveries = [d for d in deliveries if not d.get("IsOverdue", False)]
            
            if pending_deliveries:
                total_value = sum(float(d.get("LineTotal", 0)) for d in pending_deliveries)
                notification = AINotification(
                    id=f"pending_deliveries_{datetime.now().timestamp()}",
                    title="🚚 Pending Deliveries",
                    message=f"{len(pending_deliveries)} delivery(s) pending, total value KES {total_value:,.2f}",
                    priority="MEDIUM",
                    action="outstanding deliveries",
                    category="delivery",
                    icon="local_shipping",
                    actionable=True
                )
                notifications.append(notification)
            
        except Exception as e:
            logger.error(f"Error checking important alerts: {e}")
        
        return notifications
    
    async def _check_informational_alerts(self, api_service, user_role: str) -> List[AINotification]:
        """Check for informational alerts - LOW priority"""
        notifications = []
        
        try:
            # 1. Top Selling Items (Good news)
            top_items = api_service.get_top_selling_items(limit=5, days=30)
            
            if top_items:
                top_item = top_items[0]
                item_name = top_item.get("ItemName", "Unknown")
                quantity = top_item.get("quantity", 0)
                
                notification = AINotification(
                    id=f"top_seller_{datetime.now().timestamp()}",
                    title="🔥 Hot Seller Alert!",
                    message=f"{item_name} is our best seller with {quantity:.0f} units sold this month! Keep stock充足.",
                    priority="LOW",
                    action=f"price of {item_name}",
                    category="analytics",
                    icon="trending_up",
                    actionable=True
                )
                notifications.append(notification)
            
            # 2. Inventory Health Summary (for managers)
            if user_role == "manager":
                health = api_service.get_inventory_report(limit=500)
                total_items = len(health)
                total_value = sum(float(i.get("CurrentOnHand", 0)) * 500 for i in health[:100])  # Estimate
                
                notification = AINotification(
                    id=f"inventory_summary_{datetime.now().timestamp()}",
                    title="📊 Inventory Summary",
                    message=f"Total {total_items} items in inventory, estimated value KES {total_value:,.2f}",
                    priority="LOW",
                    action="analyze inventory health",
                    category="analytics",
                    icon="analytics",
                    actionable=True
                )
                notifications.append(notification)
            
            # 3. System Health (always good to know)
            notification = AINotification(
                id=f"system_health_{datetime.now().timestamp()}",
                title="✅ System Status",
                message="All systems operational. AI assistant is ready to help!",
                priority="LOW",
                action="",
                category="general",
                icon="check_circle",
                actionable=False
            )
            notifications.append(notification)
            
        except Exception as e:
            logger.error(f"Error checking informational alerts: {e}")
        
        return notifications
    
    async def get_notifications(
        self,
        user_id: int,
        limit: int = 20,
        unread_only: bool = False
    ) -> List[dict]:
        """Get notifications for a user"""
        notifications = self._notifications_cache.get(user_id, [])
        
        # Filter unread if requested
        if unread_only:
            notifications = [n for n in notifications if not n.is_read]
        
        # Sort by priority (HIGH first) and then by date (newest first)
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        notifications.sort(key=lambda x: (priority_order.get(x.priority, 3), -datetime.fromisoformat(x.created_at).timestamp()))
        
        return [n.to_dict() for n in notifications[:limit]]
    
    async def get_unread_count(self, user_id: int) -> int:
        """Get unread notification count for a user"""
        notifications = self._notifications_cache.get(user_id, [])
        unread = [n for n in notifications if not n.is_read]
        return len(unread)
    
    async def mark_as_read(self, user_id: int, notification_id: str) -> bool:
        """Mark a notification as read"""
        notifications = self._notifications_cache.get(user_id, [])
        for n in notifications:
            if n.id == notification_id:
                n.is_read = True
                logger.info(f"Marked notification {notification_id} as read for user {user_id}")
                return True
        return False
    
    async def mark_all_as_read(self, user_id: int) -> int:
        """Mark all notifications as read"""
        notifications = self._notifications_cache.get(user_id, [])
        count = 0
        for n in notifications:
            if not n.is_read:
                n.is_read = True
                count += 1
        logger.info(f"Marked {count} notifications as read for user {user_id}")
        return count
    
    async def delete_notification(self, user_id: int, notification_id: str) -> bool:
        """Delete a notification"""
        notifications = self._notifications_cache.get(user_id, [])
        for i, n in enumerate(notifications):
            if n.id == notification_id:
                del notifications[i]
                logger.info(f"Deleted notification {notification_id} for user {user_id}")
                return True
        return False
    
    async def save_notifications(self, user_id: int, notifications: List[AINotification]):
        """Save notifications for a user"""
        self._notifications_cache[user_id] = notifications
        logger.info(f"Saved {len(notifications)} notifications for user {user_id}")


# Singleton instance
_notification_service = None


def get_notification_service() -> NotificationService:
    """Get notification service singleton"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service