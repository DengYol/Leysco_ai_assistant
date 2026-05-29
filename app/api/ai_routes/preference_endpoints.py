"""Notification Preference Endpoints - Phase 2"""

from fastapi import APIRouter, Depends, Body
from typing import Dict, Optional
import logging

from app.api.dependencies import require_manager_role
from app.services.preference_service import get_preference_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications/preferences", tags=["Notification Preferences"])


def _get_user_id(context: Dict = Depends(require_manager_role)) -> int:
    """Extract user ID from context"""
    return context.get("user_id", 1)


@router.get("")
async def get_preferences(
    user_id: int = Depends(_get_user_id)
) -> Dict:
    """
    Get user notification preferences.
    
    Returns user settings for:
    - Alert type toggles (11 types)
    - Quiet hours configuration
    - Delivery channels
    - Digest settings
    """
    try:
        service = get_preference_service()
        prefs = await service.get_preferences(user_id)
        
        logger.info(f"✅ Retrieved preferences for user {user_id}")
        
        return {
            "success": True,
            "user_id": user_id,
            "preferences": prefs
        }
    
    except Exception as e:
        logger.error(f"Error getting preferences: {e}")
        return {
            "success": False,
            "message": "Failed to retrieve preferences",
            "error": str(e)
        }


@router.patch("")
async def update_preferences(
    user_id: int = Depends(_get_user_id),
    updates: Dict = Body(...)
) -> Dict:
    """
    Update user notification preferences.
    
    Allowed fields:
    - alert_out_of_stock, alert_low_stock, alert_overdue_delivery
    - alert_slow_moving, alert_price_change, alert_customer_credit
    - alert_late_payment, alert_system, alert_reorder_point
    - alert_large_order, alert_quote_status
    - quiet_hours_enabled, quiet_start_time, quiet_end_time
    - push_enabled, email_critical, email_high, in_app_enabled
    - digest_enabled, digest_frequency, digest_time
    - minimum_priority (LOW, MEDIUM, HIGH, CRITICAL)
    
    Example:
    {
        "alert_low_stock": false,
        "quiet_hours_enabled": true,
        "quiet_start_time": "18:00",
        "digest_enabled": true
    }
    """
    try:
        service = get_preference_service()
        success = await service.update_preferences(user_id, updates)
        
        if success:
            # Get updated preferences
            prefs = await service.get_preferences(user_id)
            
            logger.info(f"✅ Updated preferences for user {user_id}")
            
            return {
                "success": True,
                "message": "Preferences updated successfully",
                "preferences": prefs
            }
        else:
            return {
                "success": False,
                "message": "Failed to update preferences"
            }
    
    except Exception as e:
        logger.error(f"Error updating preferences: {e}")
        return {
            "success": False,
            "message": "Failed to update preferences",
            "error": str(e)
        }


@router.post("/reset")
async def reset_preferences(
    user_id: int = Depends(_get_user_id)
) -> Dict:
    """Reset notification preferences to defaults."""
    try:
        service = get_preference_service()
        success = await service.reset_preferences(user_id)
        
        if success:
            logger.info(f"✅ Reset preferences for user {user_id}")
            
            return {
                "success": True,
                "message": "Preferences reset to defaults",
                "preferences": service.DEFAULT_PREFERENCES
            }
        else:
            return {
                "success": False,
                "message": "User preferences not found"
            }
    
    except Exception as e:
        logger.error(f"Error resetting preferences: {e}")
        return {
            "success": False,
            "message": "Failed to reset preferences",
            "error": str(e)
        }