"""Notification endpoints for AI routes"""

from fastapi import APIRouter, Depends, Query
from typing import Dict
import asyncio
import logging

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
    trigger_scan: bool = Query(False)
):
    """
    Get proactive notifications for the current user.
    Called by Flutter app to show alerts.
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
    
    if trigger_scan:
        asyncio.create_task(
            notification_service.scan_for_user(
                user_id=user_id,
                user_role=context.get("user_role", "sales_rep"),
                tenant_code=context.get("tenant_code", ""),
                user_token=context.get("_token", ""),
                assigned_customers=context.get("assigned_customers", [])
            )
        )
    
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
        "total": len(notifications)
    })


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    context: Dict = Depends(get_conversation_context)
):
    """Mark a notification as read."""
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
    """Mark all notifications as read."""
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
    """Delete a notification."""
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
    context: Dict = Depends(require_manager_role)
):
    """
    Manually trigger a notification scan.
    Manager-only endpoint.
    """
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "message": "User ID not found"})
    
    notifications = await notification_service.scan_for_user(
        user_id=user_id,
        user_role=context.get("user_role", "manager"),
        tenant_code=context.get("tenant_code", ""),
        user_token=context.get("_token", ""),
        assigned_customers=context.get("assigned_customers", [])
    )
    
    await notification_service.save_notifications(user_id, notifications)
    
    return utf8_json_response({
        "success": True,
        "message": f"Scan completed. Found {len(notifications)} notifications.",
        "notifications_count": len(notifications)
    })


@router.get("/notifications/unread-count")
async def get_unread_count(
    context: Dict = Depends(get_conversation_context)
):
    """Get count of unread notifications."""
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "unread_count": 0})
    
    count = await notification_service.get_unread_count(user_id)
    
    return utf8_json_response({
        "success": True,
        "unread_count": count
    })