"""Dashboard, cache, and performance endpoints for AI routes"""

from fastapi import APIRouter, Depends, Query
from typing import Optional, Dict, Any
import logging

from .utils import utf8_json_response
from app.services.dashboard_service import get_dashboard_service
from app.services.cache_service import get_cache_service
from app.services.session_context import session_ctx
from app.services.performance_monitor import performance_monitor
from app.api.dependencies import get_conversation_context

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/dashboard")
def get_dashboard() -> Dict[str, Any]:
    """Get dashboard statistics."""
    svc = get_dashboard_service()
    return svc.get_dashboard()


@router.get("/cache/stats")
def cache_stats():
    """Get cache statistics."""
    return get_cache_service().get_stats()


@router.post("/cache/clear")
def cache_clear(
    intent: Optional[str] = None, 
    session_id: Optional[str] = None,
    context: Dict = Depends(get_conversation_context)
):
    """
    Clear cache - can clear by intent, session, or entire cache.
    """
    cache = get_cache_service()
    if session_id:
        session_ctx.clear(session_id)
        logger.info(f"Session cleared: {session_id}")
    if intent:
        cache.invalidate_intent(intent.upper())
        return {"message": f"Cleared cache for intent: {intent}"}
    cache.clear()
    return {"message": "Cleared entire cache"}


@router.get("/performance/stats")
def performance_stats():
    """Get performance monitoring statistics."""
    return performance_monitor.get_stats()