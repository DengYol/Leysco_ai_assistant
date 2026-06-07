"""
app/services/mock_notification_service.py (P1.4 - Gated Completely)
====================================================================
Mock Notification Service - FOR TESTING ONLY.

CHANGE:
- Entire service is gated behind ALLOW_SAMPLE_DATA flag
- Production: Service raises error if called
- Testing: Service works with hardcoded notifications
- Should be used in tests only, not in production
"""

import logging
import uuid
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE GATE: Allow sample data (default: false for production)
# ============================================================================

ALLOW_SAMPLE_DATA = os.getenv("ALLOW_SAMPLE_DATA", "false").lower() == "true"

if not ALLOW_SAMPLE_DATA:
    logger.warning("⚠️ ALLOW_SAMPLE_DATA is disabled. MockNotificationService will NOT be available.")
else:
    logger.warning("✅ ALLOW_SAMPLE_DATA is enabled. MockNotificationService is available for testing.")


class MockNotificationService:
    """
    Mock notification service with HARDCODED TEST DATA.
    
    ⚠️ FOR TESTING ONLY - Do not use in production!
    
    Only available when ALLOW_SAMPLE_DATA=true.
    In production, real notifications come from actual API/database.
    """
    
    def __init__(self):
        if not ALLOW_SAMPLE_DATA:
            logger.error("🚫 MockNotificationService cannot be initialized - ALLOW_SAMPLE_DATA is disabled")
            raise RuntimeError(
                "MockNotificationService is only for testing. "
                "Set ALLOW_SAMPLE_DATA=true to enable test data. "
                "In production, use real notification service."
            )
        
        self._notifications_cache = {}
        logger.warning("⚠️ Mock Notification Service initialized (TEST DATA ONLY)")
    
    async def get_notifications(
        self,
        user_id: int,
        limit: int = 20,
        unread_only: bool = False
    ) -> List[Dict]:
        """
        Get MOCK notifications for a user (TEST DATA).
        
        ⚠️ Returns hardcoded test notifications only.
        """
        # Check gate
        if not ALLOW_SAMPLE_DATA:
            logger.error(f"🚫 get_notifications called without ALLOW_SAMPLE_DATA=true")
            raise RuntimeError("MockNotificationService not available - ALLOW_SAMPLE_DATA is disabled")
        
        logger.warning(f"📬 Mock service: Getting TEST notifications for user {user_id}")
        
        # Generate fresh notifications if not exists
        if user_id not in self._notifications_cache:
            self._generate_mock_notifications(user_id)
        
        notifications = self._notifications_cache.get(user_id, [])
        
        if unread_only:
            notifications = [n for n in notifications if not n.get("is_read", False)]
        
        logger.warning(f"📬 Returning {len(notifications)} TEST notifications")
        
        return notifications[:limit]
    
    def _generate_mock_notifications(self, user_id: int):
        """
        Generate HARDCODED MOCK notifications (TEST DATA ONLY).
        
        ⚠️ These are fake notifications for testing the UI/UX.
        """
        notifications = []
        now = datetime.now()
        
        # ===== MOCK NOTIFICATION #1: Low stock alert (Critical) =====
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "LOW_STOCK",
            "title": "⚠️ Critical Stock Alert - Vegimax 250ml",
            "message": "Vegimax 250ml has only 15 units left! This item sells 5 units per day. Order immediately to avoid stockout.",
            "message_sw": "⚠️ Tahadhari ya Hisa Muhimu - Vegimax 250ml imesalia vitengo 15 tu!",
            "action": "Create Reorder",
            "action_intent": "CREATE_QUOTATION",
            "action_data": {"item_name": "Vegimax 250ml", "quantity": 50},
            "priority": "CRITICAL",
            "score": 95,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
            "metadata": {
                "item_code": "VEGIMAX250",
                "current_stock": 15,
                "daily_sales": 5,
                "source": "mock"  # ===== MARK AS MOCK =====
            }
        })
        
        # ===== MOCK NOTIFICATION #2: Churn risk (High) =====
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "CHURN_RISK",
            "title": "👥 Customer Churn Risk - Magomano Suppliers",
            "message": "Magomano Suppliers hasn't placed an order in 65 days (last order was KES 45,000).",
            "message_sw": "👥 Hatari ya Kupoteza Mteja - Magomano Suppliers",
            "action": "Contact Customer",
            "action_intent": "GET_CUSTOMER_DETAILS",
            "action_data": {"customer_name": "Magomano Suppliers"},
            "priority": "HIGH",
            "score": 85,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=3)).isoformat(),
            "metadata": {
                "customer_code": "MAG001",
                "days_inactive": 65,
                "last_order_value": 45000,
                "source": "mock"  # ===== MARK AS MOCK =====
            }
        })
        
        # ===== MOCK NOTIFICATION #3: Overdue delivery (Critical) =====
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "REORDER",
            "title": "🚚 OVERDUE Delivery - #DEL-2024-001",
            "message": "Delivery #DEL-2024-001 to Nairobi Warehouse is 3 days overdue.",
            "message_sw": "🚚 Usafirishaji Umechelewa - #DEL-2024-001",
            "action": "Track Delivery",
            "action_intent": "TRACK_DELIVERY",
            "action_data": {"delivery_number": "DEL-2024-001"},
            "priority": "CRITICAL",
            "score": 98,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=12)).isoformat(),
            "metadata": {
                "delivery_id": "DEL-2024-001",
                "customer": "Nairobi Warehouse",
                "days_overdue": 3,
                "source": "mock"  # ===== MARK AS MOCK =====
            }
        })
        
        # ===== MOCK NOTIFICATION #4: Price drop (Medium) =====
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "PRICE_DROP",
            "title": "💰 Price Drop - Easeed 1kg",
            "message": "Easeed 1kg price dropped by 15%! Now KES 850 (was KES 1000).",
            "message_sw": "💰 Bei Imeshuka - Easeed 1kg",
            "action": "Check Price",
            "action_intent": "GET_ITEM_PRICE",
            "action_data": {"item_name": "Easeed 1kg"},
            "priority": "MEDIUM",
            "score": 70,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=5)).isoformat(),
            "metadata": {
                "item_code": "EASEED1KG",
                "old_price": 1000,
                "new_price": 850,
                "discount_percent": 15,
                "source": "mock"  # ===== MARK AS MOCK =====
            }
        })
        
        # ===== MOCK NOTIFICATION #5: Seasonal opportunity (Medium) =====
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "SEASONAL",
            "title": "🌱 Planting Season Special",
            "message": "Planting season starts in 2 weeks. Last year, seed sales increased by 40%.",
            "message_sw": "🌱 Msimu wa Kupanda - Maandalizi",
            "action": "View Seasonal Products",
            "action_intent": "GET_ITEMS",
            "action_data": {"item_name": "seeds"},
            "priority": "MEDIUM",
            "score": 75,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=14)).isoformat(),
            "metadata": {
                "season": "planting",
                "expected_increase": 40,
                "source": "mock"  # ===== MARK AS MOCK =====
            }
        })
        
        # ===== MOCK NOTIFICATION #6: Upsell opportunity (Low) =====
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "UPSELL",
            "title": "📈 Upsell Opportunity - Nairobi Customers",
            "message": "15 customers who bought Vegimax 250ml might be interested in the new Vegimax 500ml.",
            "message_sw": "📈 Fursa ya Kuuza Zaidi",
            "action": "View Customers",
            "action_intent": "FIND_CUSTOMERS_BY_ITEM",
            "action_data": {"item_name": "Vegimax"},
            "priority": "LOW",
            "score": 60,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=7)).isoformat(),
            "metadata": {
                "customer_count": 15,
                "product": "Vegimax 500ml",
                "source": "mock"  # ===== MARK AS MOCK =====
            }
        })
        
        # ===== MOCK NOTIFICATION #7: Inventory health (Medium) =====
        notifications.append({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": "REORDER",
            "title": "📊 Inventory Health Check",
            "message": "Your inventory turnover rate has dropped 12% this month. 8 items are overstocked.",
            "message_sw": "📊 Ukaguzi wa Afya ya Hisa",
            "action": "View Inventory Health",
            "action_intent": "ANALYZE_INVENTORY_HEALTH",
            "action_data": {},
            "priority": "MEDIUM",
            "score": 80,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=5)).isoformat(),
            "metadata": {
                "turnover_decrease": 12,
                "overstock_items": 8,
                "source": "mock"  # ===== MARK AS MOCK =====
            }
        })
        
        self._notifications_cache[user_id] = notifications
        logger.warning(f"⚠️ Generated 7 MOCK notifications for user {user_id} (TEST DATA)")
    
    async def mark_as_read(self, user_id: int, notification_id: str) -> bool:
        """Mark a notification as read (mock)."""
        if not ALLOW_SAMPLE_DATA:
            raise RuntimeError("MockNotificationService not available - ALLOW_SAMPLE_DATA is disabled")
        
        if user_id in self._notifications_cache:
            for n in self._notifications_cache[user_id]:
                if n.get("id") == notification_id:
                    n["is_read"] = True
                    return True
        return False
    
    async def mark_all_as_read(self, user_id: int) -> int:
        """Mark all notifications as read (mock)."""
        if not ALLOW_SAMPLE_DATA:
            raise RuntimeError("MockNotificationService not available - ALLOW_SAMPLE_DATA is disabled")
        
        count = 0
        if user_id in self._notifications_cache:
            for n in self._notifications_cache[user_id]:
                if not n.get("is_read", False):
                    n["is_read"] = True
                    count += 1
        return count
    
    async def get_unread_count(self, user_id: int) -> int:
        """Get unread count (mock)."""
        if not ALLOW_SAMPLE_DATA:
            raise RuntimeError("MockNotificationService not available - ALLOW_SAMPLE_DATA is disabled")
        
        if user_id in self._notifications_cache:
            return len([n for n in self._notifications_cache[user_id] if not n.get("is_read", False)])
        return 0
    
    async def delete_notification(self, user_id: int, notification_id: str) -> bool:
        """Delete a notification (mock)."""
        if not ALLOW_SAMPLE_DATA:
            raise RuntimeError("MockNotificationService not available - ALLOW_SAMPLE_DATA is disabled")
        
        if user_id in self._notifications_cache:
            original_len = len(self._notifications_cache[user_id])
            self._notifications_cache[user_id] = [
                n for n in self._notifications_cache[user_id] 
                if n.get("id") != notification_id
            ]
            return len(self._notifications_cache[user_id]) < original_len
        return False
    
    async def clear_all(self, user_id: int) -> int:
        """Clear all notifications for a user (mock)."""
        if not ALLOW_SAMPLE_DATA:
            raise RuntimeError("MockNotificationService not available - ALLOW_SAMPLE_DATA is disabled")
        
        if user_id in self._notifications_cache:
            count = len(self._notifications_cache[user_id])
            self._notifications_cache[user_id] = []
            return count
        return 0


# Singleton instance
_mock_service = None


def get_mock_notification_service() -> MockNotificationService:
    """
    Get or create mock notification service.
    
    ⚠️ Only available when ALLOW_SAMPLE_DATA=true
    Raises RuntimeError in production.
    """
    global _mock_service
    if _mock_service is None:
        if not ALLOW_SAMPLE_DATA:
            logger.error("🚫 Cannot create MockNotificationService - ALLOW_SAMPLE_DATA is disabled")
            raise RuntimeError(
                "MockNotificationService is disabled in production. "
                "Set ALLOW_SAMPLE_DATA=true to enable test notifications."
            )
        _mock_service = MockNotificationService()
        logger.warning("✅ Created MockNotificationService singleton (TEST ONLY)")
    return _mock_service