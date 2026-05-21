"""Session management endpoints for AI routes"""

from fastapi import APIRouter, Depends, Query
from typing import Dict
import logging

from .utils import utf8_json_response
from app.api.dependencies import get_conversation_context
from app.services.conversation_memory import get_conversation_memory

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/session/clear")
async def clear_session(
    context: Dict = Depends(get_conversation_context)
):
    """
    Clear conversation history and start fresh.
    Called when user clicks "New Chat" button.
    """
    memory = get_conversation_memory()
    memory.clear_session(context["session_id"])
    
    return utf8_json_response({
        "success": True,
        "message": "Conversation cleared. Starting fresh!",
        "session_id": context["session_id"]
    })


@router.get("/session/summary")
async def get_session_summary(
    context: Dict = Depends(get_conversation_context)
):
    """
    Get session summary (for debugging/analytics).
    """
    memory = get_conversation_memory()
    summary = memory.get_session_summary(context["session_id"])
    
    return utf8_json_response({
        "success": True,
        "session_id": context["session_id"],
        "user_role": context["user_role"],
        "message_count": context["message_count"],
        **summary
    })


@router.get("/session/history")
async def get_session_history(
    context: Dict = Depends(get_conversation_context),
    limit: int = Query(20, ge=1, le=50)
):
    """
    Get conversation history for the session.
    Used by Flutter to show chat history when reopening.
    """
    memory = get_conversation_memory()
    history = memory.get_conversation_history(context["session_id"], limit=limit)
    
    return utf8_json_response({
        "success": True,
        "session_id": context["session_id"],
        "history": history,
        "total": len(history)
    })