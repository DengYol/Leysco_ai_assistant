"""
app/api/notification_routes.py
===============================
Notification API endpoints for the Leysco AI Assistant

PRODUCTION: Added mock service fallback for testing.
            Mock service ensures notifications work even when API is unreachable.
            Added comprehensive debug logging for troubleshooting.
"""

import logging
import os
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Query, HTTPException, status

from app.api.dependencies import get_conversation_context
from app.services.notification_service import get_notification_service, NotificationService
from app.services.mock_notification_service import get_mock_notification_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_service(user_token: str):
    """
    Return the appropriate notification service.
    Uses mock service for testing or when USE_MOCK_NOTIFICATIONS is true.
    """
    # Check if we should force mock service
    force_mock = os.getenv("USE_MOCK_NOTIFICATIONS", "false").lower() == "true"
    
    if force_mock:
        logger.info("📢 Using MOCK notification service (forced by config)")
        return get_mock_notification_service()
    
    try:
        service = get_notification_service(user_token=user_token)
        # Quick test to see if service can get warehouses (indicates API connectivity)
        # For now, use mock if there's any issue
        logger.info("📢 Using REAL notification service")
        return service
    except Exception as e:
        logger.warning(f"Real notification service unavailable: {e}, using mock service")
        return get_mock_notification_service()


async def _ensure_notifications(
    service,
    user_id: int,
    user_role: str,
    tenant_code: str,
    user_token: str,
    assigned_customers: List[str],
    unread_only: bool,
    limit: int,
) -> List[Dict]:
    """
    Return cached notifications, running a fresh scan first if the
    cache is empty.  A single helper used by both GET endpoints so the
    logic is never duplicated.
    """
    logger.debug(f"🔍 _ensure_notifications called for user {user_id}")
    
    notifications = await service.get_notifications(
        user_id=user_id,
        limit=limit,
        unread_only=unread_only,
    )
    
    logger.debug(f"📬 Initial notifications from service: {len(notifications)}")

    # For mock service, always return notifications (no scan needed)
    if hasattr(service, '_notifications_cache'):
        logger.info(f"📢 Mock service: returning {len(notifications)} notifications")
        return notifications

    if not notifications:
        logger.info(
            f"🔍 Cache empty for user {user_id} — running notification scan …"
        )
        try:
            new_notifications = await service.scan_for_user(
                user_id=user_id,
                user_role=user_role,
                tenant_code=tenant_code,
                user_token=user_token,
                assigned_customers=assigned_customers,
            )

            if new_notifications:
                await service.save_notifications(user_id, new_notifications)
                # Re-fetch so unread_only / limit filters apply cleanly
                notifications = await service.get_notifications(
                    user_id=user_id,
                    limit=limit,
                    unread_only=unread_only,
                )
                logger.info(
                    f"✅ Scan produced {len(new_notifications)} notifications "
                    f"for user {user_id}"
                )
            else:
                logger.info(f"ℹ️  Scan found nothing new for user {user_id}")

        except Exception as e:
            logger.error(
                f"❌ Scan failed for user {user_id}: {e}", exc_info=True
            )
    else:
        logger.debug(f"📬 Using cached notifications: {len(notifications)} items")

    return notifications


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def get_notifications(
    context: Dict = Depends(get_conversation_context),
    unread_only: bool = Query(False, description="Only return unread notifications"),
    limit: int = Query(20, ge=1, le=100, description="Max notifications to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> Dict[str, Any]:
    """
    Get notifications for the authenticated user.

    • First call (empty cache): runs a full scan then returns results.
    • Subsequent calls within the cache TTL: returns cached results instantly.
    • After TTL expires: next call triggers a new scan automatically.
    """
    user_id = context.get("user_id")
    user_role = context.get("user_role", "sales_rep")
    tenant_code = context.get("tenant_code", "TEST001")
    user_token = context.get("_token")
    assigned_customers = context.get("assigned_customers", [])

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    logger.info(
        f"🔔 GET /notifications — user={user_id} role={user_role} "
        f"unread_only={unread_only}"
    )

    service = _get_service(user_token)

    notifications = await _ensure_notifications(
        service=service,
        user_id=user_id,
        user_role=user_role,
        tenant_code=tenant_code,
        user_token=user_token,
        assigned_customers=assigned_customers,
        unread_only=unread_only,
        limit=limit + offset,  # fetch enough to paginate
    )

    # Unread count always comes from the full (non-filtered) cache so the
    # badge number is accurate regardless of what the caller filtered.
    try:
        unread_count = await service.get_unread_count(user_id)
        logger.debug(f"🔢 Unread count from service: {unread_count}")
    except Exception as e:
        logger.error(f"Error reading unread count: {e}")
        unread_count = len([n for n in notifications if not n.get("is_read")])
        logger.debug(f"🔢 Unread count calculated from notifications: {unread_count}")

    total = len(notifications)
    paginated = notifications[offset: offset + limit]

    logger.info(
        f"✅ Returning {len(paginated)}/{total} notifications "
        f"(unread: {unread_count}) for user {user_id}"
    )

    # Log first notification preview for debugging
    if paginated:
        first_notif = paginated[0]
        logger.debug(f"📬 First notification preview: id={first_notif.get('id')}, type={first_notif.get('type')}, title={first_notif.get('title')}")

    return {
        "notifications": paginated,
        "total": total,
        "unread_count": unread_count,
        "limit": limit,
        "offset": offset,
    }


@router.get("/unread-count")
async def get_unread_count(
    context: Dict = Depends(get_conversation_context),
) -> Dict[str, int]:
    """
    Lightweight endpoint for the bell-badge.

    Triggers a scan on first call (empty cache) so the badge is populated
    even before the user opens the notifications panel.
    """
    user_id = context.get("user_id")
    if not user_id:
        logger.debug("No user_id in context, returning 0")
        return {"unread_count": 0}

    user_token = context.get("_token")
    user_role = context.get("user_role", "sales_rep")
    tenant_code = context.get("tenant_code", "TEST001")
    assigned_customers = context.get("assigned_customers", [])

    logger.debug(f"🔔 GET /unread-count — user={user_id}, role={user_role}")

    service = _get_service(user_token)

    # Piggy-back on _ensure_notifications so a scan runs if the cache is cold.
    # We don't need the list itself here — just the side-effect of populating
    # the cache so get_unread_count() returns a real number.
    try:
        await _ensure_notifications(
            service=service,
            user_id=user_id,
            user_role=user_role,
            tenant_code=tenant_code,
            user_token=user_token,
            assigned_customers=assigned_customers,
            unread_only=False,
            limit=20,
        )
        unread_count = await service.get_unread_count(user_id)
        logger.debug(f"🔢 Unread count result: {unread_count}")
    except Exception as e:
        logger.error(f"Error in unread-count: {e}", exc_info=True)
        unread_count = 0

    return {"unread_count": unread_count}


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    context: Dict = Depends(get_conversation_context),
) -> Dict[str, Any]:
    """Mark a specific notification as read."""
    user_id = context.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    logger.info(f"📖 Marking notification {notification_id} as read for user {user_id}")

    service = _get_service(context.get("_token"))

    try:
        success = await service.mark_as_read(user_id, notification_id)
        if success:
            logger.info(f"✅ Notification {notification_id} marked as read")
        else:
            logger.warning(f"⚠️ Notification {notification_id} not found")
    except Exception as e:
        logger.error(f"Error marking notification read: {e}", exc_info=True)
        success = False

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found",
        )

    return {"success": True, "message": "Notification marked as read"}


@router.post("/mark-all-read")
async def mark_all_notifications_read(
    context: Dict = Depends(get_conversation_context),
) -> Dict[str, Any]:
    """Mark all notifications for the current user as read."""
    user_id = context.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    logger.info(f"📖 Marking all notifications as read for user {user_id}")

    service = _get_service(context.get("_token"))

    try:
        count = await service.mark_all_as_read(user_id)
        logger.info(f"✅ Marked {count} notifications as read")
    except Exception as e:
        logger.error(f"Error marking all read: {e}", exc_info=True)
        count = 0

    return {
        "success": True,
        "count": count,
        "message": f"Marked {count} notifications as read",
    }


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    context: Dict = Depends(get_conversation_context),
) -> Dict[str, Any]:
    """Delete a specific notification."""
    user_id = context.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    logger.info(f"🗑️ Deleting notification {notification_id} for user {user_id}")

    service = _get_service(context.get("_token"))

    try:
        success = await service.delete_notification(user_id, notification_id)
        if success:
            logger.info(f"✅ Notification {notification_id} deleted")
        else:
            logger.warning(f"⚠️ Notification {notification_id} not found")
    except Exception as e:
        logger.error(f"Error deleting notification: {e}", exc_info=True)
        success = False

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found",
        )

    return {"success": True, "message": "Notification deleted"}


@router.post("/refresh")
async def refresh_notifications(
    context: Dict = Depends(get_conversation_context),
) -> Dict[str, Any]:
    """
    Force a fresh notification scan, bypassing the cache.

    Useful for a manual pull-to-refresh gesture in the app.
    The old cached notifications are replaced with the new scan results.
    """
    user_id = context.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user_token = context.get("_token")
    user_role = context.get("user_role", "sales_rep")
    tenant_code = context.get("tenant_code", "TEST001")
    assigned_customers = context.get("assigned_customers", [])

    logger.info(f"🔄 Manual refresh requested for user {user_id}")

    service = _get_service(user_token)

    try:
        notifications = await service.scan_for_user(
            user_id=user_id,
            user_role=user_role,
            tenant_code=tenant_code,
            user_token=user_token,
            assigned_customers=assigned_customers,
        )
        await service.save_notifications(user_id, notifications)

        logger.info(
            f"🔄 Manual refresh: {len(notifications)} notifications "
            f"saved for user {user_id}"
        )
        
        # Log notification types for debugging
        notif_types = {}
        for n in notifications:
            t = n.get("type", "UNKNOWN")
            notif_types[t] = notif_types.get(t, 0) + 1
        logger.debug(f"📊 Notification types after refresh: {notif_types}")
        
        return {
            "success": True,
            "count": len(notifications),
            "message": f"Refreshed {len(notifications)} notifications",
        }

    except Exception as e:
        logger.error(f"Error refreshing notifications: {e}", exc_info=True)
        return {
            "success": False,
            "count": 0,
            "message": f"Refresh failed: {str(e)}",
        }


# =========================================================
# FORCE SCAN ENDPOINT - Manually trigger notification generation
# =========================================================

@router.post("/force-scan")
async def force_notification_scan(
    context: Dict = Depends(get_conversation_context),
) -> Dict[str, Any]:
    """
    Force a notification scan and immediately return results.
    Useful for testing and debugging.
    """
    user_id = context.get("user_id")
    user_role = context.get("user_role", "sales_rep")
    tenant_code = context.get("tenant_code", "TEST001")
    user_token = context.get("_token")
    assigned_customers = context.get("assigned_customers", [])
    
    if not user_id:
        return {"success": False, "message": "User ID not found"}
    
    logger.info(f"🚀 Force scan requested for user {user_id}")
    
    service = _get_service(user_token)
    
    try:
        # Force scan
        notifications = await service.scan_for_user(
            user_id=user_id,
            user_role=user_role,
            tenant_code=tenant_code,
            user_token=user_token,
            assigned_customers=assigned_customers
        )
        
        # Save to cache
        await service.save_notifications(user_id, notifications)
        
        # Get unread count
        unread_count = await service.get_unread_count(user_id)
        
        logger.info(f"✅ Force scan complete: {len(notifications)} notifications generated, {unread_count} unread")
        
        return {
            "success": True,
            "count": len(notifications),
            "unread_count": unread_count,
            "message": f"Generated {len(notifications)} notifications",
            "notifications": notifications[:5]  # Show first 5 for preview
        }
        
    except Exception as e:
        logger.error(f"Force scan failed: {e}", exc_info=True)
        return {
            "success": False,
            "count": 0,
            "message": f"Scan failed: {str(e)}"
        }


# =========================================================
# DEBUG ENDPOINT - Comprehensive troubleshooting
# =========================================================

@router.get("/debug")
async def debug_notifications(
    context: Dict = Depends(get_conversation_context),
) -> Dict[str, Any]:
    """
    Comprehensive debug endpoint to check notification service status.
    Shows service availability, mock notifications, and real service status.
    """
    user_id = context.get("user_id")
    user_role = context.get("user_role", "sales_rep")
    user_token = context.get("_token")
    
    logger.info(f"🔍 DEBUG: Checking notifications for user {user_id} (role: {user_role})")
    
    result = {
        "user_id": user_id,
        "user_role": user_role,
        "token_preview": user_token[:20] + "..." if user_token and len(user_token) > 20 else str(user_token)[:20],
        "services_available": {},
        "notifications": [],
        "mock_notifications": [],
        "error": None,
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }
    
    # Check force_mock config
    force_mock = os.getenv("USE_MOCK_NOTIFICATIONS", "false").lower() == "true"
    result["config_force_mock"] = force_mock
    logger.info(f"🔍 USE_MOCK_NOTIFICATIONS config: {force_mock}")
    
    # Check mock notification service
    try:
        from app.services.mock_notification_service import get_mock_notification_service
        mock_service = get_mock_notification_service()
        result["services_available"]["mock_service"] = True
        
        # Get mock notifications
        mock_notifs = await mock_service.get_notifications(user_id=user_id, limit=10)
        result["mock_notifications"] = mock_notifs[:5]
        result["mock_notifications_count"] = len(mock_notifs)
        result["mock_unread_count"] = await mock_service.get_unread_count(user_id)
        
        logger.info(f"📬 DEBUG: Found {len(mock_notifs)} mock notifications, {result['mock_unread_count']} unread")
        
    except Exception as e:
        result["services_available"]["mock_service"] = False
        result["mock_service_error"] = str(e)
        logger.error(f"❌ DEBUG: Mock service error: {e}")
    
    # Check real notification service
    try:
        real_service = get_notification_service(user_token=user_token)
        result["services_available"]["real_service"] = True
        
        # Try to get notifications from real service
        real_notifs = await real_service.get_notifications(user_id=user_id, limit=10)
        result["real_notifications_count"] = len(real_notifs)
        result["real_unread_count"] = await real_service.get_unread_count(user_id)
        result["real_notifications"] = real_notifs[:3]
        
        logger.info(f"📬 DEBUG: Found {len(real_notifs)} real notifications, {result['real_unread_count']} unread")
        
    except Exception as e:
        result["services_available"]["real_service"] = False
        result["real_service_error"] = str(e)
        logger.error(f"❌ DEBUG: Real service error: {e}")
    
    # Determine which service is actually being used
    if force_mock:
        result["service_used"] = "mock (forced by config)"
        result["notifications"] = result["mock_notifications"]
        result["notifications_count"] = result.get("mock_notifications_count", 0)
        result["unread_count"] = result.get("mock_unread_count", 0)
    elif result["services_available"].get("real_service"):
        result["service_used"] = "real"
        result["notifications"] = result.get("real_notifications", [])
        result["notifications_count"] = result.get("real_notifications_count", 0)
        result["unread_count"] = result.get("real_unread_count", 0)
    else:
        result["service_used"] = "mock (fallback)"
        result["notifications"] = result["mock_notifications"]
        result["notifications_count"] = result.get("mock_notifications_count", 0)
        result["unread_count"] = result.get("mock_unread_count", 0)
    
    logger.info(f"📬 DEBUG FINAL: Using {result['service_used']}, {result['notifications_count']} notifications, {result['unread_count']} unread")
    
    return result


# =========================================================
# STATUS ENDPOINT - Quick health check for notifications
# =========================================================

@router.get("/status")
async def notification_status(
    context: Dict = Depends(get_conversation_context),
) -> Dict[str, Any]:
    """
    Quick status endpoint to check if notification service is working.
    Returns minimal info for health checks.
    """
    user_id = context.get("user_id")
    
    if not user_id:
        return {"status": "error", "message": "No user ID"}
    
    force_mock = os.getenv("USE_MOCK_NOTIFICATIONS", "false").lower() == "true"
    
    return {
        "status": "ok",
        "user_id": user_id,
        "force_mock": force_mock,
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }

# =========================================================
# PUBLIC DEBUG ENDPOINT - No auth required for testing
# =========================================================

@router.get("/debug-public")
async def debug_notifications_public():
    """
    Public debug endpoint - no authentication required.
    Useful for testing mock notifications without a token.
    """
    from app.services.mock_notification_service import get_mock_notification_service
    from datetime import datetime
    
    logger.info("🔍 DEBUG PUBLIC: Checking mock notifications")
    
    result = {
        "service": "mock_notification_service",
        "mock_notifications": [],
        "mock_notifications_count": 0,
        "mock_unread_count": 0,
        "config_force_mock": os.getenv("USE_MOCK_NOTIFICATIONS", "false").lower() == "true",
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        mock_service = get_mock_notification_service()
        
        # Try with user_id = 1 (default test user)
        mock_notifs = await mock_service.get_notifications(user_id=1, limit=10)
        
        result["mock_notifications"] = mock_notifs[:5]
        result["mock_notifications_count"] = len(mock_notifs)
        result["mock_unread_count"] = await mock_service.get_unread_count(1)
        
        logger.info(f"📬 PUBLIC DEBUG: Found {len(mock_notifs)} mock notifications, {result['mock_unread_count']} unread")
        
        if mock_notifs:
            result["sample_notification"] = {
                "id": mock_notifs[0].get("id"),
                "type": mock_notifs[0].get("type"),
                "title": mock_notifs[0].get("title"),
                "message": mock_notifs[0].get("message"),
                "priority": mock_notifs[0].get("priority"),
                "is_read": mock_notifs[0].get("is_read")
            }
        
    except Exception as e:
        result["error"] = str(e)
        result["traceback"] = __import__('traceback').format_exc()
        logger.error(f"❌ PUBLIC DEBUG Error: {e}")
    
    return result


# =========================================================
# SIMPLE MOCK NOTIFICATIONS ENDPOINT - Returns hardcoded data
# =========================================================

@router.get("/mock")
async def get_mock_notifications_simple():
    """
    Simple endpoint that returns hardcoded mock notifications.
    No authentication required - useful for testing the UI.
    """
    from datetime import datetime, timedelta
    
    now = datetime.now()
    
    mock_notifications = [
        {
            "id": "mock_1",
            "type": "LOW_STOCK",
            "title": "⚠️ Critical Stock Alert - Vegimax 250ml",
            "message": "Only 15 units left! This item sells 5 units per day. Order immediately.",
            "message_sw": "⚠️ Tahadhari - Vegimax 250ml imesalia vitengo 15 tu! Agiza sasa.",
            "action": "Create Reorder",
            "action_intent": "CREATE_QUOTATION",
            "action_data": {"item_name": "Vegimax 250ml", "quantity": 50},
            "priority": "CRITICAL",
            "score": 95,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
        },
        {
            "id": "mock_2",
            "type": "CHURN_RISK",
            "title": "👥 Customer Churn Risk - Magomano Suppliers",
            "message": "No purchase in 65 days (last order KES 45,000). Send win-back offer with 10% discount.",
            "message_sw": "👥 Hatari - Magomano Suppliers hajaweka oda kwa siku 65.",
            "action": "Contact Customer",
            "action_intent": "GET_CUSTOMER_DETAILS",
            "action_data": {"customer_name": "Magomano Suppliers"},
            "priority": "HIGH",
            "score": 85,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=3)).isoformat(),
        },
        {
            "id": "mock_3",
            "type": "REORDER",
            "title": "🚚 OVERDUE Delivery - #DEL-2024-001",
            "message": "Delivery to Nairobi Warehouse is 3 days overdue. Customer waiting for 500 units.",
            "message_sw": "🚚 Usafirishaji Umechelewa - kwa Ghala la Nairobi umechelewa kwa siku 3.",
            "action": "Track Delivery",
            "action_intent": "TRACK_DELIVERY",
            "action_data": {"delivery_number": "DEL-2024-001"},
            "priority": "CRITICAL",
            "score": 98,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=12)).isoformat(),
        },
        {
            "id": "mock_4",
            "type": "PRICE_DROP",
            "title": "💰 Price Drop - Easeed 1kg",
            "message": "Price dropped by 15%! Now KES 850 (was KES 1000). Good time to stock up.",
            "message_sw": "💰 Bei Imeshuka - Easeed 1kg sasa KES 850.",
            "action": "Check Price",
            "action_intent": "GET_ITEM_PRICE",
            "action_data": {"item_name": "Easeed 1kg"},
            "priority": "MEDIUM",
            "score": 70,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=5)).isoformat(),
        },
        {
            "id": "mock_5",
            "type": "SEASONAL",
            "title": "🌱 Planting Season Special",
            "message": "Planting season starts in 2 weeks. Prepare inventory and run promotions now!",
            "message_sw": "🌱 Msimu wa Kupanda - Maandalizi ya msimu.",
            "action": "View Products",
            "action_intent": "GET_ITEMS",
            "action_data": {"item_name": "seeds"},
            "priority": "MEDIUM",
            "score": 75,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=14)).isoformat(),
        },
        {
            "id": "mock_6",
            "type": "UPSELL",
            "title": "📈 Upsell Opportunity",
            "message": "15 customers who bought Vegimax 250ml might be interested in Vegimax 500ml.",
            "message_sw": "📈 Fursa ya Kuuza Zaidi - Wateja wanaweza kupendezwa na Vegimax 500ml.",
            "action": "View Customers",
            "action_intent": "FIND_CUSTOMERS_BY_ITEM",
            "action_data": {"item_name": "Vegimax"},
            "priority": "LOW",
            "score": 60,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=7)).isoformat(),
        },
        {
            "id": "mock_7",
            "type": "REORDER",
            "title": "📊 Inventory Health Check",
            "message": "Inventory turnover dropped 12% this month. 8 items overstocked (>90 days).",
            "message_sw": "📊 Ukaguzi wa Afya ya Hisa - Kiwango cha mzunguko kimepungua.",
            "action": "View Inventory Health",
            "action_intent": "ANALYZE_INVENTORY_HEALTH",
            "action_data": {},
            "priority": "MEDIUM",
            "score": 80,
            "is_read": False,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=5)).isoformat(),
        },
    ]
    
    unread_count = len([n for n in mock_notifications if not n.get("is_read")])
    
    return {
        "success": True,
        "service": "simple_mock",
        "total": len(mock_notifications),
        "unread_count": unread_count,
        "notifications": mock_notifications
    }