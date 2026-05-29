"""Proactive notification service with database persistence - Phase 1 Fixed"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.services.leysco_api import create_api_service
from app.models import notification_models
from app.models.notification_models import (
    Notification, NotificationEscalation, NotificationAnalytics,
    UserNotificationPreference
)

logger = logging.getLogger(__name__)


class AINotification:
    """In-memory notification object (for backward compatibility with existing code)"""
    
    def __init__(self, id: str, title: str, message: str, priority: str, 
                 action: str = "", category: str = "general", icon: str = "notifications",
                 actionable: bool = True, metadata: dict = None):
        self.id = id
        self.title = title
        self.message = message
        self.priority = priority
        self.action = action
        self.category = category
        self.icon = icon
        self.actionable = actionable
        self.metadata = metadata or {}
        self.created_at = datetime.utcnow().isoformat()
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
            "is_read": self.is_read,
            "metadata": self.metadata,
        }


class NotificationService:
    """Service for generating and managing proactive notifications with database persistence"""
    
    def __init__(self):
        self.cache = {}
        self._last_scan = {}
        self.ESCALATION_THRESHOLD_HOURS = 2
    
    async def scan_for_user(
        self,
        user_id: int,
        user_role: str,
        tenant_code: str,
        user_token: str,
        assigned_customers: List[str] = None,
        assigned_warehouses: List[str] = None
    ) -> List[AINotification]:
        """Scan for notifications for a specific user (role-based filtering)"""
        notifications = []
        
        try:
            api_service = create_api_service(user_token=user_token)
            
            logger.info(f"🔍 Scanning for notifications for user {user_id} (role: {user_role})")
            
            if user_role == "sales_rep" and assigned_customers:
                logger.debug(f"Filtering for sales rep: customers={assigned_customers}")
            elif user_role == "warehouse_manager" and assigned_warehouses:
                logger.debug(f"Filtering for warehouse manager: warehouses={assigned_warehouses}")
            
            high_priority_alerts = await self._check_critical_alerts(
                api_service, user_role, assigned_customers, assigned_warehouses
            )
            notifications.extend(high_priority_alerts)
            
            medium_priority_alerts = await self._check_important_alerts(
                api_service, user_role, assigned_customers, assigned_warehouses
            )
            notifications.extend(medium_priority_alerts)
            
            low_priority_alerts = await self._check_informational_alerts(
                api_service, user_role, assigned_customers, assigned_warehouses
            )
            notifications.extend(low_priority_alerts)
            
            notifications.sort(
                key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(x.priority, 3)
            )
            
            self.cache[user_id] = notifications
            self._last_scan[user_id] = datetime.utcnow()
            
            high_count = len([n for n in notifications if n.priority == "HIGH"])
            medium_count = len([n for n in notifications if n.priority == "MEDIUM"])
            low_count = len([n for n in notifications if n.priority == "LOW"])
            
            logger.info(
                f"✅ Generated {len(notifications)} notifications for user {user_id} "
                f"(H:{high_count}, M:{medium_count}, L:{low_count})"
            )
            
        except Exception as e:
            logger.error(f"Error scanning notifications for user {user_id}: {e}", exc_info=True)
        
        return notifications
    
    async def _check_critical_alerts(
        self, api_service, user_role: str,
        assigned_customers: List[str] = None,
        assigned_warehouses: List[str] = None
    ) -> List[AINotification]:
        """Check for critical alerts - HIGH priority"""
        notifications = []
        
        try:
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
                    id=f"out_of_stock_{datetime.utcnow().timestamp()}",
                    title="🔴 CRITICAL: Items Out of Stock",
                    message=f"{len(out_of_stock)} item(s) are completely out of stock!",
                    priority="HIGH",
                    action="show low stock alerts",
                    category="alert",
                    icon="warning",
                    actionable=True,
                    metadata={"count": len(out_of_stock)}
                )
                notifications.append(notification)
            
            if critical_low:
                notification = AINotification(
                    id=f"critical_low_{datetime.utcnow().timestamp()}",
                    title="🟠 CRITICAL: Very Low Stock",
                    message=f"{len(critical_low)} item(s) have less than 10 units!",
                    priority="HIGH",
                    action="show low stock alerts",
                    category="alert",
                    icon="warning",
                    actionable=True,
                    metadata={"count": len(critical_low)}
                )
                notifications.append(notification)
            
            deliveries = api_service.get_outstanding_deliveries(limit=50)
            overdue_count = sum(1 for d in deliveries if d.get("IsOverdue", False))
            
            if overdue_count > 0:
                notification = AINotification(
                    id=f"overdue_deliveries_{datetime.utcnow().timestamp()}",
                    title="🔴 URGENT: Overdue Deliveries",
                    message=f"{overdue_count} delivery(s) are overdue!",
                    priority="HIGH",
                    action="outstanding deliveries",
                    category="delivery",
                    icon="warning",
                    actionable=True,
                    metadata={"count": overdue_count}
                )
                notifications.append(notification)
            
        except Exception as e:
            logger.error(f"Error checking critical alerts: {e}")
        
        return notifications
    
    async def _check_important_alerts(
        self, api_service, user_role: str,
        assigned_customers: List[str] = None,
        assigned_warehouses: List[str] = None
    ) -> List[AINotification]:
        """Check for important alerts - MEDIUM priority"""
        notifications = []
        
        try:
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
                    id=f"low_stock_warning_{datetime.utcnow().timestamp()}",
                    title="⚠️ Low Stock Warning",
                    message=f"{len(low_stock)} item(s) are running low (<50 units).",
                    priority="MEDIUM",
                    action="show low stock alerts",
                    category="inventory",
                    icon="inventory_2",
                    actionable=True,
                    metadata={"count": len(low_stock)}
                )
                notifications.append(notification)
            
            deliveries = api_service.get_outstanding_deliveries(limit=50)
            pending_deliveries = [d for d in deliveries if not d.get("IsOverdue", False)]
            
            if pending_deliveries:
                total_value = sum(float(d.get("LineTotal", 0)) for d in pending_deliveries)
                notification = AINotification(
                    id=f"pending_deliveries_{datetime.utcnow().timestamp()}",
                    title="🚚 Pending Deliveries",
                    message=f"{len(pending_deliveries)} delivery(s) pending.",
                    priority="MEDIUM",
                    action="outstanding deliveries",
                    category="delivery",
                    icon="local_shipping",
                    actionable=True,
                    metadata={"count": len(pending_deliveries), "total_value": total_value}
                )
                notifications.append(notification)
            
        except Exception as e:
            logger.error(f"Error checking important alerts: {e}")
        
        return notifications
    
    async def _check_informational_alerts(
        self, api_service, user_role: str,
        assigned_customers: List[str] = None,
        assigned_warehouses: List[str] = None
    ) -> List[AINotification]:
        """Check for informational alerts - LOW priority"""
        notifications = []
        
        try:
            top_items = api_service.get_top_selling_items(limit=5, days=30)
            
            if top_items:
                top_item = top_items[0]
                item_name = top_item.get("ItemName", "Unknown")
                quantity = top_item.get("quantity", 0)
                
                notification = AINotification(
                    id=f"top_seller_{datetime.utcnow().timestamp()}",
                    title="🔥 Hot Seller Alert!",
                    message=f"{item_name} is your best seller!",
                    priority="LOW",
                    action=f"price of {item_name}",
                    category="analytics",
                    icon="trending_up",
                    actionable=True,
                    metadata={"item_name": item_name, "quantity": quantity}
                )
                notifications.append(notification)
            
            notification = AINotification(
                id=f"system_health_{datetime.utcnow().timestamp()}",
                title="✅ System Status",
                message="All systems operational. AI assistant is ready!",
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
    
    # ========================================================================
    # DATABASE PERSISTENCE (Phase 1)
    # ========================================================================
    
    async def save_notifications(
        self, user_id: int, notifications: List[AINotification]
    ) -> int:
        """Save notifications to database"""
        session = None
        try:
            if notification_models.db_manager is None:
                logger.warning("Database not initialized - cannot save notifications")
                return 0
            
            session: Session = notification_models.db_manager.get_session()
            saved_count = 0
            
            for notification in notifications:
                existing = session.query(Notification).filter(
                    Notification.id == notification.id
                ).first()
                
                if existing:
                    logger.debug(f"Notification {notification.id} already exists, skipping")
                    continue
                
                db_notification = Notification(
                    id=notification.id,
                    user_id=user_id,
                    title=notification.title,
                    message=notification.message,
                    priority=notification.priority,
                    category=notification.category,
                    icon=notification.icon,
                    action=notification.action,
                    actionable=notification.actionable,
                    metadata_json=notification.metadata,
                    is_read=False,
                    created_at=datetime.utcnow(),
                    expires_at=datetime.utcnow() + timedelta(days=7),
                )
                
                session.add(db_notification)
                saved_count += 1
            
            session.commit()
            logger.info(f"✅ Saved {saved_count} notifications for user {user_id}")
            return saved_count
            
        except Exception as e:
            logger.error(f"Error saving notifications: {e}")
            if session:
                session.rollback()
            return 0
        finally:
            if session:
                session.close()
    
    async def get_notifications(
        self,
        user_id: int,
        limit: int = 20,
        unread_only: bool = False
    ) -> List[dict]:
        """Retrieve notifications from database"""
        session = None
        try:
            if notification_models.db_manager is None:
                logger.warning("Database not initialized")
                return []
            
            session: Session = notification_models.db_manager.get_session()
            
            query = session.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.expires_at > datetime.utcnow()
            )
            
            if unread_only:
                query = query.filter(Notification.is_read == False)
            
            priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            notifications = query.order_by(
                desc(Notification.created_at)
            ).limit(limit).all()
            
            notifications.sort(
                key=lambda x: (priority_order.get(x.priority, 999), -x.created_at.timestamp())
            )
            
            result = [n.to_dict() for n in notifications]
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving notifications: {e}")
            return []
        finally:
            if session:
                session.close()
    
    async def get_unread_count(self, user_id: int) -> int:
        """Get unread count"""
        session = None
        try:
            if notification_models.db_manager is None:
                return 0
            
            session: Session = notification_models.db_manager.get_session()
            
            count = session.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.is_read == False,
                Notification.expires_at > datetime.utcnow()
            ).count()
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting unread count: {e}")
            return 0
        finally:
            if session:
                session.close()
    
    async def mark_as_read(self, user_id: int, notification_id: str) -> bool:
        """Mark as read"""
        session = None
        try:
            if notification_models.db_manager is None:
                return False
            
            session: Session = notification_models.db_manager.get_session()
            
            notification = session.query(Notification).filter(
                Notification.id == notification_id,
                Notification.user_id == user_id
            ).first()
            
            if notification:
                notification.mark_as_read()
                session.commit()
                logger.info(f"✅ Marked notification {notification_id} as read")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error marking as read: {e}")
            if session:
                session.rollback()
            return False
        finally:
            if session:
                session.close()
    
    async def mark_all_as_read(self, user_id: int) -> int:
        """Mark all as read"""
        session = None
        try:
            if notification_models.db_manager is None:
                return 0
            
            session: Session = notification_models.db_manager.get_session()
            
            count = session.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.is_read == False
            ).update(
                {
                    Notification.is_read: True,
                    Notification.read_at: datetime.utcnow()
                }
            )
            
            session.commit()
            logger.info(f"✅ Marked {count} notifications as read")
            return count
            
        except Exception as e:
            logger.error(f"Error marking all as read: {e}")
            if session:
                session.rollback()
            return 0
        finally:
            if session:
                session.close()
    
    async def delete_notification(self, user_id: int, notification_id: str) -> bool:
        """Delete notification"""
        session = None
        try:
            if notification_models.db_manager is None:
                return False
            
            session: Session = notification_models.db_manager.get_session()
            
            notification = session.query(Notification).filter(
                Notification.id == notification_id,
                Notification.user_id == user_id
            ).first()
            
            if notification:
                session.delete(notification)
                session.commit()
                logger.info(f"✅ Deleted notification {notification_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting: {e}")
            if session:
                session.rollback()
            return False
        finally:
            if session:
                session.close()
    
    async def cleanup_expired_notifications(self) -> int:
        """Delete expired notifications"""
        session = None
        try:
            if notification_models.db_manager is None:
                return 0
            
            session: Session = notification_models.db_manager.get_session()
            
            count = session.query(Notification).filter(
                Notification.expires_at < datetime.utcnow()
            ).delete()
            
            session.commit()
            logger.info(f"🧹 Cleaned up {count} expired notifications")
            return count
            
        except Exception as e:
            logger.error(f"Error cleanup: {e}")
            if session:
                session.rollback()
            return 0
        finally:
            if session:
                session.close()
    
    async def check_escalation_needed(self, manager_user_id: int) -> int:
        """Check for escalations needed"""
        session = None
        try:
            if notification_models.db_manager is None:
                return 0
            
            session: Session = notification_models.db_manager.get_session()
            
            cutoff_time = datetime.utcnow() - timedelta(hours=self.ESCALATION_THRESHOLD_HOURS)
            
            unescalated = session.query(Notification).filter(
                Notification.priority == 'CRITICAL',
                Notification.is_read == False,
                Notification.created_at < cutoff_time,
                Notification.is_escalated == False
            ).all()
            
            escalated_count = 0
            
            for notification in unescalated:
                notification.mark_as_escalated(manager_user_id)
                
                escalation = NotificationEscalation(
                    id=f"esc_{notification.id}",
                    notification_id=notification.id,
                    assigned_to_user_id=notification.user_id,
                    escalated_to_user_id=manager_user_id,
                    status='escalated',
                    escalated_at=datetime.utcnow()
                )
                session.add(escalation)
                
                manager_notification = Notification(
                    id=f"escalation_{notification.id}",
                    user_id=manager_user_id,
                    title=f"🔴 ESCALATED: {notification.title}",
                    message=f"Critical alert: {notification.message}",
                    priority="CRITICAL",
                    category="escalation",
                    icon="priority_high",
                    action=notification.action,
                    metadata_json={
                        "original_notification_id": notification.id,
                        "original_user_id": notification.user_id,
                    },
                    is_read=False,
                    created_at=datetime.utcnow(),
                    expires_at=datetime.utcnow() + timedelta(days=7),
                )
                session.add(manager_notification)
                
                escalated_count += 1
            
            session.commit()
            
            if escalated_count > 0:
                logger.warning(f"⚠️ Escalated {escalated_count} notifications")
            
            return escalated_count
            
        except Exception as e:
            logger.error(f"Error checking escalation: {e}")
            if session:
                session.rollback()
            return 0
        finally:
            if session:
                session.close()


_notification_service = None


def get_notification_service() -> NotificationService:
    """Get service singleton"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service