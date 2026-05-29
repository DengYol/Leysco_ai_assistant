"""
User Notification Preferences Service - Phase 2
================================================
Manages user notification settings: quiet hours, digests, channels, alert types.

Database: PostgreSQL
ORM: SQLAlchemy
Table: UserNotificationPreference (created in Phase 1)
"""

import logging
from typing import Dict, Optional
from datetime import datetime, time
from sqlalchemy.orm import Session

from app.models import notification_models
from app.models.notification_models import UserNotificationPreference

logger = logging.getLogger(__name__)


class PreferenceService:
    """Service for managing user notification preferences"""
    
    # Default preferences for new users
    DEFAULT_PREFERENCES = {
        # Alert toggles (which types to receive)
        "alert_out_of_stock": True,
        "alert_low_stock": True,
        "alert_overdue_delivery": True,
        "alert_slow_moving": False,
        "alert_price_change": True,
        "alert_customer_credit": True,
        "alert_late_payment": True,
        "alert_system": True,
        "alert_reorder_point": True,
        "alert_large_order": True,
        "alert_quote_status": True,
        
        # Quiet hours (don't show notifications)
        "quiet_hours_enabled": False,
        "quiet_start_time": "18:00",  # 6 PM
        "quiet_end_time": "09:00",    # 9 AM
        
        # Delivery channels
        "push_enabled": True,
        "email_critical": True,
        "email_high": False,
        "in_app_enabled": True,
        
        # Digest settings
        "digest_enabled": False,
        "digest_frequency": "daily",  # daily, weekly
        "digest_time": "09:00",       # Send at 9 AM
        
        # Priority filter - only show these priorities
        "minimum_priority": "LOW",    # Show all: LOW, MEDIUM, HIGH, CRITICAL
    }
    
    def __init__(self):
        logger.info("✅ PreferenceService initialized")
    
    async def get_preferences(self, user_id: int) -> Dict:
        """Get user notification preferences"""
        session = None
        try:
            if notification_models.db_manager is None:
                logger.warning("Database not initialized")
                return self.DEFAULT_PREFERENCES.copy()
            
            session: Session = notification_models.db_manager.get_session()
            
            # Try to load existing preferences
            prefs = session.query(UserNotificationPreference).filter(
                UserNotificationPreference.user_id == user_id
            ).first()
            
            if prefs:
                result = {
                    "user_id": user_id,
                    "alert_out_of_stock": prefs.alert_out_of_stock,
                    "alert_low_stock": prefs.alert_low_stock,
                    "alert_overdue_delivery": prefs.alert_overdue_delivery,
                    "alert_slow_moving": prefs.alert_slow_moving,
                    "alert_price_change": prefs.alert_price_change,
                    "alert_customer_credit": prefs.alert_customer_credit,
                    "alert_late_payment": prefs.alert_late_payment,
                    "alert_system": prefs.alert_system,
                    "alert_reorder_point": prefs.alert_reorder_point,
                    "alert_large_order": prefs.alert_large_order,
                    "alert_quote_status": prefs.alert_quote_status,
                    "quiet_hours_enabled": prefs.quiet_hours_enabled,
                    "quiet_start_time": prefs.quiet_start_time,
                    "quiet_end_time": prefs.quiet_end_time,
                    "push_enabled": prefs.push_enabled,
                    "email_critical": prefs.email_critical,
                    "email_high": prefs.email_high,
                    "in_app_enabled": prefs.in_app_enabled,
                    "digest_enabled": prefs.digest_enabled,
                    "digest_frequency": prefs.digest_frequency,
                    "digest_time": prefs.digest_time,
                    "minimum_priority": prefs.minimum_priority,
                    "created_at": prefs.created_at.isoformat() if prefs.created_at else None,
                    "updated_at": prefs.updated_at.isoformat() if prefs.updated_at else None,
                }
                logger.debug(f"✅ Loaded preferences for user {user_id}")
                return result
            else:
                # Create default preferences for new user
                logger.info(f"Creating default preferences for user {user_id}")
                await self.create_default_preferences(user_id, session)
                return {"user_id": user_id, **self.DEFAULT_PREFERENCES}
            
        except Exception as e:
            logger.error(f"Error getting preferences: {e}")
            return {"user_id": user_id, **self.DEFAULT_PREFERENCES}
        finally:
            if session:
                session.close()
    
    async def create_default_preferences(self, user_id: int, session: Session = None) -> bool:
        """Create default preferences for a new user"""
        should_close = False
        try:
            if notification_models.db_manager is None:
                return False
            
            if session is None:
                session = notification_models.db_manager.get_session()
                should_close = True
            
            # Check if already exists
            existing = session.query(UserNotificationPreference).filter(
                UserNotificationPreference.user_id == user_id
            ).first()
            
            if existing:
                return True
            
            # Create with defaults
            prefs = UserNotificationPreference(
                user_id=user_id,
                alert_out_of_stock=True,
                alert_low_stock=True,
                alert_overdue_delivery=True,
                alert_slow_moving=False,
                alert_price_change=True,
                alert_customer_credit=True,
                alert_late_payment=True,
                alert_system=True,
                alert_reorder_point=True,
                alert_large_order=True,
                alert_quote_status=True,
                quiet_hours_enabled=False,
                quiet_start_time="18:00",
                quiet_end_time="09:00",
                push_enabled=True,
                email_critical=True,
                email_high=False,
                in_app_enabled=True,
                digest_enabled=False,
                digest_frequency="daily",
                digest_time="09:00",
            )
            
            session.add(prefs)
            session.commit()
            logger.info(f"✅ Created default preferences for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating default preferences: {e}")
            if session:
                session.rollback()
            return False
        finally:
            if should_close and session:
                session.close()
    
    async def update_preferences(self, user_id: int, updates: Dict) -> bool:
        """Update user notification preferences"""
        session = None
        try:
            if notification_models.db_manager is None:
                return False
            
            session: Session = notification_models.db_manager.get_session()
            
            prefs = session.query(UserNotificationPreference).filter(
                UserNotificationPreference.user_id == user_id
            ).first()
            
            if not prefs:
                # Create with updates
                prefs = UserNotificationPreference(user_id=user_id)
                session.add(prefs)
            
            # Apply updates
            allowed_fields = {
                "alert_out_of_stock", "alert_low_stock", "alert_overdue_delivery",
                "alert_slow_moving", "alert_price_change", "alert_customer_credit",
                "alert_late_payment", "alert_system", "alert_reorder_point",
                "alert_large_order", "alert_quote_status",
                "quiet_hours_enabled", "quiet_start_time", "quiet_end_time",
                "push_enabled", "email_critical", "email_high", "in_app_enabled",
                "digest_enabled", "digest_frequency", "digest_time", "minimum_priority"
            }
            
            for key, value in updates.items():
                if key in allowed_fields and hasattr(prefs, key):
                    setattr(prefs, key, value)
                    logger.debug(f"Set {key} = {value}")
            
            prefs.updated_at = datetime.utcnow()
            session.commit()
            logger.info(f"✅ Updated preferences for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating preferences: {e}")
            if session:
                session.rollback()
            return False
        finally:
            if session:
                session.close()
    
    async def reset_preferences(self, user_id: int) -> bool:
        """Reset preferences to defaults"""
        session = None
        try:
            if notification_models.db_manager is None:
                return False
            
            session: Session = notification_models.db_manager.get_session()
            
            prefs = session.query(UserNotificationPreference).filter(
                UserNotificationPreference.user_id == user_id
            ).first()
            
            if prefs:
                # Apply defaults
                for key, value in self.DEFAULT_PREFERENCES.items():
                    if hasattr(prefs, key):
                        setattr(prefs, key, value)
                
                prefs.updated_at = datetime.utcnow()
                session.commit()
                logger.info(f"✅ Reset preferences for user {user_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error resetting preferences: {e}")
            if session:
                session.rollback()
            return False
        finally:
            if session:
                session.close()
    
    def should_filter_by_quiet_hours(self, user_id: int, prefs: Dict) -> bool:
        """Check if current time is in quiet hours"""
        if not prefs.get("quiet_hours_enabled"):
            return False
        
        try:
            start_time_str = prefs.get("quiet_start_time", "18:00")
            end_time_str = prefs.get("quiet_end_time", "09:00")
            
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            current_time = datetime.utcnow().time()
            
            # Handle case where quiet hours cross midnight
            if start_time <= end_time:
                # e.g., 8 AM to 5 PM
                return start_time <= current_time <= end_time
            else:
                # e.g., 6 PM to 9 AM (crosses midnight)
                return current_time >= start_time or current_time <= end_time
        
        except Exception as e:
            logger.error(f"Error checking quiet hours: {e}")
            return False
    
    def apply_preferences_filter(self, notifications: list, prefs: Dict) -> list:
        """
        Filter notifications based on user preferences.
        
        Applies:
        - Alert type filters (which types are enabled)
        - Quiet hours (don't show during quiet hours)
        - Priority filter (only show certain priorities)
        """
        filtered = []
        
        for notif in notifications:
            # Check priority filter
            min_priority = prefs.get("minimum_priority", "LOW")
            priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            if priority_order.get(notif.get("priority"), 999) > priority_order.get(min_priority, 999):
                continue
            
            # Check category-based toggles
            category = notif.get("category", "general").lower()
            
            alert_type_map = {
                "alert": "alert_out_of_stock",
                "inventory": "alert_low_stock",
                "delivery": "alert_overdue_delivery",
                "pricing": "alert_price_change",
                "credit": "alert_customer_credit",
                "payment": "alert_late_payment",
                "system": "alert_system",
                "reorder": "alert_reorder_point",
                "customer": "alert_large_order",
                "quote": "alert_quote_status",
            }
            
            pref_key = alert_type_map.get(category)
            if pref_key and not prefs.get(pref_key, True):
                continue
            
            # Check quiet hours
            if self.should_filter_by_quiet_hours(notif.get("user_id"), prefs):
                # Still show CRITICAL even during quiet hours
                if notif.get("priority") != "CRITICAL":
                    continue
            
            filtered.append(notif)
        
        return filtered


# Global preference service instance
_preference_service = None


def get_preference_service() -> PreferenceService:
    """Get preference service singleton"""
    global _preference_service
    if _preference_service is None:
        _preference_service = PreferenceService()
    return _preference_service