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
from app.services.llm import get_llm_service
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
llm = get_llm_service(provider="groq")
query_rewriter = get_query_rewriter()

# ============================================================================
# INTENT PRIORITY RULES
# ============================================================================

_CLASSIFIER_CONFIDENCE_THRESHOLD = 0.75

_SPECIFIC_INTENT_OVERRIDES: dict[str, set[str]] = {
    # When classifier says GET_ITEMS but rewriter detected something more
    # specific, the rewriter wins — UNLESS confidence is above threshold.
    # FIX: Added GET_ITEM_DETAILS so "show items details of Cap Measuring"
    # routes to the item detail handler, not the generic browse handler.
    "GET_ITEMS": {
        "GET_TOP_SELLING_ITEMS",
        "GET_SLOW_MOVING_ITEMS",
        "GET_STOCK_LEVELS",
        "GET_LOW_STOCK_ALERTS",
        "GET_ITEM_DETAILS",   # "show items details of X" → detail lookup, not browse
    },
    "GET_CUSTOMERS": {
        "GET_CUSTOMER_HEALTH",
        "FIND_CUSTOMERS_BY_ITEM",
    },
    "GET_STOCK_LEVELS": {
        "GET_LOW_STOCK_ALERTS",
    },
}

# Intents that must never be overridden by apply_intent_overrides() when they
# were set by the query rewriter. Prevents e.g. "stock of sleeve 100ml" from
# being promoted to GET_CUSTOMER_PRICE because a customer_name was spuriously
# extracted alongside the item.
_REWRITER_PROTECTED_INTENTS: frozenset[str] = frozenset({
    "GET_STOCK_LEVELS",
    "GET_ITEM_PRICE",
    "GET_LOW_STOCK_ALERTS",
    "GET_ITEMS",
    "GET_ITEM_DETAILS",
    "GET_LOW_STOCK",
})

# ============================================================================
# FIX: GET_ITEMS context item_name bleed-over
# Compiled once at module level for efficiency.
#
# When the user asks to browse/list items the context resolver may inherit
# item_name from the previous turn and turn a generic listing into a filtered
# search. This regex detects listing/browse queries so we can clear item_name.
# ============================================================================
_LISTING_RE = re.compile(
    # \b after items?/products? prevents regex backtracking from "items" to "item",
    # which would bypass the (?!\s+details?) lookahead and falsely match
    # "show items details of X" as a listing query.
    r"(?:show(?:\s+me)?|list|get(?:\s+me)?|display|browse|view)\s+(?:\d+|all|every)?\s*"
    r"(?:items?|products?|inventory|bidhaa|vitu)\b(?!\s+details?)"
    r"|(?:onyesha|orodhesha|pata)\s+(?:\d+\s+)?(?:bidhaa|vitu)",
    re.IGNORECASE,
)


def _resolve_intent(
    classifier_intent: str,
    classifier_confidence: float,
    rewriter_intent: str | None,
) -> tuple[str, str]:
    """
    Decide which intent wins: the classifier's or the rewriter's.

    Returns (final_intent, source) where source is "classifier" or "rewriter".
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

    entity_extractor.set_user_token(user_token, company_code=company_code)

    cache = get_cache_service(ttl_seconds=300)

    # ========================================================================
    # QUERY REWRITING FOR BETTER INTENT DETECTION
    # ========================================================================

    rewritten_message, detected_intent_from_rewriter, extracted_entities_from_rewriter = \
        query_rewriter.rewrite(message)
    logger.info(
        f"Query rewritten: '{message}' → '{rewritten_message}' "
        f"(intent: {detected_intent_from_rewriter})"
    )
    processed_message = rewritten_message

    # ========================================================================
    # INTENT CLASSIFICATION & ENTITY EXTRACTION
    # ========================================================================

    sw_result = swahili_support.process_swahili_query(processed_message)
    if sw_result.get("detected_language") != "en":
        logger.info("Swahili detected, using Swahili processor")
        initial_entities = sw_result.get("entities", {})
        normalized_message = sw_result.get("normalized_text", processed_message)
        language = sw_result.get("detected_language", "sw")
        if sw_result.get("intent") != "UNKNOWN":
            intent_raw = {
                "intent": sw_result.get("intent"),
                "language": language,
                "confidence": 0.90,
            }
        else:
            intent_raw = await intent_classifier.classify_async(normalized_message)
            intent_raw["language"] = language
    else:
        initial_entities = {}
        normalized_message = processed_message
        intent_raw = await intent_classifier.classify_async(processed_message)

    classifier_intent = (
        intent_raw.get("intent") if isinstance(intent_raw, dict) else str(intent_raw)
    ).upper()
    classifier_confidence = (
        intent_raw.get("confidence", 0.0) if isinstance(intent_raw, dict) else 0.0
    )
    language = (
        (intent_raw.get("language") or "en").lower().strip()
        if isinstance(intent_raw, dict) else "en"
    )

    # ========================================================================
    # INTENT RESOLUTION: rewriter vs classifier
    # ========================================================================
    intent, intent_source = _resolve_intent(
        classifier_intent,
        classifier_confidence,
        detected_intent_from_rewriter,
    )

    if intent_source == "rewriter":
        logger.info(
            f"Intent overridden by rewriter: '{classifier_intent}' "
            f"(conf: {classifier_confidence:.2f}) → '{intent}'"
        )
        intent_raw["intent"] = intent
        intent_raw["confidence"] = 0.85
        intent_raw["from_rewriter"] = True
    else:
        if classifier_intent in ("UNKNOWN", "CLARIFY") and detected_intent_from_rewriter:
            intent = detected_intent_from_rewriter
            intent_raw["intent"] = intent
            intent_raw["confidence"] = 0.75
            intent_raw["from_rewriter"] = True
            logger.info(
                f"Fallback to rewriter intent: {intent} (classifier was {classifier_intent})"
            )

    # ========================================================================
    # ENTITY EXTRACTION
    # ========================================================================

    fresh_entities = await entity_extractor.extract_async(
        normalized_message,
        context=conv_context.get("context")
    )
    logger.info(f"Fresh entities from current message: {fresh_entities}")

    # Merge entities from query rewriter (rewriter values only fill gaps)
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

    logger.info(
        f"Detected intent: {intent} | language: {language} | user_role: {user_role}"
    )
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
    # FIX: Handle CLARIFY and GENERAL_AI with LLM
    # Instead of returning hardcoded suggestions, use the routing logic
    # which now has the _handle_general_ai function
    # ========================================================================
    if intent in ["CLARIFY", "GENERAL_AI", "UNKNOWN"]:
        logger.info(f"🔄 Routing {intent} to General AI handler")
        # Create a temporary context for the general AI handler
        temp_entities = entities.copy()
        temp_entities["_original_query"] = message
        
        # Use the routing logic which has the general AI handler
        response = await route_async(
            intent, 
            temp_entities, 
            normalized_message, 
            language, 
            session_id, 
            user_token,
            llm, 
            formatter, 
            context_data, 
            assigned_customers, 
            user_role,
            company_code=company_code
        )
        
        response.processing_time_ms = int(
            (asyncio.get_event_loop().time() - start_time) * 1000
        )
        performance_monitor.track_request(session_id, {"total": response.processing_time_ms})
        
        memory.add_message(session_id, "assistant", response.result, response.data)
        memory.update_context(
            session_id,
            intent=intent,
            entities=entities,
            results=response.data,
            action="responded"
        )
        
        response.suggestions = await get_suggestions_with_feedback(
            intent=intent,
            entities=entities,
            language=language,
            context=context_data,
            tenant_code=company_code,
            user_id=conv_context.get("user_id")
        )
        
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
        logger.info(f"📤 RESPONSE JSON: {response.dict()}")
        return utf8_json_response(response.dict())

    if context_used:
        logger.info(f"Context used to resolve entities: {entities}")

    # ========================================================================
    # DELIVERY ENTITY EXTRACTION
    # ========================================================================

    if intent in DELIVERY_INTENTS:
        delivery_num = extract_delivery_number(normalized_message, entities)
        if delivery_num:
            entities["delivery_number"] = delivery_num
        customer = extract_customer_for_delivery(normalized_message, entities)
        if customer:
            entities["customer_name"] = customer

    # ========================================================================
    # TOP/SLOW SELLING: extract limit and date range
    # ========================================================================

    if intent in ["GET_TOP_SELLING_ITEMS", "GET_SLOW_MOVING_ITEMS"]:
        limit_match = re.search(r'top\s+(\d+)', normalized_message.lower())
        if limit_match:
            entities["quantity"] = int(limit_match.group(1))
        days_match = re.search(r'last\s+(\d+)\s+days', normalized_message.lower())
        if days_match:
            entities["days"] = int(days_match.group(1))

    # ========================================================================
    # PENDING ACTION CONFIRMATION
    # ========================================================================

    pending = memory.get_pending_action(session_id)
    if pending and any(
        word in message.lower()
        for word in ["yes", "confirm", "create", "ok", "sure", "go ahead", "proceed"]
    ):
        return await _handle_pending_action(
            pending, entities, message, session_id, company_code,
            user_role, conv_context, start_time, memory, activity_logger, context_used
        )

    # ========================================================================
    # FIX: GET_ITEMS context item_name bleed-over
    #
    # For listing/browse queries the context resolver may have filled
    # item_name from a previous turn (e.g. "show me 10 items" → VEGIMAX-20L).
    # That silently converts a browse-all into a filtered search — wrong.
    #
    # Clear item_name when:
    #   a) The rewriter explicitly set _is_listing=True, OR
    #   b) The raw message matches the listing regex
    # Also extract quantity directly from the message if not already set.
    # ========================================================================
    if intent == "GET_ITEMS":
        _listing_from_rewriter = bool(
            extracted_entities_from_rewriter
            and extracted_entities_from_rewriter.get("_is_listing")
        )
        # FIX: Exclude item-detail queries ("show items details of X").
        # _LISTING_RE backtracks and matches "item" inside "items", bypassing
        # any lookahead guard. Simplest fix: if "detail" is in the message
        # it cannot be a listing request — the rewriter's GET_ITEM_DETAILS
        # intent handles it instead.
        _is_detail_query = "detail" in message.lower()
        _listing_from_message = (not _is_detail_query) and bool(_LISTING_RE.search(message))

        if _listing_from_rewriter or _listing_from_message:
            if entities.get("item_name"):
                logger.info(
                    f"GET_ITEMS listing request — clearing inherited item_name "
                    f"'{entities['item_name']}' (user asked for all items, not a filter)"
                )
                entities.pop("item_name", None)

            # Pull quantity from message if not already set by the rewriter
            if not entities.get("quantity"):
                _qty_match = re.search(
                    r'\b(\d+)\s+(?:items?|products?)\b', message, re.IGNORECASE
                )
                if _qty_match:
                    entities["quantity"] = int(_qty_match.group(1))
                    logger.info(
                        f"GET_ITEMS: quantity={entities['quantity']} extracted from message"
                    )

    # ========================================================================
    # INTENT OVERRIDES
    # Only run apply_intent_overrides() when the intent was NOT set (or is NOT
    # protected) by the query rewriter. This stops stock/price intents from
    # being silently promoted to GET_CUSTOMER_PRICE because the entity extractor
    # pulled a spurious customer_name from part of an item name like "sleeve".
    # ========================================================================

    logger.info(f"Final entities (current message priority): {entities}")
    performance_monitor.track_request(
        session_id,
        {"entity_extraction": (asyncio.get_event_loop().time() - start_time) * 1000}
    )

    rewriter_set_this_intent = intent_raw.get("from_rewriter", False)
    intent_is_protected = intent in _REWRITER_PROTECTED_INTENTS

    if rewriter_set_this_intent and intent_is_protected:
        logger.info(
            f"Skipping apply_intent_overrides: intent '{intent}' is rewriter-protected "
            f"(from_rewriter={rewriter_set_this_intent})"
        )
    else:
        intent = apply_intent_overrides(intent, entities)

    logger.info(f"Final intent after overrides: {intent}")
    session_ctx.merge(session_id, entities)

    # ========================================================================
    # CACHE CHECK
    # ========================================================================

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

    # ========================================================================
    # ROUTE THE REQUEST
    # ========================================================================

    response = await route_async(
        intent, entities, normalized_message, language, session_id, user_token,
        llm, formatter, context_data, assigned_customers, user_role,
        company_code=company_code
    )

    response.context_used = context_used

    if cache.should_cache(intent):
        logger.info(f"Caching response for '{message}'")
        if intent in PRICE_INTENTS:
            cache_key = f"response:{normalized_message}"
            await cache.set_simple_async(cache_key, response.dict(), ttl=3600)
        else:
            await cache.set_async(intent, entities, normalized_message, response.dict())

    response.processing_time_ms = int(
        (asyncio.get_event_loop().time() - start_time) * 1000
    )
    performance_monitor.track_request(session_id, {"total": response.processing_time_ms})

    memory.add_message(session_id, "assistant", response.result, response.data)
    memory.update_context(
        session_id,
        intent=intent,
        entities=entities,
        results=response.data,
        action="responded"
    )

    response.suggestions = await get_suggestions_with_feedback(
        intent=intent,
        entities=entities,
        language=language,
        context=context_data,
        tenant_code=company_code,
        user_id=conv_context.get("user_id")
    )

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

    logger.info(f"📤 RESPONSE JSON: {response.dict()}")

    return utf8_json_response(response.dict())


# ============================================================================
# HELPER: Contextual suggestion generation
# ============================================================================

def _generate_contextual_suggestions(message: str) -> list:
    """Generate contextual suggestions based on the user's message."""
    msg_lower = message.lower()

    if any(word in msg_lower for word in ["price", "cost", "how much", "bei", "gharama"]):
        return [
            "Price of vegimax",
            "Price of maize seeds",
            "Price of cabbage seeds",
            "Price of tomato seeds",
        ]
    if any(word in msg_lower for word in ["stock", "inventory", "available", "hisa"]):
        return [
            "Stock of vegimax",
            "Stock of maize",
            "Low stock alerts",
            "Warehouse stock levels",
        ]
    if any(word in msg_lower for word in ["delivery", "order", "usafirishaji"]):
        return [
            "Outstanding deliveries",
            "Track delivery",
            "Delivery history",
        ]
    if any(word in msg_lower for word in ["customer", "mteja", "client"]):
        return [
            "Show customers",
            "Customer orders",
            "Customer details",
        ]
    return [
        "Price of vegimax",
        "Show top selling items",
        "Outstanding deliveries",
        "Show customers",
    ]


# ============================================================================
# HANDLER: Pending action confirmation
# ============================================================================

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
        processing_time_ms=int(
            (asyncio.get_event_loop().time() - start_time) * 1000
        ),
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
        processing_time_ms=int(
            (asyncio.get_event_loop().time() - start_time) * 1000
        ),
    ).dict())


# ============================================================================
# HANDLER: Cached response
# ============================================================================

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