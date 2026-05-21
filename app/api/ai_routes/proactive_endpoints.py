"""Proactive suggestions endpoint for AI routes"""

from fastapi import APIRouter, Depends, Query
from typing import Dict
import logging

from .utils import utf8_json_response
from app.api.dependencies import get_conversation_context

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/proactive")
async def get_proactive_suggestions(
    context: Dict = Depends(get_conversation_context),
    limit: int = Query(3, ge=1, le=5)
):
    """
    Get proactive suggestions based on current context and user role.
    Called periodically by Flutter app to show in the chat.
    """
    suggestions = []
    session_context = context.get("context", {})
    
    # Check if user just viewed items and hasn't asked about prices
    if session_context.get("last_intent") in ["GET_ITEMS", "GET_TOP_SELLING_ITEMS"]:
        last_results = session_context.get("last_results", [])
        if last_results and len(last_results) > 0:
            top_item = last_results[0].get("ItemName") or last_results[0].get("name")
            if top_item:
                suggestions.append({
                    "type": "contextual",
                    "message": f"Would you like to check the price of {top_item}?",
                    "action": f"Price of {top_item}",
                    "priority": "MEDIUM"
                })
    
    # Manager-specific suggestions
    if context.get("is_manager"):
        suggestions.append({
            "type": "manager",
            "message": "View inventory health report",
            "action": "Show inventory health",
            "priority": "LOW"
        })
        suggestions.append({
            "type": "manager",
            "message": "Check reorder recommendations",
            "action": "Show reorder decisions",
            "priority": "LOW"
        })
    
    # Sales rep suggestions
    if not context.get("is_manager") and context.get("assigned_customers"):
        suggestions.append({
            "type": "sales_rep",
            "message": "View your assigned customers",
            "action": "Show my customers",
            "priority": "LOW"
        })
    
    return utf8_json_response({
        "success": True,
        "suggestions": suggestions[:limit],
        "session_id": context["session_id"]
    })