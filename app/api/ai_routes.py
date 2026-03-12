from fastapi import APIRouter
from pydantic import BaseModel
from app.ai_engine.intent_classifier import IntentClassifier
from app.ai_engine.entity_extractor import EntityExtractor
from app.ai_engine.swahili_support import SwahiliSupport
from app.ai_engine.action_router import ActionRouter
from app.ai_engine.response_formatter import ResponseFormatter
from app.ai_engine.intent_overrides import apply_intent_overrides
from app.ai_engine.decision_support import DecisionSupport
from app.services.cache_service import get_cache_service
from app.services.db_query_service import DBQueryService
from app.services.llm_service import LLMService
from app.services.pricing_service import PricingService  # ADD THIS IMPORT
import logging
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AIRequest(BaseModel):
    message: str


class AIResponse(BaseModel):
    intent: str
    entities: dict
    result: str
    data: list = []


# ---------------------------------------------------------------------------
# Initialize AI Components (once at startup)
# ---------------------------------------------------------------------------

intent_classifier = IntentClassifier()
entity_extractor  = EntityExtractor()
swahili_support   = SwahiliSupport()
action_router     = ActionRouter()
formatter         = ResponseFormatter()
db                = DBQueryService()
llm               = LLMService()
pricing_service   = PricingService()  # ADD THIS LINE - Initialize PricingService

# Initialize Decision Support with required dependencies
decision_support = DecisionSupport(
    api=db.api,                 # Pass the API client from DBQueryService
    pricing=pricing_service,    # CHANGE THIS - Use pricing_service instead of llm
    warehouse=None,             # Optional
    recommender=None            # Optional
)


# ---------------------------------------------------------------------------
# Intents that should still go through the existing action_router
# (these have special logic: fuzzy matching, quotation creation, etc.)
# ---------------------------------------------------------------------------

ACTION_ROUTER_INTENTS = {
    "CREATE_QUOTATION",       # Needs natural language item parsing
    "RECOMMEND_ITEMS",        # Custom recommendation logic
    "RECOMMEND_CUSTOMERS",    # Custom recommendation logic
    "TRACK_DELIVERY",         # Needs special delivery lookup
    "GET_CROSS_SELL",         # ADDED: Customers who bought X also bought Y
    "GET_UPSELL",             # ADDED: Premium/upgrade suggestions
    "GET_SEASONAL_RECOMMENDATIONS",  # ADDED: Seasonal product recommendations
    "GET_TRENDING_PRODUCTS",  # ADDED: Trending/popular products
}

# Intents that need decision support services
DECISION_SUPPORT_INTENTS = {
    "FORECAST_DEMAND",
    "ANALYZE_CUSTOMER_BEHAVIOR",
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "GET_SALES_TREND",
    "GET_INVENTORY_TURNOVER",
    "COMPETITOR_PRICE_CHECK",    # Added
    "FIND_BEST_PRICE",           # Added
    "MARKET_INTELLIGENCE",       # Added
    "PRICE_ALERT",               # Added
}

# Intents answered purely from the knowledge base (no SAP API call)
KNOWLEDGE_BASE_INTENTS = {
    "COMPANY_INFO",
    "PRODUCT_INFO",
    "HOW_TO_ORDER",
    "CONTACT_INFO",
    "PAYMENT_METHODS",
    "POLICY_QUESTION",
    "FAQ",
    "GREETING",
    "THANKS",
    "SMALL_TALK",
    "TRAINING_MODULE",
    "TRAINING_GUIDE",
    "TRAINING_FAQ",
    "TRAINING_VIDEO",
    "TRAINING_WEBINAR",
    "TRAINING_GLOSSARY",
    "TRAINING_ONBOARDING",
}

# Recommendation intents that use the cross-sell formatter
RECOMMENDATION_INTENTS = {
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
}


# ---------------------------------------------------------------------------
# Chat Endpoint
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=AIResponse)
def chat_ai(request: AIRequest):
    message = request.message.strip()
    cache   = get_cache_service(ttl_seconds=300)

    # ── 0. Check for Swahili first ──────────────────────────────────────────
    sw_result = swahili_support.process_swahili_query(message)
    if sw_result.get("detected_language") != "en":
        logger.info(f"🇰🇪 Swahili detected, using Swahili processor")
        initial_entities = sw_result.get("entities", {})
        message = sw_result.get("normalized_text", message)
        if sw_result.get("intent") != "UNKNOWN":
            intent_raw = {"intent": sw_result.get("intent")}
        else:
            intent_raw = intent_classifier.classify(message)
    else:
        initial_entities = {}
        intent_raw = intent_classifier.classify(message)

    # ── 1. Detect intent ────────────────────────────────────────────────────
    intent = intent_raw.get("intent") if isinstance(intent_raw, dict) else str(intent_raw)
    intent = intent.upper()
    logger.info(f"Detected intent: {intent}")

    # ── 2. General AI fallback (UNKNOWN) — never cached ────────────────────
    if intent == "UNKNOWN":
        logger.info("Using General AI fallback response")
        ai_reply = llm.generate(
            f"User asked: {message}\nReply naturally.",
            intent="GENERAL",
        )
        return AIResponse(
            intent="GENERAL_AI",
            entities=initial_entities,
            result=ai_reply.strip(),
            data=[],
        )

    # ── 3. Extract entities (with initial entities from Swahili) ────────────
    entities = entity_extractor.extract(message, initial_entities=initial_entities) or {}
    logger.info(f"Entities: {entities}")

    # ── 4. Apply intent overrides ───────────────────────────────────────────
    intent = apply_intent_overrides(intent, entities)
    logger.info(f"Final intent: {intent}")

    # ── 5. Check cache ──────────────────────────────────────────────────────
    cached = cache.get(intent, entities, message)
    if cached is not None:
        logger.info(f"⚡ Cache HIT - returning cached response for '{message}'")
        return AIResponse(
            intent=cached.get("intent", intent),
            entities=cached.get("entities", entities),
            result=cached.get("result", ""),
            data=cached.get("data", []),
        )

    # ── 6. Route the intent ─────────────────────────────────────────────────
    response = _route(intent, entities, message, llm, db, action_router, formatter, decision_support)

    # ── 7. Cache and return ─────────────────────────────────────────────────
    if cache.should_cache(intent):
        logger.info(f"📝 Caching response for '{message}'")
        cache.set(intent, entities, message, response.dict())

    return response


# ---------------------------------------------------------------------------
# Routing logic (extracted for clarity)
# ---------------------------------------------------------------------------

def _route(
    intent: str,
    entities: dict,
    message: str,
    llm: LLMService,
    db: DBQueryService,
    action_router: ActionRouter,
    formatter: ResponseFormatter,
    decision_support: DecisionSupport,
) -> AIResponse:
    """
    Four routing tiers:

    Tier 1 — Knowledge base intents (COMPANY_INFO, GREETING, etc.)
             → LLM answers from company profile, no SAP call needed.

    Tier 2 — Decision support intents (FORECAST_DEMAND, COMPETITOR_PRICE_CHECK, etc.)
             → DecisionSupport handles complex analytics.

    Tier 3 — Data intents (GET_ITEMS, GET_CUSTOMERS, GET_STOCK_LEVELS, etc.)
             → DBQueryService fetches from SAP → LLMService.narrate() formats answer.

    Tier 4 — Complex intents (CREATE_QUOTATION, RECOMMEND_*, etc.)
             → Existing action_router handles (preserves special logic).
    """

    # ── Tier 1: Conversational fast responses ───────────────────────────────
    if intent == "GREETING":
        return AIResponse(
            intent=intent, entities=entities,
            result="Hello! I'm the Leysco AI Assistant. I can help you with items, pricing, stock levels, customers, orders, and more. What would you like to know?",
            data=[],
        )

    if intent == "THANKS":
        return AIResponse(
            intent=intent, entities=entities,
            result="You're welcome! Let me know if there's anything else I can help you with.",
            data=[],
        )

    if intent == "SMALL_TALK":
        answer = llm.generate(
            f"The user sent a short conversational message: \"{message}\"\n"
            f"Reply naturally and briefly as the Leysco AI Assistant. "
            f"If appropriate, invite them to ask about items, pricing, or customers.",
            intent="GENERAL",
            max_tokens=80,
        )
        return AIResponse(intent=intent, entities=entities, result=answer, data=[])

    # ── Tier 1: Knowledge base ──────────────────────────────────────────────
    if intent in KNOWLEDGE_BASE_INTENTS:
        logger.info(f"📚 Tier 1 — Knowledge base: {intent}")
        answer = llm.generate(
            f"User asked: {message}",
            intent=intent,
        )
        return AIResponse(intent=intent, entities=entities, result=answer, data=[])

    # ── Tier 2: Decision support (analytics, competitor pricing, etc.) ─────
    if intent in DECISION_SUPPORT_INTENTS:
        logger.info(f"📊 Tier 2 — Decision support: {intent}")
        
        # Special handling for competitor pricing intents
        if intent in ["COMPETITOR_PRICE_CHECK", "FIND_BEST_PRICE", "MARKET_INTELLIGENCE", "PRICE_ALERT"]:
            # Ensure we have the item name
            if not entities.get("item_name") and intent != "MARKET_INTELLIGENCE":
                # Try to extract from message
                import re
                patterns = [
                    r'(?:price|cost|cheapest|best)\s+(?:of|for)?\s*([a-zA-Z0-9\-\(\)\s]+?)(?:\?|$)',
                    r'([a-zA-Z0-9\-\(\)\s]+?)\s+(?:price|cost)',
                ]
                for pattern in patterns:
                    match = re.search(pattern, message.lower())
                    if match:
                        item_name = match.group(1).strip()
                        entities["item_name"] = item_name
                        logger.info(f"Extracted item from message: '{item_name}'")
                        break
        
        # Call the appropriate decision support method
        try:
            if intent == "COMPETITOR_PRICE_CHECK":
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result_data = loop.run_until_complete(decision_support.competitor_price_check(entities))
                loop.close()
            elif intent == "FIND_BEST_PRICE":
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result_data = loop.run_until_complete(decision_support.find_best_price(entities))
                loop.close()
            elif intent == "MARKET_INTELLIGENCE":
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result_data = loop.run_until_complete(decision_support.market_intelligence(entities))
                loop.close()
            elif intent == "PRICE_ALERT":
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result_data = loop.run_until_complete(decision_support.price_alert(entities))
                loop.close()
            else:
                result_data = decision_support.analyze(intent, entities)
        except Exception as e:
            logger.error(f"Error in decision support: {e}")
            result_data = {"error": True, "message": str(e)}
        
        if result_data and isinstance(result_data, dict) and "error" in result_data:
            answer = llm.generate(
                f"User asked about {intent.lower().replace('_', ' ')}. "
                f"Error: {result_data.get('message', 'Unable to process request')}. "
                f"Provide a helpful response suggesting alternatives.",
                intent=intent,
            )
            return AIResponse(
                intent=intent,
                entities=entities,
                result=answer,
                data=[],
            )
        
        if result_data:
            answer = llm.narrate(
                question=message,
                db_rows=[result_data] if isinstance(result_data, dict) else result_data,
                intent=intent,
            )
            return AIResponse(
                intent=intent,
                entities=entities,
                result=answer,
                data=result_data if isinstance(result_data, list) else [result_data],
            )
        
        answer = f"I couldn't generate a {intent.lower().replace('_', ' ')} analysis at this time. Please try again later."
        return AIResponse(intent=intent, entities=entities, result=answer, data=[])

    # ── Tier 3: DB → narrate ────────────────────────────────────────────────
    if intent not in ACTION_ROUTER_INTENTS:
        logger.info(f"🗄️  Tier 3 — DB query + narrate: {intent}")

        if intent in ("GET_ITEM_PRICE", "GET_ITEM_BASE_PRICE", "GET_CUSTOMER_PRICE"):
            item_name    = entities.get("item_name") or ""
            customer_name = entities.get("customer_name") or ""
            rows = db.resolve_and_price(
                item_name=item_name,
                customer_name=customer_name if intent == "GET_CUSTOMER_PRICE" else None,
            )
        else:
            rows = db.query(intent=intent, entities=entities)

        if rows is None:
            answer = llm.generate(f"User asked: {message}", intent=intent)
            return AIResponse(intent=intent, entities=entities, result=answer, data=[])

        if not rows:
            logger.info(f"No data returned for {intent}")
            answer = f"I couldn't find any information for your request. Please try being more specific or ask about something else."
            return AIResponse(
                intent=intent,
                entities=entities,
                result=answer,
                data=[],
            )

        answer = llm.narrate(
            question=message,
            db_rows=rows,
            intent=intent,
        )

        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=rows,
        )

    # ── Tier 4: action_router ────────────────────────────────────────
    logger.info(f"⚙️  Tier 4 — Action router: {intent}")

    api_result = action_router.route(intent, entities, message)
    logger.info(f"API Result received - Type: {type(api_result)}")

    # Handle recommendation intents (GET_CROSS_SELL, GET_UPSELL, etc.)
    if intent in RECOMMENDATION_INTENTS:
        # Ensure api_result is a dict with the expected structure
        if isinstance(api_result, dict):
            formatted = _legacy_format(intent, api_result, formatter)
            # Ensure we have a valid message
            result_message = formatted.get("message", "")
            if not result_message:
                # Fallback message if formatter returns empty
                item_name = entities.get("item_name", "this item")
                result_message = f"I couldn't find any recommendations for {item_name}."
            
            return AIResponse(
                intent=intent,
                entities=entities,
                result=result_message,
                data=formatted.get("data", []),
            )
        else:
            # If api_result is not a dict (e.g., a list), wrap it
            formatted = _legacy_format(intent, {"recommendations": api_result if api_result else []}, formatter)
            return AIResponse(
                intent=intent,
                entities=entities,
                result=formatted.get("message", f"No recommendations found."),
                data=formatted.get("data", []),
            )

    # For other intents, check if api_result already has a message
    if isinstance(api_result, dict) and "message" in api_result and "ResponseData" not in api_result:
        return AIResponse(
            intent=intent,
            entities=entities,
            result=api_result["message"],
            data=api_result.get("data", []),
        )

    # Default formatting for other intents
    formatted = _legacy_format(intent, api_result, formatter)
    return AIResponse(
        intent=intent,
        entities=entities,
        result=formatted.get("message", "I couldn't process your request."),
        data=formatted.get("data", []),
    )


def _legacy_format(intent: str, api_result, formatter: ResponseFormatter) -> dict:
    """Preserve the original formatter logic for action_router results."""
    if intent == "GET_ITEMS":
        return formatter.format_list("items", api_result)
    elif intent == "GET_CUSTOMERS":
        return formatter.format_list("customers", api_result)
    elif intent in ["GET_INVOICES", "CUSTOMER_INVOICES"]:
        return formatter.format_invoices(api_result)
    elif intent == "GET_SALES_ORDERS":
        return formatter.format_sales_orders(api_result)
    elif intent == "GET_QUOTATIONS":
        return formatter.format_quotations(api_result)
    elif intent in ["GET_ITEM_PRICE", "GET_CUSTOMER_PRICE", "GET_ITEM_BASE_PRICE"]:
        return formatter.format_prices(api_result)
    # ADD CASES FOR RECOMMENDATION INTENTS
    elif intent == "GET_CROSS_SELL":
        return formatter.format_cross_sell(api_result)
    elif intent == "GET_UPSELL":
        return formatter.format_cross_sell(api_result)  # Reuse cross-sell formatter
    elif intent == "GET_SEASONAL_RECOMMENDATIONS":
        return formatter.format_cross_sell(api_result)  # Reuse cross-sell formatter
    elif intent == "GET_TRENDING_PRODUCTS":
        return formatter.format_cross_sell(api_result)  # Reuse cross-sell formatter
    else:
        return formatter.format_generic_error({"error": "Data not available."})


# ---------------------------------------------------------------------------
# Cache management endpoints
# ---------------------------------------------------------------------------

@router.get("/cache/stats")
def cache_stats():
    """Get cache performance statistics."""
    return get_cache_service().get_stats()


@router.post("/cache/clear")
def cache_clear(intent: Optional[str] = None):
    """Clear cache — optionally by intent."""
    cache = get_cache_service()
    if intent:
        cache.invalidate_intent(intent.upper())
        return {"message": f"Cleared cache for intent: {intent}"}
    cache.clear()
    return {"message": "Cleared entire cache"}