"""Notification Analytics Endpoints - Phase 2"""

from fastapi import APIRouter, Depends, Query
from typing import Dict
import logging

from app.api.dependencies import require_manager_role
from app.services.notification_analytics_service import get_analytics_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications/analytics", tags=["Notification Analytics"])


def _get_user_id(context: Dict = Depends(require_manager_role)) -> int:
    """Extract user ID from context"""
    return context.get("user_id", 1)


@router.get("/summary")
async def get_notification_analytics_summary(
    user_id: int = Depends(_get_user_id),
    days: int = Query(30, ge=1, le=365, description="Look-back period in days")
) -> Dict:
    """
    Get notification analytics summary.
    
    Returns:
    - Total notifications in period
    - Read vs unread counts
    - Read rate percentage
    - Escalations count
    - Breakdown by priority
    - Breakdown by category
    """
    try:
        service = get_analytics_service()
        
        summary = await service.get_summary(user_id, days)
        
        logger.info(f"✅ Analytics summary for user {user_id} (last {days} days)")
        
        return {
            "success": True,
            "user_id": user_id,
            "period_days": days,
            **summary
        }
    
    except Exception as e:
        logger.error(f"Error getting analytics summary: {e}")
        return {
            "success": False,
            "message": "Failed to retrieve analytics",
            "error": str(e)
        }


@router.get("/timeline")
async def get_notification_timeline(
    user_id: int = Depends(_get_user_id),
    days: int = Query(30, ge=1, le=365),
    group_by: str = Query("day", pattern="^(day|week|month)$", description="Group by day, week, or month")
) -> Dict:
    """
    Get notification volume timeline.
    
    Shows how many notifications were created on each day/week/month.
    Useful for charting notification trends.
    """
    try:
        service = get_analytics_service()
        
        timeline = await service.get_timeline(user_id, days, group_by)
        
        logger.info(f"✅ Timeline for user {user_id} (grouped by {group_by})")
        
        return {
            "success": True,
            "user_id": user_id,
            "period_days": days,
            "group_by": group_by,
            "data_points": len(timeline),
            "timeline": timeline
        }
    
    except Exception as e:
        logger.error(f"Error getting timeline: {e}")
        return {
            "success": False,
            "message": "Failed to retrieve timeline",
            "error": str(e)
        }


@router.get("/by-category")
async def get_notifications_by_category(
    user_id: int = Depends(_get_user_id),
    days: int = Query(30, ge=1, le=365)
) -> Dict:
    """
    Get notification breakdown by category and priority.
    
    Shows which categories (inventory, delivery, pricing) have most notifications,
    further broken down by priority level.
    """
    try:
        service = get_analytics_service()
        
        by_category = await service.get_by_category(user_id, days)
        
        logger.info(f"✅ Category breakdown for user {user_id}")
        
        return {
            "success": True,
            "user_id": user_id,
            "period_days": days,
            "by_category": by_category
        }
    
    except Exception as e:
        logger.error(f"Error getting category breakdown: {e}")
        return {
            "success": False,
            "message": "Failed to retrieve category breakdown",
            "error": str(e)
        }


@router.get("/engagement")
async def get_notification_engagement(
    user_id: int = Depends(_get_user_id),
    days: int = Query(30, ge=1, le=365)
) -> Dict:
    """
    Get user engagement metrics.
    
    Returns:
    - Total notifications sent
    - Number of notifications read
    - Read rate (percentage)
    - Average time to read notification
    - Action rate (% of actionable notifications that were actioned)
    """
    try:
        service = get_analytics_service()
        
        engagement = await service.get_engagement_stats(user_id, days)
        
        logger.info(f"✅ Engagement stats for user {user_id}")
        
        return {
            "success": True,
            "user_id": user_id,
            "period_days": days,
            **engagement
        }
    
    except Exception as e:
        logger.error(f"Error getting engagement stats: {e}")
        return {
            "success": False,
            "message": "Failed to retrieve engagement stats",
            "error": str(e)
        }


@router.get("/dashboard")
async def get_notification_dashboard(
    user_id: int = Depends(_get_user_id)
) -> Dict:
    """
    Get comprehensive notification dashboard data.
    
    Combines summary, timeline, category breakdown, and engagement metrics.
    Perfect for a single dashboard API call.
    """
    try:
        service = get_analytics_service()
        
        summary = await service.get_summary(user_id, 30)
        timeline = await service.get_timeline(user_id, 30, "day")
        by_category = await service.get_by_category(user_id, 30)
        engagement = await service.get_engagement_stats(user_id, 30)
        
        logger.info(f"✅ Dashboard data for user {user_id}")
        
        return {
            "success": True,
            "user_id": user_id,
            "summary": summary,
            "timeline": timeline,
            "by_category": by_category,
            "engagement": engagement,
            "period_days": 30
        }
    
    except Exception as e:
        logger.error(f"Error getting dashboard: {e}")
        return {
            "success": False,
            "message": "Failed to retrieve dashboard data",
            "error": str(e)
        }