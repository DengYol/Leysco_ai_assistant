"""Feedback loop endpoints for AI routes"""

from fastapi import APIRouter, Depends, Query
from typing import Dict
import logging

from .utils import utf8_json_response
from app.api.dependencies import get_conversation_context, require_manager_role
from app.services.feedback_service import get_feedback_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/feedback/suggestion-clicked")
async def track_suggestion_click(
    suggestion: str,
    intent: str,
    session_id: str,
    context: Dict = Depends(get_conversation_context)
):
    """
    Track when a user clicks a suggestion chip.
    Called by Flutter app to provide feedback.
    """
    feedback_service = get_feedback_service()
    user_id = context.get("user_id")
    tenant_code = context.get("tenant_code")
    
    if not user_id or not tenant_code:
        return utf8_json_response({"success": False, "message": "User or tenant not found"})
    
    await feedback_service.record_suggestion_click(
        user_id=user_id,
        tenant_code=tenant_code,
        session_id=session_id,
        intent=intent,
        suggestion_text=suggestion
    )
    
    logger.info(f"Suggestion clicked: {suggestion} | Intent: {intent} | Session: {session_id}")
    
    return utf8_json_response({
        "success": True,
        "message": "Suggestion click tracked"
    })


@router.get("/feedback/performance")
async def get_feedback_performance(
    days: int = Query(30, ge=1, le=90),
    context: Dict = Depends(require_manager_role)
):
    """
    Get suggestion performance metrics.
    Manager-only endpoint.
    """
    feedback_service = get_feedback_service()
    tenant_code = context.get("tenant_code")
    
    if not tenant_code:
        return utf8_json_response({"success": False, "message": "Tenant code not found"})
    
    performance = await feedback_service.get_suggestion_performance(tenant_code, days)
    
    return utf8_json_response({
        "success": True,
        **performance
    })


@router.get("/feedback/user-insights")
async def get_user_insights(
    context: Dict = Depends(get_conversation_context)
):
    """
    Get feedback insights for the current user.
    """
    feedback_service = get_feedback_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "message": "User ID not found"})
    
    insights = await feedback_service.get_user_insights(user_id)
    
    return utf8_json_response({
        "success": True,
        **insights
    })
