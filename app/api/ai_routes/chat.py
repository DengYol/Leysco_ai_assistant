"""Main chat endpoint for AI conversations

This module handles the core chat endpoint including:
- Intent classification
- Entity extraction
- Context resolution
- Caching
- Streaming vs non-streaming response handling
- Activity logging
- Query rewriting for better intent detection
"""

from fastapi import APIRouter, Depends
from typing import Dict
import asyncio
import re
import logging

from .schemas import AIRequest, AIResponse
from .streaming import create_streaming_response
from .utils import (
    utf8_json_response, 
    extract_delivery_number, 
    extract_customer_for_delivery
)
from .suggestion_handlers import get_suggestions_with_feedback, get_base_suggestions
from .context_resolution import resolve_reference_from_context
from .constants import (
    DELIVERY_INTENTS,
    PRICE_INTENTS,
    CANDIDATE_LABELS
)

from app.ai_engine.intent_classifier import IntentClassifier
from app.ai_engine.entity_extractor import EntityExtractor
from app.ai_engine.swahili_support import SwahiliSupport
from app.ai_engine.intent_overrides import apply_intent_overrides
from app.ai_engine.response_formatter import ResponseFormatter
from app.ai_engine.query_rewriter import get_query_rewriter
from app.services.cache_service import get_cache_service
from app.services.conversation_memory import get_conversation_memory
from app.services.activity_logger import get_activity_logger
from app.services.feedback_service import get_feedback_service
from app.services.session_context import session_ctx
from app.services.performance_monitor import performance_monitor
from app.services.llm_service import get_llm_service
from app.api.dependencies import (
    get_token_from_header,
    get_company_code,
    get_conversation_context
)
from app.core.tenant_context import set_current_tenant, TenantContext, clear_current_tenant

from .routing_logic import route_async

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize AI components (once at startup)
intent_classifier = IntentClassifier()
entity_extractor = EntityExtractor()
swahili_support = SwahiliSupport()
formatter = ResponseFormatter()
llm = get_llm_service(provider="auto")
query_rewriter = get_query_rewriter()  # Initialize query rewriter

# ============================================================================
# INTENT PRIORITY RULES
#
# These are "specific" intents that the query rewriter detects with high
# accuracy. When the rewriter identifies one of these AND the classifier
# returns a more generic intent at low confidence, we trust the rewriter.
#
# The threshold below (0.75) means: if classifier confidence < 0.75 AND
# the rewriter returned a more specific intent, prefer the rewriter's answer.
# ============================================================================

_CLASSIFIER_CONFIDENCE_THRESHOLD = 0.75

# Intents that are more specific versions of a generic intent.
# Key = generic intent the classifier might wrongly return
# Value = set of specific intents the rewriter can correctly detect
_SPECIFIC_INTENT_OVERRIDES: dict[str, set[str]] = {
    "GET_ITEMS": {
        "GET_TOP_SELLING_ITEMS",
        "GET_SLOW_MOVING_ITEMS",
        "GET_STOCK_LEVELS",
        "GET_LOW_STOCK_ALERTS",
    },
    "GET_CUSTOMERS": {
        "GET_CUSTOMER_HEALTH",
        "FIND_CUSTOMERS_BY_ITEM",
    },
    "GET_STOCK_LEVELS": {
        "GET_LOW_STOCK_ALERTS",
    },
}


def _resolve_intent(
    classifier_intent: str,
    classifier_confidence: float,
    rewriter_intent: str | None,
) -> tuple[str, str]:
    """
    Decide which intent wins: the classifier's or the rewriter's.

    Returns (final_intent, source) where source is "classifier" or "rewriter".

    Rules (checked in order):
    1. If there is no rewriter intent, always use the classifier.
    2. If classifier and rewriter agree, use the classifier (it's already right).
    3. If the rewriter's intent is a known specific refinement of the
       classifier's generic intent AND classifier confidence is below the
       threshold, trust the rewriter.
    4. Otherwise, use the classifier.
    """
    if not rewriter_intent:
        return classifier_intent, "classifier"

    if classifier_intent == rewriter_intent:
        return classifier_intent, "classifier"

    specific_for_classifier = _SPECIFIC_INTENT_OVERRIDES.get(classifier_intent, set())
    if (
        rewriter_intent in specific_for_classifier
        and classifier_confidence < _CLASSIFIER_CONFIDENCE_THRESHOLD
    ):
        return rewriter_intent, "rewriter"

    return classifier_intent, "classifier"


@router.post("/chat")
async def chat_ai(
    request: AIRequest,
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code),
    conv_context: Dict = Depends(get_conversation_context)
):
    """
    Process chat messages with AI-powered intent recognition and conversation memory.
    
    The conv_context includes:
    - session_id: Current session identifier
    - user_role: "manager" or "sales_rep"
    - assigned_customers: List of customer codes for sales reps
    - context: Previous conversation context (last_intent, last_results, etc.)
    - history: Previous messages
    """
    start_time = asyncio.get_event_loop().time()
    message = request.message.strip()
    
    # Use request.session_id first, fallback to conv_context
    session_id = request.session_id or conv_context["session_id"]
    conv_context["session_id"] = session_id
    
    user_role = conv_context["user_role"]
    assigned_customers = conv_context.get("assigned_customers", [])
    
    # Get services
    memory = get_conversation_memory()
    activity_logger = get_activity_logger()
    feedback_service = get_feedback_service()
    
    # Validate message
    if not message:
        return utf8_json_response(AIResponse(
            intent="EMPTY",
            entities={},
            result="Please enter a message.",
            data=[],
            suggestions=[],
            session_id=session_id,
            processing_time_ms=0,
        ).dict())
    
    # Log user message to memory
    memory.add_message(session_id, "user", message)
    
    # Set tenant context
    tenant = TenantContext(
        company_code=company_code,
        company_id=0,
        user_id=conv_context.get("user_id", 0),
        user_email=conv_context.get("user_email", ""),
        user_role=user_role,
        user_token=user_token
    )
    set_current_tenant(tenant)
    
    # ========================================================================
    # Set user token on entity extractor for API access
    # ========================================================================
    entity_extractor.set_user_token(user_token)
    
    cache = get_cache_service(ttl_seconds=300)
    
    # ========================================================================
    # QUERY REWRITING FOR BETTER INTENT DETECTION
    # ========================================================================
    
    # Rewrite and expand query for better understanding
    rewritten_message, detected_intent_from_rewriter, extracted_entities_from_rewriter = query_rewriter.rewrite(message)
    
    # Log the rewriting
    logger.info(f"Query rewritten: '{message}' → '{rewritten_message}' (intent: {detected_intent_from_rewriter})")
    
    # Use rewritten message for further processing
    processed_message = rewritten_message
    
    # ========================================================================
    # INTENT CLASSIFICATION & ENTITY EXTRACTION
    # ========================================================================
    
    # Process with Swahili support if needed
    sw_result = swahili_support.process_swahili_query(processed_message)
    if sw_result.get("detected_language") != "en":
        logger.info("Swahili detected, using Swahili processor")
        initial_entities = sw_result.get("entities", {})
        normalized_message = sw_result.get("normalized_text", processed_message)
        language = sw_result.get("detected_language", "sw")
        if sw_result.get("intent") != "UNKNOWN":
            intent_raw = {"intent": sw_result.get("intent"), "language": language, "confidence": 0.90}
        else:
            intent_raw = await intent_classifier.classify_async(normalized_message)
            intent_raw["language"] = language
    else:
        initial_entities = {}
        normalized_message = processed_message
        intent_raw = await intent_classifier.classify_async(processed_message)

    classifier_intent = (intent_raw.get("intent") if isinstance(intent_raw, dict) else str(intent_raw)).upper()
    classifier_confidence = intent_raw.get("confidence", 0.0) if isinstance(intent_raw, dict) else 0.0
    language = (intent_raw.get("language") or "en").lower().strip() if isinstance(intent_raw, dict) else "en"

    # ========================================================================
    # INTENT RESOLUTION: rewriter vs classifier
    #
    # The query rewriter uses deterministic pattern matching and is highly
    # accurate for specific intents like GET_TOP_SELLING_ITEMS or
    # GET_SLOW_MOVING_ITEMS. When the classifier falls back to a generic
    # intent (e.g. GET_ITEMS) with low confidence, we prefer the rewriter.
    # ========================================================================
    intent, intent_source = _resolve_intent(
        classifier_intent,
        classifier_confidence,
        detected_intent_from_rewriter,
    )

    if intent_source == "rewriter":
        logger.info(
            f"Intent overridden by rewriter: '{classifier_intent}' (conf: {classifier_confidence:.2f}) "
            f"→ '{intent}'"
        )
        intent_raw["intent"] = intent
        intent_raw["confidence"] = 0.85   # rewriter is deterministic; assign high confidence
        intent_raw["from_rewriter"] = True
    else:
        # Final safety net: if classifier still returned UNKNOWN/CLARIFY and
        # rewriter has something, use the rewriter.
        if classifier_intent in ("UNKNOWN", "CLARIFY") and detected_intent_from_rewriter:
            intent = detected_intent_from_rewriter
            intent_raw["intent"] = intent
            intent_raw["confidence"] = 0.75
            intent_raw["from_rewriter"] = True
            logger.info(f"Fallback to rewriter intent: {intent} (classifier was {classifier_intent})")

    # Extract entities
    fresh_entities = await entity_extractor.extract_async(
        normalized_message, 
        context=conv_context.get("context")
    )
    logger.info(f"Fresh entities from current message: {fresh_entities}")
    
    # Merge entities from query rewriter
    if extracted_entities_from_rewriter:
        for key, value in extracted_entities_from_rewriter.items():
            if value and not fresh_entities.get(key):
                fresh_entities[key] = value
                logger.info(f"Entity from rewriter: {key}={value}")
    
    # Resolve references from conversation context
    context_data = conv_context.get("context", {})
    resolved_entities, context_used = resolve_reference_from_context(
        normalized_message, context_data, fresh_entities
    )
    entities = resolved_entities.copy()
    
    logger.info(f"Detected intent: {intent} | language: {language} | user_role: {user_role}")
    performance_monitor.track_request(
        session_id, 
        {"intent_detection": (asyncio.get_event_loop().time() - start_time) * 1000}
    )
    
    # ========================================================================
    # STREAMING RESPONSE HANDLING
    # ========================================================================
    
    if request.stream:
        return create_streaming_response(
            message=normalized_message,
            intent=intent,
            entities=entities,
            language=language,
            session_id=session_id,
            user_token=user_token,
            context=conv_context.get("context")
        )
    
    # ========================================================================
    # NON-STREAMING RESPONSE HANDLING
    # ========================================================================
    
    # Handle CLARIFY intent (ambiguous query)
    if intent == "CLARIFY":
        return await _handle_clarify_intent(
            intent_raw, initial_entities, language, message, session_id,
            company_code, user_role, conv_context, start_time, activity_logger
        )
    
    # Handle UNKNOWN intent - use query rewriter to generate better suggestions
    if intent == "UNKNOWN":
        # Try to generate contextual suggestions based on the original message
        contextual_suggestions = _generate_contextual_suggestions(message)
        return await _handle_unknown_intent(
            message, initial_entities, language, session_id, company_code,
            user_role, conv_context, start_time, memory, activity_logger,
            contextual_suggestions
        )
    
    if context_used:
        logger.info(f"Context used to resolve entities: {entities}")
    
    # Extract delivery information for delivery intents
    if intent in DELIVERY_INTENTS:
        delivery_num = extract_delivery_number(normalized_message, entities)
        if delivery_num:
            entities["delivery_number"] = delivery_num
        customer = extract_customer_for_delivery(normalized_message, entities)
        if customer:
            entities["customer_name"] = customer
    
    # Extract limit and days for top selling/slow moving items
    if intent in ["GET_TOP_SELLING_ITEMS", "GET_SLOW_MOVING_ITEMS"]:
        limit_match = re.search(r'top\s+(\d+)', normalized_message.lower())
        if limit_match:
            entities["quantity"] = int(limit_match.group(1))
        days_match = re.search(r'last\s+(\d+)\s+days', normalized_message.lower())
        if days_match:
            entities["days"] = int(days_match.group(1))
    
    # Check for pending action (quotation confirmation, etc.)
    pending = memory.get_pending_action(session_id)
    if pending and any(word in message.lower() for word in ["yes", "confirm", "create", "ok", "sure", "go ahead", "proceed"]):
        return await _handle_pending_action(
            pending, entities, message, session_id, company_code,
            user_role, conv_context, start_time, memory, activity_logger, context_used
        )
    
    logger.info(f"Final entities (current message priority): {entities}")
    performance_monitor.track_request(
        session_id, 
        {"entity_extraction": (asyncio.get_event_loop().time() - start_time) * 1000}
    )

    # Apply intent overrides
    intent = apply_intent_overrides(intent, entities)
    logger.info(f"Final intent after overrides: {intent}")
    session_ctx.merge(session_id, entities)

    # Check cache
    cached = None
    if intent in PRICE_INTENTS:
        cache_key = f"response:{normalized_message}"
        cached = await cache.get_simple_async(cache_key)
    else:
        cached = await cache.get_async(intent, entities, normalized_message)
    
    if cached is not None:
        return await _handle_cached_response(
            cached, intent, entities, message, session_id, company_code,
            user_role, conv_context, start_time, memory, activity_logger, context_used,
            language, context_data
        )

    # Route the request - PASS COMPANY_CODE HERE!
    response = await route_async(
        intent, entities, normalized_message, language, session_id, user_token,
        llm, formatter, context_data, assigned_customers, user_role,
        company_code=company_code  # <-- THIS IS THE KEY FIX
    )
    
    # Add context_used flag to response
    response.context_used = context_used

    # Cache the response
    if cache.should_cache(intent):
        logger.info(f"Caching response for '{message}'")
        if intent in PRICE_INTENTS:
            cache_key = f"response:{normalized_message}"
            await cache.set_simple_async(cache_key, response.dict(), ttl=3600)
        else:
            await cache.set_async(intent, entities, normalized_message, response.dict())
    
    response.processing_time_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
    performance_monitor.track_request(session_id, {"total": response.processing_time_ms})
    
    # Store assistant response in memory
    memory.add_message(session_id, "assistant", response.result, response.data)
    memory.update_context(
        session_id,
        intent=intent,
        entities=entities,
        results=response.data,
        action="responded"
    )
    
    # Use feedback-aware suggestions
    response.suggestions = await get_suggestions_with_feedback(
        intent=intent,
        entities=entities,
        language=language,
        context=context_data,
        tenant_code=company_code,
        user_id=conv_context.get("user_id")
    )
    
    # Log the activity
    await activity_logger.log_query(
        user_id=conv_context.get("user_id", 0),
        user_role=user_role,
        tenant_code=company_code,
        session_id=session_id,
        intent=intent,
        query=message,
        response=response.result,
        processing_time_ms=response.processing_time_ms,
        suggestions_shown=response.suggestions,
        context_used=context_used,
        success=True
    )
    
    clear_current_tenant()
    
    # Log the response JSON before returning
    logger.info(f"📤 RESPONSE JSON: {response.dict()}")
    
    # Return with UTF-8 encoding
    return utf8_json_response(response.dict())


def _generate_contextual_suggestions(message: str) -> list:
    """Generate contextual suggestions based on the user's message"""
    suggestions = []
    msg_lower = message.lower()
    
    # Price-related suggestions
    if any(word in msg_lower for word in ["price", "cost", "how much", "bei", "gharama"]):
        suggestions = [
            "Price of vegimax",
            "Price of maize seeds",
            "Price of cabbage seeds",
            "Price of tomato seeds"
        ]
    # Stock-related suggestions
    elif any(word in msg_lower for word in ["stock", "inventory", "available", "hisa"]):
        suggestions = [
            "Stock of vegimax",
            "Stock of maize",
            "Low stock alerts",
            "Warehouse stock levels"
        ]
    # Delivery-related suggestions
    elif any(word in msg_lower for word in ["delivery", "order", "usafirishaji"]):
        suggestions = [
            "Outstanding deliveries",
            "Track delivery",
            "Delivery history"
        ]
    # Customer-related suggestions
    elif any(word in msg_lower for word in ["customer", "mteja", "client"]):
        suggestions = [
            "Show customers",
            "Customer orders",
            "Customer details"
        ]
    # General suggestions
    else:
        suggestions = [
            "Price of vegimax",
            "Show top selling items",
            "Outstanding deliveries",
            "Show customers"
        ]
    
    return suggestions[:4]  # Return up to 4 suggestions


async def _handle_clarify_intent(
    intent_raw, initial_entities, language, message, session_id,
    company_code, user_role, conv_context, start_time, activity_logger
):
    """Handle CLARIFY intent - ambiguous query needs disambiguation."""
    candidates = intent_raw.get("candidates", []) if isinstance(intent_raw, dict) else []
    chip_messages = [CANDIDATE_LABELS.get(c, c.replace("_", " ").title()) for c in candidates[:3]]
    
    # If no candidates from classifier, try contextual suggestions
    if not chip_messages:
        chip_messages = _generate_contextual_suggestions(message)
    
    if language == "sw":
        msg = "Samahani, sikuelewa vizuri. Je, unamaanisha:\n- " + "\n- ".join(chip_messages) + "\n\nTafadhali bonyeza chaguo moja au andika swali lako tena."
    else:
        msg = "I'm not quite sure what you're looking for. Did you mean:\n- " + "\n- ".join(chip_messages) + "\n\nTap one of the options or rephrase your question."
    
    clear_current_tenant()
    
    await activity_logger.log_query(
        user_id=conv_context.get("user_id", 0),
        user_role=user_role,
        tenant_code=company_code,
        session_id=session_id,
        intent="CLARIFY",
        query=message,
        response=msg,
        processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
        suggestions_shown=chip_messages,
        context_used=False,
        success=True
    )
    
    return utf8_json_response(AIResponse(
        intent="CLARIFY",
        entities=initial_entities,
        result=msg,
        data=[],
        suggestions=chip_messages,
        session_id=session_id,
        processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
    ).dict())


async def _handle_unknown_intent(
    message, initial_entities, language, session_id, company_code,
    user_role, conv_context, start_time, memory, activity_logger,
    contextual_suggestions=None
):
    """Handle UNKNOWN intent - fallback to general LLM response."""
    logger.info("Using General AI fallback response")
    
    # Use query rewriter to get better suggestions
    rewriter = get_query_rewriter()
    rewritten, detected_intent, extracted_entities = rewriter.rewrite(message)
    
    # If we have a detected intent from rewriter, use it
    if detected_intent:
        logger.info(f"Query rewriter detected intent: {detected_intent} for '{message}'")
        # We could recursively call with the detected intent, but for now, just log
    
    ai_reply = await llm.generate_async(
        f"User asked: {message}\nReply naturally. Be helpful and suggest what you can help with.",
        intent="GENERAL",
        language=language,
        max_tokens=300,
    )
    memory.add_message(session_id, "assistant", ai_reply)
    
    # Use contextual suggestions if provided, otherwise generate
    suggestions = contextual_suggestions or _generate_contextual_suggestions(message)
    
    await activity_logger.log_query(
        user_id=conv_context.get("user_id", 0),
        user_role=user_role,
        tenant_code=company_code,
        session_id=session_id,
        intent="GENERAL_AI",
        query=message,
        response=ai_reply,
        processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
        suggestions_shown=suggestions,
        context_used=False,
        success=True
    )
    
    clear_current_tenant()
    return utf8_json_response(AIResponse(
        intent="GENERAL_AI",
        entities=initial_entities,
        result=ai_reply.strip(),
        data=[],
        suggestions=suggestions,
        session_id=session_id,
        processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
    ).dict())


async def _handle_pending_action(
    pending, entities, message, session_id, company_code,
    user_role, conv_context, start_time, memory, activity_logger, context_used
):
    """Handle pending action confirmation."""
    logger.info(f"User confirmed pending action: {pending['action']}")
    result_message = f"Confirmed: {pending['action']} completed successfully."
    memory.clear_pending_action(session_id)
    memory.add_message(session_id, "assistant", result_message)
    
    await activity_logger.log_query(
        user_id=conv_context.get("user_id", 0),
        user_role=user_role,
        tenant_code=company_code,
        session_id=session_id,
        intent=pending["action"],
        query=message,
        response=result_message,
        processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
        suggestions_shown=[],
        context_used=context_used,
        success=True
    )
    
    return utf8_json_response(AIResponse(
        intent=pending["action"],
        entities=entities,
        result=result_message,
        data=pending.get("data", []),
        suggestions=[],
        session_id=session_id,
        processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
    ).dict())


async def _handle_cached_response(
    cached, intent, entities, message, session_id, company_code,
    user_role, conv_context, start_time, memory, activity_logger, context_used,
    language, context_data
):
    """Handle cached response."""
    logger.info(f"Cache HIT for '{message}'")
    processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
    clear_current_tenant()
    memory.add_message(session_id, "assistant", cached.get("result", ""))
    
    await activity_logger.log_query(
        user_id=conv_context.get("user_id", 0),
        user_role=user_role,
        tenant_code=company_code,
        session_id=session_id,
        intent=cached.get("intent", intent),
        query=message,
        response=cached.get("result", ""),
        processing_time_ms=processing_time,
        suggestions_shown=cached.get("suggestions", []),
        context_used=context_used,
        success=True
    )
    
    return utf8_json_response(AIResponse(
        intent=cached.get("intent", intent),
        entities=cached.get("entities", entities),
        result=cached.get("result", ""),
        data=cached.get("data", []),
        suggestions=await get_suggestions_with_feedback(
            intent=intent,
            entities=entities,
            language=language,
            context=context_data,
            tenant_code=company_code,
            user_id=conv_context.get("user_id")
        ),
        session_id=session_id,
        processing_time_ms=processing_time,
        context_used=context_used
    ).dict())