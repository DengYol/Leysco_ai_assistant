"""Streaming response generator for AI chat

This module handles all streaming responses for the AI chat endpoint,
including progressive updates for different intent types.
"""

import json
import asyncio
from typing import Dict, AsyncGenerator, Optional, Tuple, Any
from fastapi.responses import StreamingResponse
from app.ai_engine.action_router import create_action_router
from app.ai_engine.decision_support import DecisionSupport
from app.ai_engine.response_formatter import ResponseFormatter
from app.services.db_query import create_db_query_service
from app.services.pricing_service import create_pricing_service
from app.services.conversation_memory import get_conversation_memory
# The LLM package lives at app/services/llm/ (folder named 'llm', not 'llm_service')
from app.services.llm import get_llm_service
from .constants import (
    KNOWLEDGE_BASE_INTENTS,
    ACTION_ROUTER_INTENTS,
    DECISION_SUPPORT_INTENTS,
    PRICE_INTENTS
)
from .suggestion_handlers import get_suggestions_with_feedback, legacy_format
from .rag_handlers import enhance_with_rag
from .utils import create_summary_from_analysis
import logging

logger = logging.getLogger(__name__)

# Global formatter and LLM instances
# FIX: Use "groq" explicitly — "auto" was accepted by the old monolith but the
# new package normalises "auto" → "groq" anyway; be explicit to avoid confusion.
formatter = ResponseFormatter()
llm = get_llm_service(provider="groq")


async def generate_streaming_response(
    message: str,
    intent: str,
    entities: dict,
    language: str,
    session_id: str,
    user_token: str,
    context: Dict = None,
) -> AsyncGenerator[str, None]:
    """Generate streaming response with progressive updates and context awareness."""
    # Create per-request services with user token
    action_router = create_action_router(user_token=user_token)
    pricing_service = create_pricing_service(user_token=user_token)
    db = create_db_query_service(user_token=user_token)
    
    decision_support = DecisionSupport(
        api=action_router.api,
        pricing=pricing_service,
        warehouse=action_router.warehouse,
        recommender=action_router.recommender,
    )
    
    memory = get_conversation_memory()
    
    rows = None
    response_text = ""
    
    try:
        yield f"data: {json.dumps({'type': 'intent', 'content': intent, 'data': None}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'entities', 'content': '', 'data': entities}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'status', 'content': 'Processing your request...', 'data': None}, ensure_ascii=False)}\n\n"
        
        start_time = asyncio.get_event_loop().time()
        
        if intent in KNOWLEDGE_BASE_INTENTS:
            response_text = await _handle_knowledge_base_streaming(
                message, intent, language
            )
            async for chunk in _stream_text(response_text, delay=0.02):
                yield chunk
        
        elif intent in ACTION_ROUTER_INTENTS:
            api_result, response_text = await _handle_action_router_streaming(
                action_router, intent, entities, message, language
            )
            async for chunk in _stream_text(response_text, delay=0.01):
                yield chunk
            
            if isinstance(api_result, dict) and api_result.get("data"):
                yield f"data: {json.dumps({'type': 'data', 'content': '', 'data': api_result.get('data', [])[:10]}, ensure_ascii=False)}\n\n"
        
        elif intent in DECISION_SUPPORT_INTENTS:
            response_text = await _handle_decision_support_streaming(
                decision_support, intent, entities, language
            )
            async for chunk in _stream_text(response_text, delay=0.01):
                yield chunk
        
        else:
            rows, response_text = await _handle_db_query_streaming(
                db, intent, entities, message, language
            )
            async for chunk in _stream_text(response_text, delay=0.015):
                yield chunk
        
        memory.add_message(session_id, "assistant", response_text, rows)
        
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        
        suggestions = await get_suggestions_with_feedback(
            intent=intent,
            entities=entities,
            language=language,
            context=context,
            tenant_code=None,
            user_id=None
        )
        
        yield f"data: {json.dumps({'type': 'suggestions', 'content': '', 'data': suggestions}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'content': '', 'data': {'processing_time_ms': processing_time}}, ensure_ascii=False)}\n\n"
        
    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        error_msg = "I encountered an issue processing your request. Please try again."
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg, 'data': {'error': str(e)}}, ensure_ascii=False)}\n\n"


async def _handle_knowledge_base_streaming(
    message: str,
    intent: str,
    language: str
) -> str:
    rag_context = await enhance_with_rag(message, None)
    
    if rag_context:
        prompt = (
            f"You are the Leysco AI Assistant. Use the following information to answer the user's question.\n\n"
            f"RELEVANT INFORMATION:\n{rag_context}\n\n"
            f"USER QUESTION: {message}\n\n"
            f"Answer based on the information above. If the information doesn't contain the answer, say so politely."
        )
    else:
        prompt = f"User asked: {message}"
    
    return await llm.generate_async(
        prompt,
        intent=intent,
        language=language,
        max_tokens=400,
    )


async def _handle_action_router_streaming(
    action_router,
    intent: str,
    entities: dict,
    message: str,
    language: str
) -> Tuple[Any, str]:
    api_result = action_router.route(intent, entities, message, language=language)
    
    if isinstance(api_result, dict) and "message" in api_result:
        response_text = api_result["message"]
    else:
        formatted = legacy_format(intent, api_result, formatter)
        response_text = formatted.get("message", "I couldn't process your request.")
    
    return api_result, response_text


async def _handle_decision_support_streaming(
    decision_support,
    intent: str,
    entities: dict,
    language: str
) -> str:
    result_data = await decision_support.analyze(intent, entities)
    
    if result_data and isinstance(result_data, dict):
        if intent == "GET_TOP_SELLING_ITEMS":
            items = result_data.get("items", [])
            days = entities.get("days") if isinstance(entities.get("days"), int) else 30
            limit = entities.get("quantity") if isinstance(entities.get("quantity"), int) else 10
            limit = min(limit, len(items)) if items else limit
            formatted = formatter.format_top_selling_items(items=items, limit=limit, days=days, language=language)
            return formatted.get("message", "")
        
        elif intent == "GET_SLOW_MOVING_ITEMS":
            items = result_data.get("items", [])
            days = entities.get("days") if isinstance(entities.get("days"), int) else 90
            limit = entities.get("quantity") if isinstance(entities.get("quantity"), int) else 10
            limit = min(limit, len(items)) if items else limit
            formatted = formatter.format_slow_moving_items(items=items, limit=limit, days=days, language=language)
            return formatted.get("message", "")
        
        elif intent == "GET_SALES_ANALYTICS":
            formatted = formatter.format_sales_analytics(result_data, language)
            return formatted.get("message", "")
        
        else:
            return create_summary_from_analysis(intent, result_data)
    
    return "Analysis complete. No significant findings."


async def _handle_db_query_streaming(
    db,
    intent: str,
    entities: dict,
    message: str,
    language: str
) -> Tuple[Any, str]:
    if intent in PRICE_INTENTS:
        rows = db.resolve_and_price(
            item_name=entities.get("item_name") or "",
            customer_name=entities.get("customer_name") or "" if intent == "GET_CUSTOMER_PRICE" else None,
        )
    else:
        rows = db.query(intent=intent, entities=entities, language=language)
    
    if intent == "GET_OUTSTANDING_DELIVERIES" and rows:
        formatted = formatter.format_outstanding_deliveries(rows, language)
        return rows, formatted.get("message", "")
    
    response_text = await llm.narrate_async(
        question=message,
        db_rows=rows[:20] if isinstance(rows, list) and rows else (rows or []),
        intent=intent,
        language=language,
        max_tokens=500 if rows else 300,
    )
    return rows, response_text


async def _stream_text(text: str, delay: float = 0.02) -> AsyncGenerator[str, None]:
    """Stream text word by word as SSE chunks."""
    for word in text.split():
        yield f"data: {json.dumps({'type': 'text', 'content': word + ' ', 'data': None}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(delay)


def create_streaming_response(
    message: str,
    intent: str,
    entities: dict,
    language: str,
    session_id: str,
    user_token: str,
    context: Dict = None,
) -> StreamingResponse:
    """Create a streaming response for the chat endpoint."""
    return StreamingResponse(
        generate_streaming_response(
            message=message,
            intent=intent,
            entities=entities,
            language=language,
            session_id=session_id,
            user_token=user_token,
            context=context
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8"
        }
    )


__all__ = [
    'generate_streaming_response',
    'create_streaming_response'
]
