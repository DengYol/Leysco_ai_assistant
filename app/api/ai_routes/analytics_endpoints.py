"""Analytics endpoints for AI routes (Manager only)"""

from fastapi import APIRouter, Depends, Query, Response
from typing import Dict
from datetime import datetime, timedelta
import logging

from .utils import utf8_json_response
from app.api.dependencies import require_manager_role
from app.services.activity_logger import get_activity_logger

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/analytics/summary")
async def get_analytics_summary(
    period: str = Query("today", pattern="^(today|yesterday|week|month)$"),
    context: Dict = Depends(require_manager_role)
):
    """
    Get analytics summary for the tenant.
    Manager-only endpoint.
    
    Periods: today, yesterday, week, month
    """
    activity_logger = get_activity_logger()
    tenant_code = context.get("tenant_code")
    
    if not tenant_code:
        return utf8_json_response({"success": False, "message": "Tenant code not found"})
    
    summary = await activity_logger.get_analytics_summary(tenant_code, period)
    
    return utf8_json_response({
        "success": True,
        **summary
    })


@router.get("/analytics/intents")
async def get_intent_analytics(
    days: int = Query(30, ge=1, le=90),
    context: Dict = Depends(require_manager_role)
):
    """
    Get intent distribution analytics.
    Manager-only endpoint.
    """
    activity_logger = get_activity_logger()
    tenant_code = context.get("tenant_code")
    
    if not tenant_code:
        return utf8_json_response({"success": False, "message": "Tenant code not found"})
    
    analytics = await activity_logger.get_intent_analytics(tenant_code, days)
    
    return utf8_json_response({
        "success": True,
        **analytics
    })


@router.get("/analytics/users")
async def get_user_analytics(
    days: int = Query(30, ge=1, le=90),
    context: Dict = Depends(require_manager_role)
):
    """
    Get user-level analytics.
    Manager-only endpoint.
    """
    activity_logger = get_activity_logger()
    tenant_code = context.get("tenant_code")
    
    if not tenant_code:
        return utf8_json_response({"success": False, "message": "Tenant code not found"})
    
    analytics = await activity_logger.get_user_analytics(tenant_code, days)
    
    return utf8_json_response({
        "success": True,
        **analytics
    })


@router.get("/analytics/performance")
async def get_performance_trends(
    days: int = Query(7, ge=1, le=30),
    context: Dict = Depends(require_manager_role)
):
    """
    Get performance trends over time.
    Manager-only endpoint.
    """
    activity_logger = get_activity_logger()
    tenant_code = context.get("tenant_code")
    
    if not tenant_code:
        return utf8_json_response({"success": False, "message": "Tenant code not found"})
    
    trends = await activity_logger.get_performance_trends(tenant_code, days)
    
    return utf8_json_response({
        "success": True,
        **trends
    })


@router.get("/analytics/export")
async def export_analytics(
    days: int = Query(30, ge=1, le=90),
    format: str = Query("csv", pattern="^(csv|json)$"),
    context: Dict = Depends(require_manager_role)
):
    """
    Export analytics data.
    Manager-only endpoint.
    """
    activity_logger = get_activity_logger()
    tenant_code = context.get("tenant_code")
    
    if not tenant_code:
        return utf8_json_response({"success": False, "message": "Tenant code not found"})
    
    if format == "csv":
        csv_data = await activity_logger.export_analytics_csv(tenant_code, days)
        
        return Response(
            content=csv_data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=analytics_{tenant_code}_{days}days.csv"}
        )
    else:
        recent = await activity_logger.get_recent_activity(tenant_code, limit=10000)
        
        cutoff = datetime.now() - timedelta(days=days)
        filtered = []
        for entry in recent:
            created_at = datetime.fromisoformat(entry.get("created_at", ""))
            if created_at >= cutoff:
                filtered.append(entry)
        
        return utf8_json_response({
            "success": True,
            "tenant_code": tenant_code,
            "days": days,
            "total_records": len(filtered),
            "data": filtered
        })


@router.get("/analytics/dashboard")
async def get_analytics_dashboard(
    context: Dict = Depends(require_manager_role)
):
    """
    Get all analytics data in one call for dashboard display.
    Manager-only endpoint.
    """
    activity_logger = get_activity_logger()
    tenant_code = context.get("tenant_code")
    
    if not tenant_code:
        return utf8_json_response({"success": False, "message": "Tenant code not found"})
    
    summary = await activity_logger.get_analytics_summary(tenant_code, "week")
    intents = await activity_logger.get_intent_analytics(tenant_code, 30)
    users = await activity_logger.get_user_analytics(tenant_code, 30)
    trends = await activity_logger.get_performance_trends(tenant_code, 7)
    
    return utf8_json_response({
        "success": True,
        "tenant_code": tenant_code,
        "summary": summary,
        "top_intents": intents.get("intents", [])[:10],
        "top_users": users.get("users", [])[:10],
        "performance_trends": trends.get("trends", []),
        "timestamp": datetime.now().isoformat()
    })