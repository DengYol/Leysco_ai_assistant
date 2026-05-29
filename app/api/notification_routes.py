"""Notification endpoints for AI routes - Phase 1 Fixed with Database Persistence"""

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from typing import Dict
import asyncio
import logging
from datetime import datetime

from .utils import utf8_json_response
from app.api.dependencies import get_conversation_context, require_manager_role
from app.services.notification_service import get_notification_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/notifications")
async def get_notifications(
    context: Dict = Depends(get_conversation_context),
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    trigger_scan: bool = Query(False),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Get proactive notifications for the current user.
    
    NEW: Notifications are loaded from database (persistent).
    
    Query parameters:
        - limit: Max notifications to return (default: 20)
        - unread_only: Only return unread notifications (default: False)
        - trigger_scan: Trigger a fresh scan (runs in background, default: False)
    """
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({
            "success": False,
            "message": "User ID not found",
            "notifications": [],
            "unread_count": 0
        })
    
    # NEW: Trigger scan in background if requested
    if trigger_scan:
        background_tasks.add_task(
            notification_service.scan_for_user,
            user_id=user_id,
            user_role=context.get("user_role", "sales_rep"),
            tenant_code=context.get("tenant_code", ""),
            user_token=context.get("_token", ""),
            assigned_customers=context.get("assigned_customers", []),
            assigned_warehouses=context.get("assigned_warehouses", [])
        )
    
    # Load notifications from database
    notifications = await notification_service.get_notifications(
        user_id=user_id,
        limit=limit,
        unread_only=unread_only
    )
    
    unread_count = await notification_service.get_unread_count(user_id)
    
    return utf8_json_response({
        "success": True,
        "notifications": notifications,
        "unread_count": unread_count,
        "total": len(notifications),
        "timestamp": datetime.utcnow().isoformat()
    })


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    context: Dict = Depends(get_conversation_context)
):
    """
    Mark a notification as read.
    
    NEW: Updates database record.
    """
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "message": "User ID not found"})
    
    success = await notification_service.mark_as_read(user_id, notification_id)
    
    return utf8_json_response({
        "success": success,
        "message": "Notification marked as read" if success else "Notification not found"
    })


@router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(
    context: Dict = Depends(get_conversation_context)
):
    """
    Mark all notifications as read for the current user.
    
    NEW: Updates all database records.
    """
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "message": "User ID not found"})
    
    count = await notification_service.mark_all_as_read(user_id)
    
    return utf8_json_response({
        "success": True,
        "message": f"Marked {count} notifications as read",
        "count": count
    })


@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    context: Dict = Depends(get_conversation_context)
):
    """
    Delete a notification.
    
    NEW: Deletes from database.
    """
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "message": "User ID not found"})
    
    success = await notification_service.delete_notification(user_id, notification_id)
    
    return utf8_json_response({
        "success": success,
        "message": "Notification deleted" if success else "Notification not found"
    })


@router.post("/notifications/scan")
async def trigger_notification_scan(
    context: Dict = Depends(require_manager_role),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Manually trigger a notification scan.
    Manager-only endpoint.
    
    NEW: Saves notifications to database after scanning.
    """
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "message": "User ID not found"})
    
    try:
        # Scan for new notifications
        notifications = await notification_service.scan_for_user(
            user_id=user_id,
            user_role=context.get("user_role", "manager"),
            tenant_code=context.get("tenant_code", ""),
            user_token=context.get("_token", ""),
            assigned_customers=context.get("assigned_customers", []),
            assigned_warehouses=context.get("assigned_warehouses", [])
        )
        
        # NEW: Save to database in background
        background_tasks.add_task(
            notification_service.save_notifications,
            user_id,
            notifications
        )
        
        return utf8_json_response({
            "success": True,
            "message": f"Scan completed. Found {len(notifications)} notifications.",
            "notifications_count": len(notifications),
            "note": "Saving to database..."
        })
        
    except Exception as e:
        logger.error(f"Error triggering notification scan: {e}")
        return utf8_json_response({
            "success": False,
            "message": f"Error during scan: {str(e)}"
        })


@router.get("/notifications/unread-count")
async def get_unread_count(
    context: Dict = Depends(get_conversation_context)
):
    """
    Get count of unread notifications.
    
    NEW: Queries database for count.
    """
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "unread_count": 0})
    
    count = await notification_service.get_unread_count(user_id)
    
    return utf8_json_response({
        "success": True,
        "unread_count": count
    })


@router.post("/notifications/cleanup")
async def trigger_cleanup(
    context: Dict = Depends(require_manager_role),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Manually trigger cleanup of expired notifications.
    Manager-only endpoint.
    
    NEW: Phase 1 Feature - Cleanup expired notifications.
    
    Notifications older than 7 days are deleted.
    """
    notification_service = get_notification_service()
    
    try:
        # Run cleanup in background
        background_tasks.add_task(
            notification_service.cleanup_expired_notifications
        )
        
        return utf8_json_response({
            "success": True,
            "message": "Cleanup started. Expired notifications will be removed.",
            "status": "processing"
        })
        
    except Exception as e:
        logger.error(f"Error triggering cleanup: {e}")
        return utf8_json_response({
            "success": False,
            "message": f"Error during cleanup: {str(e)}"
        })


@router.post("/notifications/check-escalation")
async def check_escalation(
    context: Dict = Depends(require_manager_role),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Check for critical notifications that need escalation.
    Manager-only endpoint.
    
    NEW: Phase 1 Feature - Escalate unread critical alerts to manager.
    
    If a CRITICAL alert is unread for > 2 hours, it gets escalated.
    """
    notification_service = get_notification_service()
    manager_user_id = context.get("user_id")
    
    if not manager_user_id:
        return utf8_json_response({"success": False, "message": "User ID not found"})
    
    try:
        # Run escalation check in background
        background_tasks.add_task(
            notification_service.check_escalation_needed,
            manager_user_id
        )
        
        return utf8_json_response({
            "success": True,
            "message": "Escalation check started.",
            "status": "processing"
        })
        
    except Exception as e:
        logger.error(f"Error checking escalation: {e}")
        return utf8_json_response({
            "success": False,
            "message": f"Error during escalation check: {str(e)}"
        })


# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================

@router.get("/notifications/health")
async def notifications_health(
    context: Dict = Depends(get_conversation_context)
):
    """
    Health check for notifications system.
    
    Returns:
        - Database connection status
        - Last notification count
        - System status
    """
    try:
        notification_service = get_notification_service()
        user_id = context.get("user_id")
        
        if user_id:
            unread_count = await notification_service.get_unread_count(user_id)
        else:
            unread_count = None
        
        return utf8_json_response({
            "success": True,
            "status": "healthy",
            "database": "connected",
            "unread_count": unread_count,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return utf8_json_response({
            "success": False,
            "status": "unhealthy",
            "error": str(e)
        })