"""
app/services/notification_service.py
=====================================
Proactive Notification Engine
Scans for opportunities and creates user notifications

FEATURES:
- Low stock alerts
- Churn risk detection
- Reorder recommendations
- Price drop alerts
- Seasonal opportunities
- Upsell opportunities
- Anomaly detection alerts
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime
import uuid

from app.services.cache_service import get_cache_service
from app.services.leysco_api_service import create_api_service
from app.services.pricing_service import create_pricing_service
from app.ai_engine.decision_support import DecisionSupport

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    LOW_STOCK = "LOW_STOCK"
    CHURN_RISK = "CHURN_RISK"
    REORDER = "REORDER"
    PRICE_DROP = "PRICE_DROP"
    SEASONAL = "SEASONAL"
    UPSELL = "UPSELL"
    CROSS_SELL = "CROSS_SELL"
    LEAD_OPPORTUNITY = "LEAD_OPPORTUNITY"
    ANOMALY = "ANOMALY"  # New: Anomaly detection alerts


class Priority(str, Enum):
    CRITICAL = "CRITICAL"  # Act immediately (0-24 hours)
    HIGH = "HIGH"          # Act within 24-48 hours
    MEDIUM = "MEDIUM"      # Act within 1 week
    LOW = "LOW"            # Nice to know


@dataclass
class Notification:
    """Data class for a notification"""
    id: str
    user_id: int
    user_role: str
    tenant_code: str
    type: NotificationType
    title: str
    message: str
    message_sw: str  # Swahili version
    action: str  # Suggested action text
    action_intent: str  # Intent to trigger when tapped
    action_data: Dict[str, Any]  # Data for the action
    priority: Priority
    score: int  # 0-100
    potential_value: float
    is_read: bool
    created_at: str
    expires_at: str
    metadata: Dict[str, Any]


class NotificationService:
    """
    Proactive notification engine.
    Scans for opportunities and manages user notifications.
    """
    
    # Scanner intervals (seconds)
    SCAN_INTERVAL = 900  # 15 minutes
    
    # Score thresholds
    CRITICAL_SCORE = 80
    HIGH_SCORE = 60
    MEDIUM_SCORE = 40
    
    # Cache TTLs
    NOTIFICATION_CACHE_TTL = 300  # 5 minutes
    SCAN_LOCK_TTL = 900  # 15 minutes
    
    def __init__(self):
        self.cache = get_cache_service()
        self._scanner_task = None
        self._is_scanning = False
        
        # Lazy-loaded services
        self._api_service = None
        self._pricing_service = None
        self._decision_support = None
    
    def _get_api_service(self, user_token: str):
        """Lazy load API service with user token."""
        return create_api_service(user_token=user_token)
    
    def _get_decision_support(self, user_token: str):
        """Lazy load decision support."""
        api = self._get_api_service(user_token)
        pricing = create_pricing_service(user_token=user_token)
        return DecisionSupport(api=api, pricing=pricing, warehouse=None, recommender=None)
    
    # =========================================================
    # OPPORTUNITY DETECTORS
    # =========================================================
    
    async def _detect_low_stock(
        self, 
        user_token: str, 
        tenant_code: str,
        user_role: str
    ) -> List[Notification]:
        """Detect low stock items that need reordering."""
        notifications = []
        
        try:
            api = self._get_api_service(user_token)
            decision_support = self._get_decision_support(user_token)
            
            # Get inventory health analysis
            health = decision_support.analyze_inventory_health()
            
            if health.get("error"):
                logger.warning(f"Low stock detection failed: {health.get('error')}")
                return []
            
            # Process critical items
            for item in health.get("critical_items", [])[:5]:
                score = 95  # Critical stock = high priority
                potential_value = item.get("value", 0) or item.get("unit_price", 0) * 100
                
                notification = Notification(
                    id=str(uuid.uuid4()),
                    user_id=0,  # Will be set per user
                    user_role=user_role,
                    tenant_code=tenant_code,
                    type=NotificationType.LOW_STOCK,
                    title=f"⚠️ Critical Stock: {item.get('name', 'Unknown')}",
                    message=f"Only {item.get('available', 0):.0f} units left ({item.get('days_left', 'N/A')} days). Order immediately!",
                    message_sw=f"⚠️ Hisa Muhimu: {item.get('name', 'Unknown')} imesalia vitengo {item.get('available', 0):.0f} tu. Agiza sasa!",
                    action="View reorder recommendations",
                    action_intent="GET_REORDER_DECISIONS",
                    action_data={"item_code": item.get("code")},
                    priority=Priority.CRITICAL,
                    score=score,
                    potential_value=potential_value,
                    is_read=False,
                    created_at=datetime.now().isoformat(),
                    expires_at=(datetime.now() + timedelta(days=1)).isoformat(),
                    metadata={"item_code": item.get("code"), "current_stock": item.get("available")}
                )
                notifications.append(notification)
            
            # Process low stock items
            for item in health.get("risk_items", [])[:5]:
                score = 70
                potential_value = item.get("value", 0) or item.get("unit_price", 0) * 50
                
                notification = Notification(
                    id=str(uuid.uuid4()),
                    user_id=0,
                    user_role=user_role,
                    tenant_code=tenant_code,
                    type=NotificationType.LOW_STOCK,
                    title=f"📦 Low Stock: {item.get('name', 'Unknown')}",
                    message=f"Only {item.get('available', 0):.0f} units left. Reorder within 3-5 days.",
                    message_sw=f"📦 Hisa Chache: {item.get('name', 'Unknown')} imesalia vitengo {item.get('available', 0):.0f} tu. Agiza ndani ya siku 3-5.",
                    action="Check stock levels",
                    action_intent="GET_WAREHOUSE_STOCK",
                    action_data={"item_code": item.get("code")},
                    priority=Priority.HIGH,
                    score=score,
                    potential_value=potential_value,
                    is_read=False,
                    created_at=datetime.now().isoformat(),
                    expires_at=(datetime.now() + timedelta(days=3)).isoformat(),
                    metadata={"item_code": item.get("code"), "current_stock": item.get("available")}
                )
                notifications.append(notification)
            
            logger.info(f"🔔 Detected {len(notifications)} low stock notifications")
            
        except Exception as e:
            logger.error(f"Error in low stock detection: {e}", exc_info=True)
        
        return notifications
    
    async def _detect_churn_risk(
        self,
        user_token: str,
        tenant_code: str,
        user_role: str,
        assigned_customers: List[str] = None
    ) -> List[Notification]:
        """Detect customers at risk of churning."""
        notifications = []
        
        try:
            api = self._get_api_service(user_token)
            decision_support = self._get_decision_support(user_token)
            
            # Get all customers (or assigned only for sales reps)
            if assigned_customers:
                # For sales reps, check only assigned customers
                customers = []
                for cust_code in assigned_customers[:20]:  # Limit for performance
                    cust = api.resolve_customer(cust_code)
                    if cust:
                        customers.append(cust)
            else:
                # For managers, get top customers by value
                customers = api.get_customers(limit=50)
            
            for customer in customers[:30]:  # Limit for performance
                customer_code = customer.get("CardCode")
                customer_name = customer.get("CardName", "Unknown")
                
                # Analyze customer behavior
                behavior = decision_support.analyze_customer_behavior(customer_name)
                
                if behavior.get("error"):
                    continue
                
                # Check for churn risk
                risk_factors = behavior.get("risk_factors", [])
                days_since_last = behavior.get("purchase_patterns", {}).get("last_purchase_days_ago", 999)
                
                if days_since_last > 60 or any("churn" in f.lower() for f in risk_factors):
                    score = min(90, 50 + (days_since_last - 30))
                    potential_value = behavior.get("purchase_patterns", {}).get("avg_order_value", 10000)
                    
                    notification = Notification(
                        id=str(uuid.uuid4()),
                        user_id=0,
                        user_role=user_role,
                        tenant_code=tenant_code,
                        type=NotificationType.CHURN_RISK,
                        title=f"⚠️ Churn Risk: {customer_name}",
                        message=f"No purchase in {days_since_last} days. Send win-back offer with 10% discount.",
                        message_sw=f"⚠️ Hatari ya Kuondoka: {customer_name} hajaagiza kwa siku {days_since_last}. Tuma ofa ya kurudisha kwa punguzo la 10%.",
                        action="Create win-back quotation",
                        action_intent="CREATE_QUOTATION",
                        action_data={"customer_name": customer_name, "discount": 10},
                        priority=Priority.HIGH if days_since_last > 90 else Priority.MEDIUM,
                        score=score,
                        potential_value=potential_value,
                        is_read=False,
                        created_at=datetime.now().isoformat(),
                        expires_at=(datetime.now() + timedelta(days=7)).isoformat(),
                        metadata={"customer_code": customer_code, "days_inactive": days_since_last}
                    )
                    notifications.append(notification)
            
            logger.info(f"🔔 Detected {len(notifications)} churn risk notifications")
            
        except Exception as e:
            logger.error(f"Error in churn risk detection: {e}", exc_info=True)
        
        return notifications
    
    async def _detect_reorder_opportunities(
        self,
        user_token: str,
        tenant_code: str,
        user_role: str
    ) -> List[Notification]:
        """Detect items that need reordering based on sales velocity."""
        notifications = []
        
        try:
            decision_support = self._get_decision_support(user_token)
            
            # Get reorder decisions
            reorders = decision_support.get_reorder_decisions()
            
            if reorders.get("error"):
                return []
            
            # Process immediate orders
            for item in reorders.get("immediate_orders", [])[:5]:
                score = 85
                
                notification = Notification(
                    id=str(uuid.uuid4()),
                    user_id=0,
                    user_role=user_role,
                    tenant_code=tenant_code,
                    type=NotificationType.REORDER,
                    title=f"🔄 Reorder Needed: {item.get('name', 'Unknown')}",
                    message=f"Order {item.get('recommended_qty', 0)} units (KES {item.get('estimated_cost', 0):,.0f}). Current stock: {item.get('available', 0)} units.",
                    message_sw=f"🔄 Agiza Tena: {item.get('name', 'Unknown')}. Agiza vitengo {item.get('recommended_qty', 0)}. Hisa ya sasa: {item.get('available', 0)}.",
                    action="Create purchase order",
                    action_intent="CREATE_QUOTATION",
                    action_data={"item_code": item.get("code"), "quantity": item.get("recommended_qty")},
                    priority=Priority.CRITICAL if item.get("urgency") == "CRITICAL" else Priority.HIGH,
                    score=score,
                    potential_value=item.get("estimated_cost", 0),
                    is_read=False,
                    created_at=datetime.now().isoformat(),
                    expires_at=(datetime.now() + timedelta(days=2)).isoformat(),
                    metadata={"item_code": item.get("code"), "recommended_qty": item.get("recommended_qty")}
                )
                notifications.append(notification)
            
            logger.info(f"🔔 Detected {len(notifications)} reorder notifications")
            
        except Exception as e:
            logger.error(f"Error in reorder detection: {e}", exc_info=True)
        
        return notifications
    
    async def _detect_price_drops(
        self,
        user_token: str,
        tenant_code: str,
        user_role: str
    ) -> List[Notification]:
        """Detect significant price drops."""
        notifications = []
        
        try:
            decision_support = self._get_decision_support(user_token)
            
            # Analyze pricing opportunities
            pricing = decision_support.analyze_pricing_opportunities()
            
            if pricing.get("error"):
                return []
            
            # Process price drops
            for item in pricing.get("price_drops", [])[:5]:
                score = min(80, 50 + item.get("drop_percent", 0))
                
                notification = Notification(
                    id=str(uuid.uuid4()),
                    user_id=0,
                    user_role=user_role,
                    tenant_code=tenant_code,
                    type=NotificationType.PRICE_DROP,
                    title=f"💰 Price Drop: {item.get('name', 'Unknown')}",
                    message=f"Price dropped {item.get('drop_percent', 0)}%! Now KES {item.get('current', 0):,.0f} (was KES {item.get('avg_price', 0):,.0f}). Good time to stock up.",
                    message_sw=f"💰 Kushuka kwa Bei: {item.get('name', 'Unknown')} imeshuka kwa {item.get('drop_percent', 0)}%! Sasa KES {item.get('current', 0):,.0f}. Wakati mwema wa kununua.",
                    action="Check current price",
                    action_intent="GET_ITEM_PRICE",
                    action_data={"item_name": item.get("name")},
                    priority=Priority.MEDIUM,
                    score=score,
                    potential_value=item.get("current", 0) * 100,
                    is_read=False,
                    created_at=datetime.now().isoformat(),
                    expires_at=(datetime.now() + timedelta(days=3)).isoformat(),
                    metadata={"item_code": item.get("code"), "drop_percent": item.get("drop_percent")}
                )
                notifications.append(notification)
            
            logger.info(f"🔔 Detected {len(notifications)} price drop notifications")
            
        except Exception as e:
            logger.error(f"Error in price drop detection: {e}", exc_info=True)
        
        return notifications
    
    async def _detect_seasonal_opportunities(
        self,
        user_token: str,
        tenant_code: str,
        user_role: str
    ) -> List[Notification]:
        """Detect seasonal selling opportunities."""
        notifications = []
        
        try:
            api = self._get_api_service(user_token)
            current_month = datetime.now().month
            
            # Seasonal product categories by month
            seasonal_products = {
                3: ["seeds", "fertilizer"],      # March - Planting
                6: ["pesticide", "herbicide"],    # June - Growing
                9: ["harvesting"],                 # September - Harvest
                12: ["storage", "silo"]            # December - Storage
            }
            
            keywords = seasonal_products.get(current_month, [])
            if not keywords:
                return []
            
            # Search for relevant products
            for keyword in keywords:
                items = api.get_items(search=keyword, limit=3)
                for item in items[:3]:
                    notification = Notification(
                        id=str(uuid.uuid4()),
                        user_id=0,
                        user_role=user_role,
                        tenant_code=tenant_code,
                        type=NotificationType.SEASONAL,
                        title=f"🌱 Seasonal: {item.get('ItemName', 'Unknown')}",
                        message=f"In high demand for {datetime.now().strftime('%B')}. Run a promotion to boost sales.",
                        message_sw=f"🌱 Msimu: {item.get('ItemName', 'Unknown')} inahitajika sana mwezi wa {datetime.now().strftime('%B')}. Fanya promo kuongeza mauzo.",
                        action="Check stock levels",
                        action_intent="GET_WAREHOUSE_STOCK",
                        action_data={"item_code": item.get("ItemCode")},
                        priority=Priority.MEDIUM,
                        score=65,
                        potential_value=50000,
                        is_read=False,
                        created_at=datetime.now().isoformat(),
                        expires_at=(datetime.now() + timedelta(days=14)).isoformat(),
                        metadata={"item_code": item.get("ItemCode")}
                    )
                    notifications.append(notification)
            
            logger.info(f"🔔 Detected {len(notifications)} seasonal notifications")
            
        except Exception as e:
            logger.error(f"Error in seasonal detection: {e}", exc_info=True)
        
        return notifications
    
    # =========================================================
    # ANOMALY DETECTION (NEW)
    # =========================================================
    
    async def _detect_anomalies(
        self,
        user_token: str,
        tenant_code: str,
        user_role: str
    ) -> List[Notification]:
        """
        Detect anomalies and create notifications.
        Only for managers.
        """
        notifications = []
        
        # Only managers get anomaly alerts
        if user_role != "manager":
            return notifications
        
        try:
            from app.services.anomaly_detection_service import get_anomaly_detection_service
            
            anomaly_service = get_anomaly_detection_service()
            
            # Run anomaly scan
            results = await anomaly_service.scan_all_anomalies(
                tenant_code=tenant_code,
                user_token=user_token
            )
            
            # Process sales anomalies
            for anomaly in results.get("sales_anomalies", [])[:3]:
                notification = Notification(
                    id=anomaly.id,
                    user_id=0,
                    user_role=user_role,
                    tenant_code=tenant_code,
                    type=NotificationType.ANOMALY,
                    title=anomaly.title,
                    message=anomaly.message,
                    message_sw=anomaly.message_sw,
                    action="Investigate anomaly",
                    action_intent="GET_ANALYTICS",
                    action_data={"type": anomaly.type, "entity_code": anomaly.entity_code},
                    priority=Priority.CRITICAL if anomaly.severity == "CRITICAL" else Priority.HIGH,
                    score=anomaly.score,
                    potential_value=anomaly.potential_value,
                    is_read=False,
                    created_at=anomaly.detected_at,
                    expires_at=(datetime.now() + timedelta(days=7)).isoformat(),
                    metadata=anomaly.metadata
                )
                notifications.append(notification)
            
            # Process stock anomalies
            for anomaly in results.get("stock_anomalies", [])[:3]:
                notification = Notification(
                    id=anomaly.id,
                    user_id=0,
                    user_role=user_role,
                    tenant_code=tenant_code,
                    type=NotificationType.ANOMALY,
                    title=anomaly.title,
                    message=anomaly.message,
                    message_sw=anomaly.message_sw,
                    action="Check stock levels",
                    action_intent="GET_WAREHOUSE_STOCK",
                    action_data={"item_code": anomaly.entity_code},
                    priority=Priority.HIGH,
                    score=anomaly.score,
                    potential_value=anomaly.potential_value,
                    is_read=False,
                    created_at=anomaly.detected_at,
                    expires_at=(datetime.now() + timedelta(days=3)).isoformat(),
                    metadata=anomaly.metadata
                )
                notifications.append(notification)
            
            # Process pricing anomalies
            for anomaly in results.get("pricing_anomalies", [])[:3]:
                notification = Notification(
                    id=anomaly.id,
                    user_id=0,
                    user_role=user_role,
                    tenant_code=tenant_code,
                    type=NotificationType.ANOMALY,
                    title=anomaly.title,
                    message=anomaly.message,
                    message_sw=anomaly.message_sw,
                    action="Review pricing",
                    action_intent="GET_ITEM_PRICE",
                    action_data={"item_code": anomaly.entity_code},
                    priority=Priority.MEDIUM,
                    score=anomaly.score,
                    potential_value=anomaly.potential_value,
                    is_read=False,
                    created_at=anomaly.detected_at,
                    expires_at=(datetime.now() + timedelta(days=5)).isoformat(),
                    metadata=anomaly.metadata
                )
                notifications.append(notification)
            
            logger.info(f"🔔 Detected {len(notifications)} anomaly notifications")
            
        except Exception as e:
            logger.error(f"Error in anomaly detection: {e}", exc_info=True)
        
        return notifications
    
    # =========================================================
    # MAIN SCANNER
    # =========================================================
    
    async def scan_for_user(
        self,
        user_id: int,
        user_role: str,
        tenant_code: str,
        user_token: str,
        assigned_customers: List[str] = None
    ) -> List[Notification]:
        """
        Run all detectors for a specific user.
        Returns list of notifications for this user.
        """
        all_notifications = []
        
        try:
            # Only managers get inventory and pricing alerts
            if user_role == "manager":
                # Low stock alerts
                low_stock = await self._detect_low_stock(user_token, tenant_code, user_role)
                all_notifications.extend(low_stock)
                
                # Reorder opportunities
                reorders = await self._detect_reorder_opportunities(user_token, tenant_code, user_role)
                all_notifications.extend(reorders)
                
                # Price drops
                price_drops = await self._detect_price_drops(user_token, tenant_code, user_role)
                all_notifications.extend(price_drops)
                
                # Seasonal opportunities
                seasonal = await self._detect_seasonal_opportunities(user_token, tenant_code, user_role)
                all_notifications.extend(seasonal)
                
                # Anomaly detection (NEW)
                anomalies = await self._detect_anomalies(user_token, tenant_code, user_role)
                all_notifications.extend(anomalies)
            
            # Both managers and sales reps get churn risk for their customers
            churn_risk = await self._detect_churn_risk(
                user_token, tenant_code, user_role, assigned_customers
            )
            all_notifications.extend(churn_risk)
            
            # Set user_id for all notifications
            for notif in all_notifications:
                notif.user_id = user_id
            
            # Sort by score (highest first)
            all_notifications.sort(key=lambda x: x.score, reverse=True)
            
            # Limit to top 20 per scan
            all_notifications = all_notifications[:20]
            
            logger.info(f"✅ Scanned {len(all_notifications)} notifications for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error scanning for user {user_id}: {e}", exc_info=True)
        
        return all_notifications
    
    async def save_notifications(
        self,
        user_id: int,
        notifications: List[Notification]
    ) -> None:
        """Save notifications to cache for retrieval."""
        if not notifications:
            return
        
        # Get existing notifications
        cache_key = f"notifications:user:{user_id}"
        existing = self.cache.get_simple(cache_key) or []
        
        # Convert new notifications to dict and filter out duplicates
        new_dicts = [asdict(n) for n in notifications]
        
        # Merge with existing (newer ones first)
        all_notifs = new_dicts + existing
        # Remove duplicates by id
        seen = set()
        unique_notifs = []
        for n in all_notifs:
            if n["id"] not in seen:
                seen.add(n["id"])
                unique_notifs.append(n)
        
        # Keep only last 50 notifications
        unique_notifs = unique_notifs[:50]
        
        # Save to cache
        self.cache.set_simple(cache_key, unique_notifs, ttl=self.NOTIFICATION_CACHE_TTL)
        logger.info(f"💾 Saved {len(new_dicts)} notifications for user {user_id} (total: {len(unique_notifs)})")
    
    async def get_notifications(
        self,
        user_id: int,
        limit: int = 20,
        unread_only: bool = False
    ) -> List[Dict]:
        """Get notifications for a user."""
        cache_key = f"notifications:user:{user_id}"
        notifications = self.cache.get_simple(cache_key) or []
        
        if unread_only:
            notifications = [n for n in notifications if not n.get("is_read", False)]
        
        return notifications[:limit]
    
    async def mark_as_read(
        self,
        user_id: int,
        notification_id: str
    ) -> bool:
        """Mark a notification as read."""
        cache_key = f"notifications:user:{user_id}"
        notifications = self.cache.get_simple(cache_key) or []
        
        found = False
        for n in notifications:
            if n.get("id") == notification_id:
                n["is_read"] = True
                found = True
                break
        
        if found:
            self.cache.set_simple(cache_key, notifications, ttl=self.NOTIFICATION_CACHE_TTL)
            logger.info(f"📖 Marked notification {notification_id} as read for user {user_id}")
        
        return found
    
    async def mark_all_as_read(self, user_id: int) -> int:
        """Mark all notifications as read."""
        cache_key = f"notifications:user:{user_id}"
        notifications = self.cache.get_simple(cache_key) or []
        
        unread_count = 0
        for n in notifications:
            if not n.get("is_read", False):
                n["is_read"] = True
                unread_count += 1
        
        if unread_count > 0:
            self.cache.set_simple(cache_key, notifications, ttl=self.NOTIFICATION_CACHE_TTL)
            logger.info(f"📖 Marked {unread_count} notifications as read for user {user_id}")
        
        return unread_count
    
    async def delete_notification(
        self,
        user_id: int,
        notification_id: str
    ) -> bool:
        """Delete a notification."""
        cache_key = f"notifications:user:{user_id}"
        notifications = self.cache.get_simple(cache_key) or []
        
        original_len = len(notifications)
        notifications = [n for n in notifications if n.get("id") != notification_id]
        
        if len(notifications) != original_len:
            self.cache.set_simple(cache_key, notifications, ttl=self.NOTIFICATION_CACHE_TTL)
            logger.info(f"🗑️ Deleted notification {notification_id} for user {user_id}")
            return True
        
        return False
    
    async def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications."""
        cache_key = f"notifications:user:{user_id}"
        notifications = self.cache.get_simple(cache_key) or []
        
        return len([n for n in notifications if not n.get("is_read", False)])



_notification_service = None


def get_notification_service(user_token: str = None) -> NotificationService:
    """
    Get or create NotificationService singleton.
    
    Args:
        user_token: Optional user token for authenticated API calls
    """
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    
    # Update token if provided
    if user_token:
        _notification_service._api_service = create_api_service(user_token)
        _notification_service._pricing_service = create_pricing_service(user_token)
    
    return _notification_service