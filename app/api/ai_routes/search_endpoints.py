"""Notification Search & Filter Endpoints - Phase 2"""

from fastapi import APIRouter, Depends, Query
from typing import Dict, Optional
import logging

from app.api.dependencies import require_manager_role
from app.services.notification_search_service import get_search_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notification Search"])


def _get_user_id(context: Dict = Depends(require_manager_role)) -> int:
    """Extract user ID from context"""
    return context.get("user_id", 1)


@router.get("/search")
async def search_notifications(
    user_id: int = Depends(_get_user_id),
    q: Optional[str] = Query(None, description="Search query (title/message)"),
    priority: Optional[str] = Query(None, description="Filter by priority: CRITICAL, HIGH, MEDIUM, LOW"),
    category: Optional[str] = Query(None, description="Filter by category: inventory, delivery, pricing, etc."),
    from_date: Optional[str] = Query(None, description="Start date (ISO format: 2026-05-01)"),
    to_date: Optional[str] = Query(None, description="End date (ISO format: 2026-05-31)"),
    read_status: Optional[str] = Query(None, description="Filter by status: read, unread"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> Dict:
    """
    Search and filter notifications with advanced options.
    
    Examples:
    - GET /search?q=stock - Search for "stock" in titles/messages
    - GET /search?priority=CRITICAL - Show only critical alerts
    - GET /search?category=inventory - Show inventory alerts
    - GET /search?from_date=2026-05-01&to_date=2026-05-31 - Date range
    - GET /search?priority=HIGH&read_status=unread - Combine filters
    """
    try:
        service = get_search_service()
        
        result = await service.search(
            user_id=user_id,
            query=q,
            priority=priority,
            category=category,
            from_date=from_date,
            to_date=to_date,
            read_status=read_status,
            limit=limit,
            offset=offset
        )
        
        logger.info(
            f"✅ Search for user {user_id}: found {result.get('total_count', 0)} results "
            f"(filters: {result.get('filters', {})})"
        )
        
        return {
            "success": True,
            "user_id": user_id,
            **result
        }
    
    except Exception as e:
        logger.error(f"Error searching notifications: {e}")
        return {
            "success": False,
            "message": "Search failed",
            "error": str(e)
        }


@router.get("/categories")
async def get_notification_categories(
    user_id: int = Depends(_get_user_id)
) -> Dict:
    """
    Get all notification categories with counts.
    
    Returns list of categories (inventory, delivery, pricing, etc.)
    and how many notifications exist in each.
    """
    try:
        service = get_search_service()
        
        categories = await service.get_categories(user_id)
        
        logger.debug(f"✅ Retrieved {len(categories)} categories for user {user_id}")
        
        return {
            "success": True,
            "user_id": user_id,
            "categories": categories,
            "total_categories": len(categories)
        }
    
    except Exception as e:
        logger.error(f"Error getting categories: {e}")
        return {
            "success": False,
            "message": "Failed to retrieve categories",
            "error": str(e)
        }


@router.get("/summary")
async def get_notifications_summary(
    user_id: int = Depends(_get_user_id)
) -> Dict:
    """
    Get notification summary by priority and category.
    
    Useful for dashboard/overview pages.
    Shows counts: total, read, unread, by priority, by category.
    """
    try:
        service = get_search_service()
        
        summary = await service.get_summary(user_id)
        
        logger.debug(f"✅ Retrieved summary for user {user_id}")
        
        return {
            "success": True,
            "user_id": user_id,
            "summary": summary
        }
    
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        return {
            "success": False,
            "message": "Failed to retrieve summary",
            "error": str(e)
        }