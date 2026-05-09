"""
app/services/mock_notification_service.py
==========================================
Mock Notification Service for testing when API is unreachable
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class MockNotificationService:
    """Mock notification service for testing."""
    
    def __init__(self):
        self._notifications_cache = {}
        logger.info("✅ Mock Notification Service initialized")
    
    async def get_notifications(
        self,
        user_id: int,
        limit: int = 20,
        unread_only: bool = False
    ) -> List[Dict]:
        """Get mock notifications for a user."""
        
        logger.info(f"📬 Mock service: Getting notifications for user {user_id}")
        
        # Generate fresh notifications for this user if not exists
        if user_id not in self._notifications_cache:
            self._generate_mock_notifications(user_id)
        
        notifications = self._notifications_cache.get(user_id, [])
        
        if unread_only:
            notifications = [n for n in notifications if not n.get("is_read", False)]
        
        logger.info(f"📬 Returning {len(notifications)} mock notifications for user {user_id}")
        
        return notifications[:limit]
    
    def _generate_mock_notifications(self, user_id: int):
        """Generate mock notifications for a user."""
        notifications = []
        now = datetime.now()
        
        # Mock 1: Low stock alert (Critical)
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "LOW_STOCK",
            "title": "⚠️ Critical Stock Alert - Vegimax 250ml",
            "message": "Vegimax 250ml has only 15 units left! This item sells 5 units per day. Order immediately to avoid stockout.",
            "message_sw": "⚠️ Tahadhari ya Hisa Muhimu - Vegimax 250ml imesalia vitengo 15 tu! Bidhaa hii inauza vitengo 5 kwa siku. Agiza sasa ili kuepuka kuisha kwa hisa.",
            "action": "Create Reorder",
            "action_intent": "CREATE_QUOTATION",
            "action_data": {"item_name": "Vegimax 250ml", "quantity": 50},
            "priority": "CRITICAL",
            "score": 95,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
            "metadata": {"item_code": "VEGIMAX250", "current_stock": 15, "daily_sales": 5}
        })
        
        # Mock 2: Churn risk (High)
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "CHURN_RISK",
            "title": "👥 Customer Churn Risk - Magomano Suppliers",
            "message": "Magomano Suppliers hasn't placed an order in 65 days (last order was KES 45,000). Send a win-back offer with 10% discount to re-engage.",
            "message_sw": "👥 Hatari ya Kupoteza Mteja - Magomano Suppliers hajaweka oda kwa siku 65 (oda ya mwisho ilikuwa KES 45,000). Tuma ofa ya kuwataka warudi na punguzo la 10%.",
            "action": "Contact Customer",
            "action_intent": "GET_CUSTOMER_DETAILS",
            "action_data": {"customer_name": "Magomano Suppliers"},
            "priority": "HIGH",
            "score": 85,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=3)).isoformat(),
            "metadata": {"customer_code": "MAG001", "days_inactive": 65, "last_order_value": 45000}
        })
        
        # Mock 3: Overdue delivery (Critical)
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "REORDER",
            "title": "🚚 OVERDUE Delivery - #DEL-2024-001",
            "message": "Delivery #DEL-2024-001 to Nairobi Warehouse is 3 days overdue. Customer is waiting for 500 units of Vegimax.",
            "message_sw": "🚚 Usafirishaji Umechelewa - #DEL-2024-001 kwa Ghala la Nairobi umechelewa kwa siku 3. Mteja anasubiri vitengo 500 vya Vegimax.",
            "action": "Track Delivery",
            "action_intent": "TRACK_DELIVERY",
            "action_data": {"delivery_number": "DEL-2024-001"},
            "priority": "CRITICAL",
            "score": 98,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=12)).isoformat(),
            "metadata": {"delivery_id": "DEL-2024-001", "customer": "Nairobi Warehouse", "days_overdue": 3}
        })
        
        # Mock 4: Price drop opportunity (Medium)
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "PRICE_DROP",
            "title": "💰 Price Drop - Easeed 1kg",
            "message": "Easeed 1kg price dropped by 15%! Now KES 850 (was KES 1000). Good time to stock up for the planting season.",
            "message_sw": "💰 Bei Imeshuka - Easeed 1kg imeshuka kwa 15%! Sasa KES 850 (ilikuwa KES 1000). Wakati mwema wa kununua kwa ajili ya msimu wa kupanda.",
            "action": "Check Price",
            "action_intent": "GET_ITEM_PRICE",
            "action_data": {"item_name": "Easeed 1kg"},
            "priority": "MEDIUM",
            "score": 70,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=5)).isoformat(),
            "metadata": {"item_code": "EASEED1KG", "old_price": 1000, "new_price": 850, "discount_percent": 15}
        })
        
        # Mock 5: Seasonal opportunity (Medium)
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "SEASONAL",
            "title": "🌱 Planting Season Special",
            "message": "Planting season starts in 2 weeks. Last year, seed sales increased by 40% during this period. Prepare inventory and run promotions now!",
            "message_sw": "🌱 Msimu wa Kupanda - Maandalizi ya Msimu",
            "action": "View Seasonal Products",
            "action_intent": "GET_ITEMS",
            "action_data": {"item_name": "seeds"},
            "priority": "MEDIUM",
            "score": 75,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=14)).isoformat(),
            "metadata": {"season": "planting", "expected_increase": 40}
        })
        
        # Mock 6: Upsell opportunity (Low)
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "UPSELL",
            "title": "📈 Upsell Opportunity - Nairobi Customers",
            "message": "15 customers who bought Vegimax 250ml last month might be interested in the new Vegimax 500ml (39% more value).",
            "message_sw": "📈 Fursa ya Kuuza Zaidi - Wateja wa Nairobi wanaweza kupendezwa na Vegimax 500ml mpya.",
            "action": "View Customers",
            "action_intent": "FIND_CUSTOMERS_BY_ITEM",
            "action_data": {"item_name": "Vegimax"},
            "priority": "LOW",
            "score": 60,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=7)).isoformat(),
            "metadata": {"customer_count": 15, "product": "Vegimax 500ml"}
        })
        
        # Mock 7: Inventory health (Manager only - Medium)
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "REORDER",
            "title": "📊 Inventory Health Check",
            "message": "Your inventory turnover rate has dropped 12% this month. 8 items are overstocked (>90 days supply). Run a promotion to clear slow movers.",
            "message_sw": "📊 Ukaguzi wa Afya ya Hisa - Kiwango cha mzunguko wa hisa kimepungua kwa 12% mwezi huu.",
            "action": "View Inventory Health",
            "action_intent": "ANALYZE_INVENTORY_HEALTH",
            "action_data": {},
            "priority": "MEDIUM",
            "score": 80,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=5)).isoformat(),
            "metadata": {"turnover_decrease": 12, "overstock_items": 8}
        })
        
        self._notifications_cache[user_id] = notifications
        logger.info(f"📝 Generated 7 mock notifications for user {user_id}")
    
    async def mark_as_read(self, user_id: int, notification_id: str) -> bool:
        """Mark a notification as read."""
        if user_id in self._notifications_cache:
            for n in self._notifications_cache[user_id]:
                if n.get("id") == notification_id:
                    n["is_read"] = True
                    logger.info(f"📖 Marked notification {notification_id[:8]} as read for user {user_id}")
                    return True
        return False
    
    async def mark_all_as_read(self, user_id: int) -> int:
        """Mark all notifications as read."""
        count = 0
        if user_id in self._notifications_cache:
            for n in self._notifications_cache[user_id]:
                if not n.get("is_read", False):
                    n["is_read"] = True
                    count += 1
            logger.info(f"📖 Marked {count} notifications as read for user {user_id}")
        return count
    
    async def get_unread_count(self, user_id: int) -> int:
        """Get unread count."""
        if user_id in self._notifications_cache:
            return len([n for n in self._notifications_cache[user_id] if not n.get("is_read", False)])
        return 0
    
    async def delete_notification(self, user_id: int, notification_id: str) -> bool:
        """Delete a notification."""
        if user_id in self._notifications_cache:
            original_len = len(self._notifications_cache[user_id])
            self._notifications_cache[user_id] = [
                n for n in self._notifications_cache[user_id] 
                if n.get("id") != notification_id
            ]
            if len(self._notifications_cache[user_id]) < original_len:
                logger.info(f"🗑️ Deleted notification {notification_id[:8]} for user {user_id}")
                return True
        return False
    
    async def clear_all(self, user_id: int) -> int:
        """Clear all notifications for a user."""
        if user_id in self._notifications_cache:
            count = len(self._notifications_cache[user_id])
            self._notifications_cache[user_id] = []
            logger.info(f"🗑️ Cleared all {count} notifications for user {user_id}")
            return count
        return 0


# Singleton instance
_mock_service = None


def get_mock_notification_service() -> MockNotificationService:
    """Get or create mock notification service."""
    global _mock_service
    if _mock_service is None:
        _mock_service = MockNotificationService()
        logger.info("✅ Created MockNotificationService singleton")
    return _mock_service