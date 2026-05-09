"""
app/api/ai_routes.py
====================
AI Chat Endpoint - Optimized with async, caching, and streaming support

MODIFIED FOR PHASE 1: Passes user token to ActionRouter and other services
MODIFIED FOR PHASE 2: Added proper outstanding deliveries formatting
MODIFIED FOR PHASE 3: Added conversation memory and proactive notifications
MODIFIED FOR PHASE 4: Added activity logging and analytics endpoints
MODIFIED FOR PHASE 5: Added feedback loop and ML forecasting endpoints
MODIFIED FOR PHASE 6: Added anomaly detection endpoints
MODIFIED FOR PHASE 7: Added RAG (Retrieval-Augmented Generation) endpoints
MODIFIED FOR PHASE 8: Added Knowledge Graph endpoints
FIXED: Issue 1 - Token threaded to streaming path
FIXED: Issue 2 - Session ID from request takes priority
FIXED: Issue 3 - Intent classification before streaming decision
FIXED: Issue 4 - zadd_async implemented in cache service
FIXED: Issue 5 - UTF-8 encoding for emojis and special characters
FIXED: Issue 6 - Added GET /quotation/{quotation_id} endpoint
FIXED: Issue 7 - GET_TOP_SELLING_ITEMS and GET_SLOW_MOVING_ITEMS now use proper formatter
FIXED: Issue 8 - Null handling for limit/days parameters in formatter calls
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse, Response, JSONResponse
from pydantic import BaseModel
from app.ai_engine.intent_classifier import IntentClassifier
from app.ai_engine.entity_extractor import EntityExtractor
from app.ai_engine.swahili_support import SwahiliSupport
from app.ai_engine.action_router import create_action_router
from app.ai_engine.response_formatter import ResponseFormatter
from app.ai_engine.intent_overrides import apply_intent_overrides
from app.ai_engine.decision_support import DecisionSupport
from app.ai_engine.suggestions_engine import suggestions_engine
from app.services.cache_service import get_cache_service
from app.services.db_query_service import create_db_query_service
from app.services.llm_service import get_llm_service
from app.services.pricing_service import create_pricing_service
from app.services.dashboard_service import get_dashboard_service
from app.services.session_context import session_ctx
from app.services.performance_monitor import performance_monitor
from app.services.conversation_memory import get_conversation_memory
from app.services.notification_service import get_notification_service
from app.services.activity_logger import get_activity_logger
from app.services.feedback_service import get_feedback_service
from app.services.anomaly_detection_service import get_anomaly_detection_service
from app.services.vector_store import get_vector_store
from app.services.knowledge_ingestion import get_knowledge_ingestion_service
from app.services.knowledge_graph import get_knowledge_graph
from app.services.quotation_service import QuotationService
from app.services.leysco_api_service import create_api_service
from app.ml.forecasting_service import get_ml_forecasting_service
from app.api.dependencies import (
    get_token_from_header,
    get_company_code,
    get_conversation_context,
    require_manager_role,
    extract_user_role_from_token,
    extract_assigned_customers_from_token
)
from app.core.tenant_context import set_current_tenant, TenantContext, clear_current_tenant
import logging
import uuid
import re
import json
import asyncio
from typing import Optional, Any, AsyncGenerator, Dict, List
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AIRequest(BaseModel):
    message: str
    session_id: str | None = None
    stream: bool = False  # Enable streaming response


class AIResponse(BaseModel):
    intent: str
    entities: dict
    result: str
    data: list = []
    suggestions: list[str] = []
    session_id: str = ""
    processing_time_ms: int = 0
    context_used: bool = False  # Indicates if context was used


class StreamChunk(BaseModel):
    type: str  # "intent", "entities", "text", "done", "error"
    content: str
    data: dict | None = None


# ---------------------------------------------------------------------------
# Initialize AI Components (once at startup)
# ---------------------------------------------------------------------------

intent_classifier = IntentClassifier()
entity_extractor = EntityExtractor()
swahili_support = SwahiliSupport()
# ActionRouter will be created per request with user token
formatter = ResponseFormatter()
# REMOVED: db = DBQueryService() - will be created per request with token
llm = get_llm_service(provider="auto")  # Auto-select Gemini or Groq


# ---------------------------------------------------------------------------
# Helper function for UTF-8 JSON response
# ---------------------------------------------------------------------------

def utf8_json_response(content: dict, status_code: int = 200) -> JSONResponse:
    """
    Return JSON response with proper UTF-8 encoding and headers.
    Ensures emojis and special characters display correctly.
    """
    return JSONResponse(
        content=content,
        status_code=status_code,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Content-Encoding": "utf-8",
            "Cache-Control": "no-cache"
        }
    )


# ---------------------------------------------------------------------------
# Intent routing sets (UPDATED)
# ---------------------------------------------------------------------------

ACTION_ROUTER_INTENTS = {
    "CREATE_QUOTATION",
    "RECOMMEND_ITEMS",
    "RECOMMEND_CUSTOMERS",
    "TRACK_DELIVERY",
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
    "FOLLOW_UP_QUOTATIONS",
    "FIND_CUSTOMERS_BY_ITEM",
}

DELIVERY_INTENTS = {
    "GET_OUTSTANDING_DELIVERIES",
    "GET_DELIVERY_HISTORY",
    "TRACK_DELIVERY",
    "GET_DELIVERY_STATUS",
}

DECISION_SUPPORT_INTENTS = {
    "FORECAST_DEMAND",
    "ANALYZE_CUSTOMER_BEHAVIOR",
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "GET_SALES_TREND",
    "GET_INVENTORY_TURNOVER",
    "COMPETITOR_PRICE_CHECK",
    "FIND_BEST_PRICE",
    "MARKET_INTELLIGENCE",
    "PRICE_ALERT",
    "GET_TOP_SELLING_ITEMS",
    "GET_SLOW_MOVING_ITEMS",
    "GET_SALES_ANALYTICS",
}

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

RECOMMENDATION_INTENTS = {
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
    "FIND_CUSTOMERS_BY_ITEM",
}

PRICE_INTENTS = {"GET_ITEM_PRICE", "GET_ITEM_BASE_PRICE", "GET_CUSTOMER_PRICE"}

# Intents that should use the new ResponseFormatter with emojis and bold text
FORMATTED_INTENTS = {
    "CREATE_QUOTATION",
    "GET_TOP_SELLING_ITEMS",
    "GET_SLOW_MOVING_ITEMS",
    "GET_OUTSTANDING_DELIVERIES",
    "FIND_CUSTOMERS_BY_ITEM",
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "FORECAST_DEMAND",
}


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def ensure_utf8_string(text: str) -> str:
    """Ensure string is properly encoded as UTF-8."""
    if not text:
        return text
    try:
        # Remove any invalid UTF-8 sequences
        return text.encode('utf-8', errors='ignore').decode('utf-8')
    except Exception:
        return str(text)


async def _enhance_with_rag(query: str, tenant_code: str) -> Optional[str]:
    """
    Retrieve relevant knowledge base content to augment the prompt.
    """
    try:
        vector_store = get_vector_store()
        
        # Search for relevant documents
        results = await vector_store.search(query, limit=3)
        
        if not results:
            return None
        
        # Filter by similarity threshold (0.5 = moderately similar)
        relevant_docs = [r for r in results if r["similarity"] > 0.5]
        
        if not relevant_docs:
            return None
        
        # Build context from retrieved documents
        context_parts = []
        for doc in relevant_docs:
            context_parts.append(doc["content"])
        
        context = "\n\n---\n\n".join(context_parts)
        
        logger.info(f"RAG retrieved {len(relevant_docs)} relevant documents")
        return context
        
    except Exception as e:
        logger.error(f"RAG enhancement failed: {e}")
        return None


async def _suggest_with_feedback(
    intent: str,
    entities: dict,
    language: str,
    context: Dict = None,
    tenant_code: str = None,
    user_id: int = None
) -> list[str]:
    """Get suggestion chips reordered by feedback."""
    # Get base suggestions
    suggestions = _suggest(intent, entities, language, context)
    
    if not suggestions or not tenant_code:
        return suggestions
    
    # Reorder based on feedback
    feedback_service = get_feedback_service()
    reordered = await feedback_service.reorder_suggestions(
        tenant_code=tenant_code,
        intent=intent,
        suggestions=suggestions,
        user_id=user_id
    )
    
    return reordered[:5]  # Limit to 5 suggestions


def _suggest(intent: str, entities: dict, language: str, context: Dict = None) -> list[str]:
    """Get suggestion chips for the response with context awareness."""
    suggestions = []
    
    # Context-aware suggestions
    if context and context.get("last_results"):
        last_results = context.get("last_results", [])
        if last_results and len(last_results) > 0:
            if intent in ["GET_TOP_SELLING_ITEMS", "GET_ITEMS"]:
                top_item = last_results[0].get("ItemName") or last_results[0].get("name")
                if top_item:
                    suggestions.append(f"Tell me about {top_item}")
                    suggestions.append(f"Price of {top_item}")
    
    # Intent-specific suggestions
    if intent == "GET_TOP_SELLING_ITEMS":
        if language == "sw":
            suggestions.extend(["Top 5 bidhaa", "Top 10 bidhaa", "Bidhaa bora mwezi huu"])
        else:
            suggestions.extend(["Top 5 items", "Top 10 items", "Best sellers this month"])
    
    elif intent == "GET_SLOW_MOVING_ITEMS":
        if language == "sw":
            suggestions.extend(["Bidhaa polepole", "Dead stock", "Bidhaa zisizouzwa"])
        else:
            suggestions.extend(["Slow movers", "Dead stock", "Non-moving items"])
    
    elif intent == "GET_OUTSTANDING_DELIVERIES":
        if language == "sw":
            suggestions.extend(["Onyesha maelezo", "Tengeneza hati", "Usafirishaji uliochelewa"])
        else:
            suggestions.extend(["Show details", "Create delivery note", "Overdue deliveries"])
    
    # Add fallback suggestions if none generated
    if not suggestions:
        suggestions = suggestions_engine.get(intent=intent, entities=entities, language=language)
    
    # Limit to 5 suggestions
    return suggestions[:5]


def _legacy_format(intent: str, api_result, formatter: ResponseFormatter) -> dict:
    """Preserve the original formatter logic for action_router results."""
    if intent == "GET_ITEMS":
        return formatter.format_list("items", api_result)
    elif intent == "GET_CUSTOMERS":
        return formatter.format_list("customers", api_result)
    elif intent in {"GET_INVOICES", "CUSTOMER_INVOICES"}:
        return formatter.format_invoices(api_result)
    elif intent == "GET_SALES_ORDERS":
        return formatter.format_sales_orders(api_result)
    elif intent == "GET_QUOTATIONS":
        return formatter.format_quotations(api_result)
    elif intent in PRICE_INTENTS:
        return formatter.format_prices(api_result)
    elif intent in {"GET_CROSS_SELL", "GET_UPSELL", "GET_SEASONAL_RECOMMENDATIONS", 
                    "GET_TRENDING_PRODUCTS", "FIND_CUSTOMERS_BY_ITEM"}:
        return formatter.format_cross_sell(api_result)
    elif intent == "GET_OUTSTANDING_DELIVERIES":
        # Use the new formatter for outstanding deliveries
        return formatter.format_outstanding_deliveries(api_result)
    else:
        return formatter.format_generic_error({"error": "Data not available."})


def _truncate_large_data(data: Any, max_items: int = 10) -> Any:
    """Truncate large data structures to prevent token limit issues."""
    if isinstance(data, dict):
        truncated = data.copy()
        for key in ['critical_items', 'overstock_items', 'slow_movers', 
                    'fast_movers', 'reorder_recommendations', 'risk_items']:
            if key in truncated and isinstance(truncated[key], list) and len(truncated[key]) > max_items:
                truncated[key] = truncated[key][:max_items]
                truncated[f"{key}_truncated"] = True
                truncated[f"{key}_total"] = len(data[key])
        return truncated
    elif isinstance(data, list):
        if len(data) > max_items:
            return {
                "items": data[:max_items],
                "total": len(data),
                "truncated": True
            }
        return data
    return data


def _create_summary_from_analysis(intent: str, analysis: dict) -> str:
    """Create a text summary from analysis data for LLM narration."""
    if intent == "FIND_CUSTOMERS_BY_ITEM":
        if isinstance(analysis, list) and len(analysis) > 0:
            item_name = analysis[0].get("ItemName", "this product") if analysis else "this product"
            summary = f"Found {len(analysis)} customers who purchase {item_name}"
            if len(analysis) > 0:
                top_customers = [c.get("CardName", "Unknown") for c in analysis[:5]]
                summary += f"\nTop customers: {', '.join(top_customers)}"
            return summary
        return "Customer segmentation analysis completed."
    elif intent == "FORECAST_DEMAND":
        if isinstance(analysis, dict):
            item_name = analysis.get("item_name", "Unknown item")
            forecast = analysis.get("forecast", {})
            next_month = forecast.get("next_month", "N/A")
            confidence = forecast.get("confidence", "N/A")
            return f"Demand forecast for {item_name}: Next month: {next_month} units (Confidence: {confidence}%)"
        return "Demand forecast analysis completed."
    elif intent == "ANALYZE_INVENTORY_HEALTH":
        if isinstance(analysis, dict):
            health_score = analysis.get("health_score", 0)
            total_items = analysis.get("total_items", 0)
            low_stock = analysis.get("low_stock_items", 0)
            overstock = analysis.get("overstock_items", 0)
            return f"Inventory health score: {health_score}/100. Total items: {total_items}, Low stock: {low_stock}, Overstock: {overstock}"
        return "Inventory health analysis completed."
    elif intent == "GET_REORDER_DECISIONS":
        if isinstance(analysis, dict):
            recommendations = analysis.get("recommendations", [])
            if recommendations:
                return f"Found {len(recommendations)} reorder recommendations. Top: {recommendations[0].get('item_name', 'Unknown')} - {recommendations[0].get('reason', 'Reorder needed')}"
            return "No reorder recommendations at this time."
        return "Reorder decision analysis completed."
    elif intent == "GET_TOP_SELLING_ITEMS":
        if isinstance(analysis, list) and len(analysis) > 0:
            top_items = [item.get("ItemName", "Unknown") for item in analysis[:5]]
            return f"Top selling items: {', '.join(top_items)}"
        return "No top selling items found."
    elif intent == "GET_SLOW_MOVING_ITEMS":
        if isinstance(analysis, list) and len(analysis) > 0:
            slow_items = [item.get("ItemName", "Unknown") for item in analysis[:5]]
            return f"Slow moving items: {', '.join(slow_items)}"
        return "No slow moving items found."
    else:
        try:
            compact = {}
            for key, value in analysis.items():
                if isinstance(value, list) and len(value) > 10:
                    compact[key] = value[:10]
                    compact[f"{key}_total"] = len(value)
                else:
                    compact[key] = value
            return json.dumps(compact, default=str)[:3000]
        except:
            return str(analysis)[:2000]


def _format_delivery_response(data: Any, intent: str, language: str) -> str:
    """Format delivery data into a readable response."""
    if not data:
        if language == "sw":
            return "Hakuna taarifa za usafirishaji zilizopatikana."
        return "No delivery information found."
    
    # Use the new formatter for outstanding deliveries
    if intent == "GET_OUTSTANDING_DELIVERIES":
        formatted = formatter.format_outstanding_deliveries(data, language)
        return formatted.get("message", str(data)[:2000])
    
    return str(data)[:2000]


def _extract_delivery_number(message: str, entities: dict) -> Optional[str]:
    """Extract delivery number from message or entities."""
    delivery_num = entities.get("delivery_number") or entities.get("doc_num") or entities.get("order_number")
    if delivery_num:
        return str(delivery_num).strip()
    
    patterns = [
        r'(?:delivery|order|#)\s*(\d{4,8})',
        r'track\s+(\d{4,8})',
        r'status\s+of\s+(?:delivery|order)\s+(\d{4,8})',
        r'(?:delivery|order)\s+number\s+(\d{4,8})',
    ]
    for pattern in patterns:
        match = re.search(pattern, message.lower())
        if match:
            return match.group(1)
    return None


def _extract_customer_for_delivery(message: str, entities: dict) -> Optional[str]:
    """Extract customer name from message or entities for delivery queries."""
    customer = entities.get("customer_name") or entities.get("customer")
    if customer:
        return customer
    
    patterns = [
        r'(?:deliveries?|orders?)\s+(?:for|to|of)\s+([A-Za-z0-9\s&]+?)(?:\?|$|\.)',
        r'(?:track|check|view)\s+(?:delivery|order)\s+(?:for|of)\s+([A-Za-z0-9\s&]+?)(?:\?|$)',
        r'outstanding\s+deliveries?\s+(?:for|to)\s+([A-Za-z0-9\s&]+)',
        r'([A-Za-z0-9\s&]+?)\s+(?:deliveries|orders)',
    ]
    for pattern in patterns:
        match = re.search(pattern, message.lower())
        if match:
            customer = match.group(1).strip()
            stop_words = ['outstanding', 'delivery', 'order', 'show', 'me', 'my', 'all', 'list']
            if customer and customer not in stop_words and len(customer) > 2:
                return customer
    return None


def _resolve_reference_from_context(message: str, context: Dict, entities: Dict) -> tuple:
    """
    Resolve references like "the first one", "its price", "that customer" using conversation context.
    
    Returns:
        Tuple of (resolved_entities, context_used_flag)
    """
    resolved_entities = entities.copy()
    context_used = False
    
    if not context:
        return resolved_entities, False
    
    last_results = context.get("last_results", [])
    referenced_items = context.get("referenced_items", [])
    referenced_customers = context.get("referenced_customers", [])
    
    message_lower = message.lower()
    
    # Check for ordinal references (first, second, third, 1st, 2nd, etc.)
    ordinals = {
        "first": 0, "1st": 0, "one": 0,
        "second": 1, "2nd": 1, "two": 1,
        "third": 2, "3rd": 2, "three": 2,
        "fourth": 3, "4th": 3, "four": 3,
        "fifth": 4, "5th": 4, "five": 4
    }
    
    # Check for item references
    if not resolved_entities.get("item_name"):
        for word, index in ordinals.items():
            if word in message_lower:
                if index < len(last_results):
                    item = last_results[index]
                    resolved_entities["item_name"] = item.get("ItemName") or item.get("name")
                    resolved_entities["_resolved_from_context"] = True
                    context_used = True
                    logger.info(f"Resolved '{word}' to item: {resolved_entities['item_name']}")
                    break
        
        if not context_used and any(word in message_lower for word in ["it", "this", "that", "the item"]):
            if referenced_items and len(referenced_items) > 0:
                resolved_entities["item_name"] = referenced_items[0].get("name")
                resolved_entities["_resolved_from_context"] = True
                context_used = True
                logger.info(f"Resolved reference to item: {resolved_entities['item_name']}")
        
        if not context_used and "price" in message_lower:
            if referenced_items and len(referenced_items) > 0:
                resolved_entities["_price_query"] = True
                resolved_entities["item_name"] = referenced_items[0].get("name")
                context_used = True
                logger.info(f"Resolved price reference for: {resolved_entities['item_name']}")
    
    # Check for customer references
    if not resolved_entities.get("customer_name"):
        for word, index in ordinals.items():
            if word in message_lower:
                if index < len(referenced_customers):
                    customer = referenced_customers[index]
                    resolved_entities["customer_name"] = customer.get("name")
                    resolved_entities["_resolved_from_context"] = True
                    context_used = True
                    logger.info(f"Resolved '{word}' to customer: {resolved_entities['customer_name']}")
                    break
        
        if not context_used and any(word in message_lower for word in ["customer", "them", "they", "that company"]):
            if referenced_customers and len(referenced_customers) > 0:
                resolved_entities["customer_name"] = referenced_customers[0].get("name")
                resolved_entities["_resolved_from_context"] = True
                context_used = True
                logger.info(f"Resolved customer reference: {resolved_entities['customer_name']}")
    
    return resolved_entities, context_used


# ---------------------------------------------------------------------------
# Streaming Response Generator (FIXED: receives intent, entities, token)
# ---------------------------------------------------------------------------

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
    activity_logger = get_activity_logger()
    
    try:
        yield f"data: {json.dumps({'type': 'intent', 'content': intent, 'data': None}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'entities', 'content': '', 'data': entities}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'status', 'content': 'Processing your request...', 'data': None}, ensure_ascii=False)}\n\n"
        
        start_time = asyncio.get_event_loop().time()
        
        if intent in KNOWLEDGE_BASE_INTENTS:
            # Try RAG enhancement for knowledge base queries
            rag_context = await _enhance_with_rag(message, None)
            
            if rag_context:
                prompt = f"""You are the Leysco AI Assistant. Use the following information to answer the user's question.
                
RELEVANT INFORMATION:
{rag_context}

USER QUESTION: {message}

Answer based on the information above. If the information doesn't contain the answer, say so politely.
"""
            else:
                prompt = f"User asked: {message}"
            
            response_text = await llm.generate_async(
                prompt,
                intent=intent,
                language=language,
                max_tokens=400,
            )
            for word in response_text.split():
                yield f"data: {json.dumps({'type': 'text', 'content': word + ' ', 'data': None}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)
        
        elif intent in ACTION_ROUTER_INTENTS:
            yield f"data: {json.dumps({'type': 'status', 'content': 'Fetching data from system...', 'data': None}, ensure_ascii=False)}\n\n"
            api_result = action_router.route(intent, entities, message, language=language)
            if isinstance(api_result, dict) and "message" in api_result:
                response_text = api_result["message"]
            else:
                formatted = _legacy_format(intent, api_result, formatter)
                response_text = formatted.get("message", "I couldn't process your request.")
            for word in response_text.split():
                yield f"data: {json.dumps({'type': 'text', 'content': word + ' ', 'data': None}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)
            if isinstance(api_result, dict) and api_result.get("data"):
                yield f"data: {json.dumps({'type': 'data', 'content': '', 'data': api_result.get('data', [])[:10]}, ensure_ascii=False)}\n\n"
        
        elif intent in DECISION_SUPPORT_INTENTS:
            yield f"data: {json.dumps({'type': 'status', 'content': 'Analyzing data...', 'data': None}, ensure_ascii=False)}\n\n"
            result_data = await decision_support.analyze(intent, entities)
            if result_data and isinstance(result_data, dict):
                # Use formatter for top selling and slow moving items in streaming too
                if intent == "GET_TOP_SELLING_ITEMS":
                    items = result_data.get("items", [])
                    # Fix: Handle None values
                    days = entities.get("days")
                    if days is None or not isinstance(days, int):
                        days = 30
                    limit = entities.get("quantity")
                    if limit is None or not isinstance(limit, int):
                        limit = 10
                    limit = min(limit, len(items)) if items else limit
                    formatted = formatter.format_top_selling_items(
                        items=items,
                        limit=limit,
                        days=days,
                        language=language
                    )
                    response_text = formatted.get("message", "")
                elif intent == "GET_SLOW_MOVING_ITEMS":
                    items = result_data.get("items", [])
                    # Fix: Handle None values
                    days = entities.get("days")
                    if days is None or not isinstance(days, int):
                        days = 90
                    limit = entities.get("quantity")
                    if limit is None or not isinstance(limit, int):
                        limit = 10
                    limit = min(limit, len(items)) if items else limit
                    formatted = formatter.format_slow_moving_items(
                        items=items,
                        limit=limit,
                        days=days,
                        language=language
                    )
                    response_text = formatted.get("message", "")
                else:
                    response_text = _create_summary_from_analysis(intent, result_data)
            else:
                response_text = "Analysis complete. No significant findings."
            for word in response_text.split():
                yield f"data: {json.dumps({'type': 'text', 'content': word + ' ', 'data': None}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)
        
        else:
            yield f"data: {json.dumps({'type': 'status', 'content': 'Searching database...', 'data': None}, ensure_ascii=False)}\n\n"
            if intent in PRICE_INTENTS:
                rows = db.resolve_and_price(
                    item_name=entities.get("item_name") or "",
                    customer_name=entities.get("customer_name") or "" if intent == "GET_CUSTOMER_PRICE" else None,
                )
            else:
                rows = db.query(intent=intent, entities=entities, language=language)
            
            # Use formatter for outstanding deliveries
            if intent == "GET_OUTSTANDING_DELIVERIES" and rows:
                formatted = formatter.format_outstanding_deliveries(rows, language)
                response_text = formatted.get("message", "")
                for word in response_text.split():
                    yield f"data: {json.dumps({'type': 'text', 'content': word + ' ', 'data': None}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.015)
            elif rows:
                response_text = await llm.narrate_async(
                    question=message,
                    db_rows=rows[:20] if isinstance(rows, list) else rows,
                    intent=intent,
                    language=language,
                    max_tokens=500,
                )
                for word in response_text.split():
                    yield f"data: {json.dumps({'type': 'text', 'content': word + ' ', 'data': None}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.015)
            else:
                response_text = await llm.narrate_async(
                    question=message,
                    db_rows=[],
                    intent=intent,
                    language=language,
                    max_tokens=300,
                )
                for word in response_text.split():
                    yield f"data: {json.dumps({'type': 'text', 'content': word + ' ', 'data': None}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.015)
        
        # Store assistant response in memory
        rows_local = rows if 'rows' in locals() else None
        memory.add_message(session_id, "assistant", response_text, rows_local)
        
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        
        # Use feedback-aware suggestions
        suggestions = await _suggest_with_feedback(
            intent=intent,
            entities=entities,
            language=language,
            context=context,
            tenant_code=None,  # Will be set in chat endpoint
            user_id=None
        )
        
        yield f"data: {json.dumps({'type': 'suggestions', 'content': '', 'data': suggestions}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'content': '', 'data': {'processing_time_ms': processing_time}}, ensure_ascii=False)}\n\n"
        
    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        error_msg = "I encountered an issue processing your request. Please try again."
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg, 'data': {'error': str(e)}}, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Chat Endpoint (FIXED: session_id priority, intent classification before streaming)
# ---------------------------------------------------------------------------

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
    
    tenant = TenantContext(
        company_code=company_code,
        company_id=0,
        user_id=conv_context.get("user_id", 0),
        user_email=conv_context.get("user_email", ""),
        user_role=user_role,
        user_token=user_token
    )
    set_current_tenant(tenant)
    
    cache = get_cache_service(ttl_seconds=300)
    
    # Intent classification BEFORE streaming decision
    # Swahili detection
    sw_result = swahili_support.process_swahili_query(message)
    if sw_result.get("detected_language") != "en":
        logger.info("Swahili detected, using Swahili processor")
        initial_entities = sw_result.get("entities", {})
        normalized_message = sw_result.get("normalized_text", message)
        language = sw_result.get("detected_language", "sw")
        if sw_result.get("intent") != "UNKNOWN":
            intent_raw = {"intent": sw_result.get("intent"), "language": language}
        else:
            intent_raw = await intent_classifier.classify_async(normalized_message)
            intent_raw["language"] = language
    else:
        initial_entities = {}
        normalized_message = message
        intent_raw = await intent_classifier.classify_async(message)

    intent = intent_raw.get("intent") if isinstance(intent_raw, dict) else str(intent_raw)
    intent = intent.upper()
    language = (intent_raw.get("language") or "en").lower().strip() if isinstance(intent_raw, dict) else "en"

    # Extract entities
    fresh_entities = await entity_extractor.extract_async(normalized_message, context=conv_context.get("context"))
    logger.info(f"Fresh entities from current message: {fresh_entities}")
    
    # Resolve references from conversation context
    context_data = conv_context.get("context", {})
    resolved_entities, context_used = _resolve_reference_from_context(
        normalized_message, context_data, fresh_entities
    )
    entities = resolved_entities.copy()
    
    logger.info(f"Detected intent: {intent} | language: {language} | user_role: {user_role}")
    performance_monitor.track_request(session_id, {"intent_detection": (asyncio.get_event_loop().time() - start_time) * 1000})
    
    # Handle streaming with classified intent and entities
    if request.stream:
        return StreamingResponse(
            generate_streaming_response(
                message=normalized_message,
                intent=intent,
                entities=entities,
                language=language,
                session_id=session_id,
                user_token=user_token,
                context=conv_context.get("context")
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Content-Type": "text/event-stream; charset=utf-8"
            }
        )
    
    # ========================================================================
    # NON-STREAMING PATH CONTINUES HERE
    # ========================================================================
    
    if intent == "CLARIFY":
        candidates = intent_raw.get("candidates", []) if isinstance(intent_raw, dict) else []
        candidate_labels = {
            "GET_ITEM_PRICE": "Check item price",
            "GET_STOCK_LEVELS": "Check stock levels",
            "GET_CUSTOMER_PRICE": "Customer-specific price",
            "GET_CUSTOMERS": "Browse customers",
            "GET_CUSTOMER_DETAILS": "Customer details",
            "GET_CUSTOMER_ORDERS": "Customer orders",
            "GET_ITEMS": "Browse items",
            "GET_WAREHOUSE_STOCK": "Warehouse stock",
            "GET_WAREHOUSES": "List warehouses",
            "GET_LOW_STOCK_ALERTS": "Low stock alerts",
            "CREATE_QUOTATION": "Create a quotation",
            "GET_QUOTATIONS": "View quotations",
            "RECOMMEND_ITEMS": "Recommend items",
            "GET_TRENDING_PRODUCTS": "Trending products",
            "GET_CROSS_SELL": "Cross-sell suggestions",
            "FIND_CUSTOMERS_BY_ITEM": "Find customers for a product",
            "GET_OUTSTANDING_DELIVERIES": "Check deliveries",
            "TRACK_DELIVERY": "Track delivery",
            "COMPANY_INFO": "Company info",
            "PRODUCT_INFO": "Product info",
            "CONTACT_INFO": "Contact info",
            "GET_TOP_SELLING_ITEMS": "Top selling items",
            "GET_SLOW_MOVING_ITEMS": "Slow moving items",
        }
        chip_messages = [candidate_labels.get(c, c.replace("_", " ").title()) for c in candidates[:3]]
        if language == "sw":
            msg = "Samahani, sikuelewa vizuri. Je, unamaanisha:\n- " + "\n- ".join(chip_messages) + "\n\nTafadhali bonyeza chaguo moja au andika swali lako tena."
        else:
            msg = "I'm not quite sure what you're looking for. Did you mean:\n- " + "\n- ".join(chip_messages) + "\n\nTap one of the options or rephrase your question."
        clear_current_tenant()
        
        # Log clarification
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

    if intent == "UNKNOWN":
        logger.info("Using General AI fallback response")
        ai_reply = await llm.generate_async(
            f"User asked: {message}\nReply naturally.",
            intent="GENERAL",
            language=language,
            max_tokens=300,
        )
        memory.add_message(session_id, "assistant", ai_reply)
        
        await activity_logger.log_query(
            user_id=conv_context.get("user_id", 0),
            user_role=user_role,
            tenant_code=company_code,
            session_id=session_id,
            intent="GENERAL_AI",
            query=message,
            response=ai_reply,
            processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            suggestions_shown=_suggest("GENERAL", initial_entities, language, conv_context.get("context")),
            context_used=False,
            success=True
        )
        
        clear_current_tenant()
        return utf8_json_response(AIResponse(
            intent="GENERAL_AI",
            entities=initial_entities,
            result=ai_reply.strip(),
            data=[],
            suggestions=_suggest("GENERAL", initial_entities, language, conv_context.get("context")),
            session_id=session_id,
            processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
        ).dict())

    if context_used:
        logger.info(f"Context used to resolve entities: {entities}")
    
    if intent in DELIVERY_INTENTS:
        delivery_num = _extract_delivery_number(normalized_message, entities)
        if delivery_num:
            entities["delivery_number"] = delivery_num
        customer = _extract_customer_for_delivery(normalized_message, entities)
        if customer:
            entities["customer_name"] = customer
    
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
    
    logger.info(f"Final entities (current message priority): {entities}")
    performance_monitor.track_request(session_id, {"entity_extraction": (asyncio.get_event_loop().time() - start_time) * 1000})

    intent = apply_intent_overrides(intent, entities)
    logger.info(f"Final intent after overrides: {intent}")
    session_ctx.merge(session_id, entities)

    cached = None
    if intent in PRICE_INTENTS:
        cache_key = f"response:{normalized_message}"
        cached = await cache.get_simple_async(cache_key)
    else:
        cached = await cache.get_async(intent, entities, normalized_message)
    
    if cached is not None:
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
            suggestions=await _suggest_with_feedback(
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

    response = await _route_async(
        intent, entities, normalized_message, language, session_id, user_token,
        llm, formatter, context_data, assigned_customers, user_role
    )
    
    # Add context_used flag to response
    response.context_used = context_used

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
    response.suggestions = await _suggest_with_feedback(
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
    
    # Return with UTF-8 encoding
    return utf8_json_response(response.dict())


# ---------------------------------------------------------------------------
# Async Routing Logic (UPDATED with context and permissions)
# ---------------------------------------------------------------------------

async def _route_async(
    intent: str,
    entities: dict,
    message: str,
    language: str,
    session_id: str,
    user_token: str,
    llm,
    formatter: ResponseFormatter,
    context: Dict = None,
    assigned_customers: List[str] = None,
    user_role: str = "sales_rep"
) -> AIResponse:
    """Async routing with proper await, user token, context awareness, and permissions."""
    
    # Add assigned customers filter for sales reps
    if user_role == "sales_rep" and assigned_customers:
        entities["_assigned_customers"] = assigned_customers
        logger.info(f"Applying assigned customers filter for sales rep: {len(assigned_customers)} customers")
    
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
    
    # Tier 1: Fast conversational responses
    if intent == "GREETING":
        if language == "sw":
            msg = "Habari! Mimi ni Msaidizi wa AI wa Leysco. Ninaweza kukusaidia na bei za bidhaa, hisa, wateja, maagizo, na zaidi. Unahitaji nini?"
        else:
            msg = "Hello! I'm the Leysco AI Assistant. I can help you with items, pricing, stock levels, customers, orders, and more. What would you like to know?"
        return AIResponse(
            intent=intent,
            entities=entities,
            result=msg,
            data=[],
            suggestions=await _suggest_with_feedback(intent, entities, language, context),
            session_id=session_id,
        )

    if intent == "THANKS":
        if language == "sw":
            msg = "Karibu sana! Niambie kama una swali lingine lolote."
        else:
            msg = "You're welcome! Let me know if there's anything else I can help you with."
        return AIResponse(
            intent=intent,
            entities=entities,
            result=msg,
            data=[],
            suggestions=await _suggest_with_feedback(intent, entities, language, context),
            session_id=session_id,
        )

    if intent == "SMALL_TALK":
        answer = await llm.generate_async(
            f"The user sent a short conversational message: \"{message}\"\n"
            f"Reply naturally and briefly as the Leysco AI Assistant.",
            intent="GENERAL",
            max_tokens=80,
            language=language,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=[],
            suggestions=await _suggest_with_feedback(intent, entities, language, context),
            session_id=session_id,
        )

    # Tier 1: Knowledge base
    if intent in KNOWLEDGE_BASE_INTENTS:
        logger.info(f"Tier 1 — Knowledge base: {intent}")
        
        # Try RAG enhancement
        rag_context = await _enhance_with_rag(message, None)
        
        if rag_context:
            prompt = f"""You are the Leysco AI Assistant. Use the following information to answer the user's question.
            
RELEVANT INFORMATION:
{rag_context}

USER QUESTION: {message}

Answer based on the information above. If the information doesn't contain the answer, say so politely.
"""
        else:
            prompt = f"User asked: {message}"
        
        answer = await llm.generate_async(
            prompt,
            intent=intent,
            language=language,
            max_tokens=500,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=[],
            suggestions=await _suggest_with_feedback(intent, entities, language, context),
            session_id=session_id,
        )

    # Tier 2: Delivery Tracking (UPDATED with formatter)
    if intent in DELIVERY_INTENTS:
        logger.info(f"Tier 2 — Delivery tracking: {intent}")
        if intent == "TRACK_DELIVERY":
            delivery_number = entities.get("delivery_number") or entities.get("doc_num")
            if not delivery_number:
                if language == "sw":
                    msg = "Tafadhali toa namba ya usafirishaji. Kwa mfano: 'fuatilia delivery #10045'"
                else:
                    msg = "Please provide a delivery number. For example: 'track delivery #10045'"
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=msg,
                    data=[],
                    suggestions=["track delivery 10045", "check order status"],
                    session_id=session_id,
                )
        
        rows = db.query(intent=intent, entities=entities, language=language)
        
        if rows is None or not rows:
            answer = await llm.generate_async(
                f"User asked about deliveries: {message}",
                intent=intent,
                language=language,
                max_tokens=300,
            )
            return AIResponse(
                intent=intent,
                entities=entities,
                result=answer,
                data=[],
                suggestions=await _suggest_with_feedback(intent, entities, language, context),
                session_id=session_id,
            )
        
        # Use the new formatter for outstanding deliveries
        if intent == "GET_OUTSTANDING_DELIVERIES":
            formatted = formatter.format_outstanding_deliveries(rows, language)
            return AIResponse(
                intent=intent,
                entities=entities,
                result=formatted.get("message", ""),
                data=formatted.get("data", rows),
                suggestions=await _suggest_with_feedback(intent, entities, language, context),
                session_id=session_id,
            )
        
        # For other delivery intents, use existing logic
        if isinstance(rows, list) and len(rows) > 0:
            result_message = _format_delivery_response(rows[0] if len(rows) == 1 else rows, intent, language)
            return AIResponse(
                intent=intent,
                entities=entities,
                result=result_message,
                data=rows,
                suggestions=await _suggest_with_feedback(intent, entities, language, context),
                session_id=session_id,
            )
        
        answer = await llm.narrate_async(
            question=message,
            db_rows=rows,
            intent=intent,
            language=language,
            max_tokens=400,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=rows,
            suggestions=await _suggest_with_feedback(intent, entities, language, context),
            session_id=session_id,
        )

    # Tier 3: Decision support (Manager-only for some intents)
    # FIXED: GET_TOP_SELLING_ITEMS and GET_SLOW_MOVING_ITEMS now use proper formatter
    if intent in DECISION_SUPPORT_INTENTS:
        # Some decision support intents are manager-only
        manager_only_intents = ["ANALYZE_INVENTORY_HEALTH", "GET_REORDER_DECISIONS", "ANALYZE_PRICING_OPPORTUNITIES"]
        if intent in manager_only_intents and user_role != "manager":
            return AIResponse(
                intent=intent,
                entities=entities,
                result="This feature is only available for managers. Please contact your manager for inventory and pricing decisions.",
                data=[],
                suggestions=await _suggest_with_feedback(intent, entities, language, context),
                session_id=session_id,
            )
        
        logger.info(f"Tier 3 — Decision support: {intent}")
        try:
            result_data = await decision_support.analyze(intent, entities)
            if result_data and isinstance(result_data, dict):
                # Use formatter for top selling and slow moving items
                if intent == "GET_TOP_SELLING_ITEMS":
                    items = result_data.get("items", [])
                    # Fix: Handle None values - provide defaults
                    days = entities.get("days")
                    if days is None or not isinstance(days, int):
                        days = 30  # Default to 30 days
                    limit = entities.get("quantity")
                    if limit is None or not isinstance(limit, int):
                        limit = 10  # Default to top 10
                    # Also ensure limit doesn't exceed items length
                    limit = min(limit, len(items)) if items else limit
                    formatted = formatter.format_top_selling_items(
                        items=items,
                        limit=limit,
                        days=days,
                        language=language
                    )
                    return AIResponse(
                        intent=intent,
                        entities=entities,
                        result=formatted.get("message", ""),
                        data=items,
                        suggestions=await _suggest_with_feedback(intent, entities, language, context),
                        session_id=session_id,
                    )
                elif intent == "GET_SLOW_MOVING_ITEMS":
                    items = result_data.get("items", [])
                    # Fix: Handle None values - provide defaults
                    days = entities.get("days")
                    if days is None or not isinstance(days, int):
                        days = 90  # Default to 90 days
                    limit = entities.get("quantity")
                    if limit is None or not isinstance(limit, int):
                        limit = 10  # Default to top 10
                    # Also ensure limit doesn't exceed items length
                    limit = min(limit, len(items)) if items else limit
                    formatted = formatter.format_slow_moving_items(
                        items=items,
                        limit=limit,
                        days=days,
                        language=language
                    )
                    return AIResponse(
                        intent=intent,
                        entities=entities,
                        result=formatted.get("message", ""),
                        data=items,
                        suggestions=await _suggest_with_feedback(intent, entities, language, context),
                        session_id=session_id,
                    )
                elif intent == "GET_SALES_ANALYTICS":
                    formatted = formatter.format_sales_analytics(result_data, language)
                    return AIResponse(
                        intent=intent,
                        entities=entities,
                        result=formatted.get("message", ""),
                        data=result_data,
                        suggestions=await _suggest_with_feedback(intent, entities, language, context),
                        session_id=session_id,
                    )
                else:
                    summary = _create_summary_from_analysis(intent, result_data)
                    return AIResponse(
                        intent=intent,
                        entities=entities,
                        result=summary,
                        data=[result_data],
                        suggestions=await _suggest_with_feedback(intent, entities, language, context),
                        session_id=session_id,
                    )
        except Exception as e:
            logger.error(f"Error in decision support: {e}", exc_info=True)
            answer = await llm.generate_async(
                f"There was an error processing your request for {intent.lower().replace('_', ' ')}.",
                intent=intent,
                language=language,
                max_tokens=200,
            )
            return AIResponse(
                intent=intent,
                entities=entities,
                result=answer,
                data=[],
                suggestions=await _suggest_with_feedback(intent, entities, language, context),
                session_id=session_id,
            )
        
        answer = await llm.generate_async(
            f"No data available for {intent.lower().replace('_', ' ')}.",
            intent=intent,
            language=language,
            max_tokens=200,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=[],
            suggestions=await _suggest_with_feedback(intent, entities, language, context),
            session_id=session_id,
        )

    # Tier 4: DB -> narrate (UPDATED with formatter for deliveries)
    if intent not in ACTION_ROUTER_INTENTS:
        logger.info(f"Tier 4 — DB query + narrate: {intent}")
        if intent in PRICE_INTENTS:
            rows = db.resolve_and_price(
                item_name=entities.get("item_name") or "",
                customer_name=entities.get("customer_name") or "" if intent == "GET_CUSTOMER_PRICE" else None,
            )
        else:
            rows = db.query(intent=intent, entities=entities, language=language)

        if rows is None:
            answer = await llm.generate_async(
                f"User asked: {message}",
                intent=intent,
                language=language,
                max_tokens=300,
            )
            return AIResponse(
                intent=intent,
                entities=entities,
                result=answer,
                data=[],
                suggestions=await _suggest_with_feedback(intent, entities, language, context),
                session_id=session_id,
            )

        if not rows:
            logger.info(f"No data returned for {intent}")
            answer = await llm.narrate_async(
                question=message,
                db_rows=[],
                intent=intent,
                language=language,
                max_tokens=300,
            )
            return AIResponse(
                intent=intent,
                entities=entities,
                result=answer,
                data=[],
                suggestions=await _suggest_with_feedback(intent, entities, language, context),
                session_id=session_id,
            )

        # Use the new formatter for outstanding deliveries
        if intent == "GET_OUTSTANDING_DELIVERIES":
            formatted = formatter.format_outstanding_deliveries(rows, language)
            return AIResponse(
                intent=intent,
                entities=entities,
                result=formatted.get("message", ""),
                data=formatted.get("data", rows),
                suggestions=await _suggest_with_feedback(intent, entities, language, context),
                session_id=session_id,
            )

        if isinstance(rows, list) and len(rows) > 20:
            truncated_rows = rows[:20]
            answer = await llm.narrate_async(
                question=message,
                db_rows=truncated_rows,
                intent=intent,
                language=language,
                max_tokens=600,
            )
            answer += f"\n\n(Showing first 20 of {len(rows)} results)"
        else:
            answer = await llm.narrate_async(
                question=message,
                db_rows=rows,
                intent=intent,
                language=language,
                max_tokens=600,
            )
        
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=rows if isinstance(rows, list) else [rows],
            suggestions=await _suggest_with_feedback(intent, entities, language, context),
            session_id=session_id,
        )

    # Tier 5: action_router (UPDATED with formatter)
    logger.info(f"Tier 5 — Action router: {intent}")
    api_result = action_router.route(intent, entities, message, language=language)
    logger.info(f"API Result type: {type(api_result)}")

    # Special handling for CREATE_QUOTATION to use the nice formatter
    if intent == "CREATE_QUOTATION":
        # Check if we have a successful quotation
        if api_result.get("success") or api_result.get("quotation_id"):
            quotation_id = api_result.get("quotation_id")
            data = api_result.get("data", [{}])[0] if api_result.get("data") else {}
            
            customer_name = data.get("customer_name") or entities.get("customer_name", "")
            items = data.get("items", [])
            total_amount = data.get("total_amount", 0)
            
            # If total_amount is 0, calculate from items
            if total_amount == 0 and items:
                for item in items:
                    price = item.get("price", 0)
                    quantity = item.get("quantity", 1)
                    total_amount += float(price) * float(quantity)
            
            # Get valid until date (30 days from now)
            valid_until = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            
            # Format using the nice formatter
            formatted = formatter.format_quotation_creation_success(
                customer_name=customer_name,
                items=items,
                total_amount=total_amount,
                valid_until=valid_until,
                doc_num=quotation_id,
                language=language
            )
            
            # Ensure UTF-8 encoding
            message_text = ensure_utf8_string(formatted["message"])
            
            return AIResponse(
                intent=intent,
                entities=entities,
                result=message_text,
                data=formatted["data"],
                suggestions=await _suggest_with_feedback(intent, entities, language, context),
                session_id=session_id,
            )
        else:
            # Error case - use error formatter
            error_msg = api_result.get("message", "Failed to create quotation")
            invalid_items = api_result.get("invalid_items", [])
            
            formatted = formatter.format_quotation_creation_error(
                error_message=error_msg,
                invalid_items=invalid_items,
                language=language
            )
            
            return AIResponse(
                intent=intent,
                entities=entities,
                result=formatted["message"],
                data=formatted["data"],
                suggestions=await _suggest_with_feedback(intent, entities, language, context),
                session_id=session_id,
            )

    if intent in RECOMMENDATION_INTENTS:
        if isinstance(api_result, dict):
            formatted = _legacy_format(intent, api_result, formatter)
            result_message = formatted.get("message", "")
            if not result_message:
                result_message = f"I couldn't find any recommendations for {entities.get('item_name', 'this item')}."
        else:
            formatted = _legacy_format(
                intent,
                {"recommendations": api_result if api_result else []},
                formatter,
            )
            result_message = formatted.get("message", "No recommendations found.")
        return AIResponse(
            intent=intent,
            entities=entities,
            result=result_message,
            data=formatted.get("data", []),
            suggestions=await _suggest_with_feedback(intent, entities, language, context),
            session_id=session_id,
        )

    if isinstance(api_result, dict) and "message" in api_result and "ResponseData" not in api_result:
        return AIResponse(
            intent=intent,
            entities=entities,
            result=api_result["message"],
            data=api_result.get("data", []),
            suggestions=await _suggest_with_feedback(intent, entities, language, context),
            session_id=session_id,
        )

    formatted = _legacy_format(intent, api_result, formatter)
    return AIResponse(
        intent=intent,
        entities=entities,
        result=formatted.get("message", "I couldn't process your request."),
        data=formatted.get("data", []),
        suggestions=await _suggest_with_feedback(intent, entities, language, context),
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# QUOTATION ENDPOINTS (FIXED: Added GET by ID)
# ---------------------------------------------------------------------------

@router.get("/quotation/{quotation_id}")
async def get_quotation_by_id(
    quotation_id: str,
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code),
    conv_context: Dict = Depends(get_conversation_context)
):
    """
    Get a single quotation by ID.
    Called by Flutter when user clicks View/Print/Send buttons.
    """
    try:
        # Check authentication
        if not user_token:
            return utf8_json_response({
                "success": False,
                "message": "Not authenticated. Please log in again."
            }, status_code=401)
        
        logger.info(f"Fetching quotation by ID: {quotation_id}")
        
        # Create action router to get API service
        action_router = create_action_router(user_token=user_token)
        
        # Use the action router's quotation service to get by ID (async)
        quotation = await action_router.quotation.get_quotation_by_id(quotation_id)
        
        if not quotation:
            logger.warning(f"Quotation {quotation_id} not found")
            return utf8_json_response({
                "success": False,
                "message": f"Quotation #{quotation_id} not found."
            }, status_code=404)
        
        logger.info(f"Successfully fetched quotation {quotation_id}")
        return utf8_json_response({
            "success": True,
            "quotation": quotation
        })
        
    except Exception as e:
        logger.error(f"Error fetching quotation {quotation_id}: {e}", exc_info=True)
        return utf8_json_response({
            "success": False,
            "message": f"Error fetching quotation: {str(e)}"
        }, status_code=500)


@router.get("/quotations")
async def get_quotations(
    limit: int = Query(10, ge=1, le=100),
    customer: Optional[str] = None,
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code),
    conv_context: Dict = Depends(get_conversation_context)
):
    """
    Get list of quotations.
    Called by Flutter to show quotation history.
    """
    try:
        if not user_token:
            return utf8_json_response({
                "success": False,
                "message": "Not authenticated. Please log in again."
            }, status_code=401)
        
        logger.info(f"Fetching quotations, limit={limit}, customer={customer}")
        
        # Create action router to get API service
        action_router = create_action_router(user_token=user_token)
        
        if customer:
            # Get customer code first
            customer_obj = action_router.api.resolve_customer(customer)
            if customer_obj:
                customer_code = customer_obj.get("CardCode")
                quotations = action_router.quotation.get_customer_quotations(
                    customer_code=customer_code,
                    per_page=limit
                )
            else:
                quotations = []
        else:
            # Get all quotations
            quotations = action_router.api.get_quotations(limit=limit)
        
        return utf8_json_response({
            "success": True,
            "quotations": quotations
        })
        
    except Exception as e:
        logger.error(f"Error fetching quotations: {e}", exc_info=True)
        return utf8_json_response({
            "success": False,
            "message": f"Error fetching quotations: {str(e)}"
        }, status_code=500)


# ---------------------------------------------------------------------------
# Session Management Endpoints
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Proactive Notifications Endpoints
# ---------------------------------------------------------------------------

@router.get("/notifications")
async def get_notifications(
    context: Dict = Depends(get_conversation_context),
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    trigger_scan: bool = Query(False)
):
    """
    Get proactive notifications for the current user.
    Called by Flutter app to show alerts.
    """
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({
            "success": False,
            "message": "User ID not found",
            "notifications": [],
            "unread_count": 0
        })
    
    # Trigger a scan if requested (for testing or manual refresh)
    if trigger_scan:
        asyncio.create_task(
            notification_service.scan_for_user(
                user_id=user_id,
                user_role=context.get("user_role", "sales_rep"),
                tenant_code=context.get("tenant_code", ""),
                user_token=context.get("_token", ""),
                assigned_customers=context.get("assigned_customers", [])
            )
        )
    
    # Get notifications
    notifications = await notification_service.get_notifications(
        user_id=user_id,
        limit=limit,
        unread_only=unread_only
    )
    
    unread_count = await notification_service.get_unread_count(user_id)
    
    return utf8_json_response({
        "success": True,
        "notifications": notifications,
        "unread_count": unread_count,
        "total": len(notifications)
    })


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    context: Dict = Depends(get_conversation_context)
):
    """Mark a notification as read."""
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "message": "User ID not found"})
    
    success = await notification_service.mark_as_read(user_id, notification_id)
    
    return utf8_json_response({
        "success": success,
        "message": "Notification marked as read" if success else "Notification not found"
    })


@router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(
    context: Dict = Depends(get_conversation_context)
):
    """Mark all notifications as read."""
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "message": "User ID not found"})
    
    count = await notification_service.mark_all_as_read(user_id)
    
    return utf8_json_response({
        "success": True,
        "message": f"Marked {count} notifications as read",
        "count": count
    })


@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    context: Dict = Depends(get_conversation_context)
):
    """Delete a notification."""
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "message": "User ID not found"})
    
    success = await notification_service.delete_notification(user_id, notification_id)
    
    return utf8_json_response({
        "success": success,
        "message": "Notification deleted" if success else "Notification not found"
    })


@router.post("/notifications/scan")
async def trigger_notification_scan(
    context: Dict = Depends(require_manager_role)
):
    """
    Manually trigger a notification scan.
    Manager-only endpoint.
    """
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "message": "User ID not found"})
    
    # Run scan
    notifications = await notification_service.scan_for_user(
        user_id=user_id,
        user_role=context.get("user_role", "manager"),
        tenant_code=context.get("tenant_code", ""),
        user_token=context.get("_token", ""),
        assigned_customers=context.get("assigned_customers", [])
    )
    
    await notification_service.save_notifications(user_id, notifications)
    
    return utf8_json_response({
        "success": True,
        "message": f"Scan completed. Found {len(notifications)} notifications.",
        "notifications_count": len(notifications)
    })


@router.get("/notifications/unread-count")
async def get_unread_count(
    context: Dict = Depends(get_conversation_context)
):
    """Get count of unread notifications."""
    notification_service = get_notification_service()
    user_id = context.get("user_id")
    
    if not user_id:
        return utf8_json_response({"success": False, "unread_count": 0})
    
    count = await notification_service.get_unread_count(user_id)
    
    return utf8_json_response({
        "success": True,
        "unread_count": count
    })


# ---------------------------------------------------------------------------
# Proactive Suggestions Endpoint
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ANALYTICS ENDPOINTS (Manager Only)
# ---------------------------------------------------------------------------

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
        # JSON format
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
    
    # Fetch all analytics in parallel
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


# ---------------------------------------------------------------------------
# FEEDBACK LOOP ENDPOINTS
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ML FORECASTING ENDPOINTS (Manager Only)
# ---------------------------------------------------------------------------

@router.post("/forecast/ml")
async def ml_forecast_demand(
    item_code: str,
    item_name: str = None,
    forecast_days: int = Query(30, ge=7, le=90),
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    ML-powered demand forecast.
    Manager-only endpoint.
    """
    ml_service = get_ml_forecasting_service()
    
    # Fetch real historical sales data
    historical_sales = await _get_historical_sales(
        item_code=item_code,
        days=365,
        user_token=user_token,
        company_code=company_code
    )
    
    if not historical_sales:
        return utf8_json_response({
            "success": False,
            "message": f"No historical sales data for item {item_code}. Need at least 90 days of data."
        })
    
    forecast = await ml_service.forecast_demand(
        item_code=item_code,
        item_name=item_name or item_code,
        historical_sales=historical_sales,
        forecast_days=forecast_days
    )
    
    return utf8_json_response({
        "success": True,
        **forecast,
        "data_source": "real" if len(historical_sales) > 0 and historical_sales[0].get("item_code") != "MOCK_ITEM" else "mock"
    })


@router.get("/forecast/seasonal")
async def get_seasonal_forecast(
    item_code: str = None,
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Get seasonal forecast insights.
    Manager-only endpoint.
    """
    # Get historical sales to detect seasonality
    historical_sales = await _get_historical_sales(
        item_code=item_code,
        days=365,
        user_token=user_token,
        company_code=company_code
    )
    
    if not historical_sales:
        return utf8_json_response({
            "success": False,
            "message": f"No historical sales data for item {item_code}."
        })
    
    # Detect seasonal patterns
    from collections import defaultdict
    monthly_totals = defaultdict(float)
    
    for sale in historical_sales:
        try:
            date = datetime.strptime(sale["date"], "%Y-%m-%d")
            month = date.month
            monthly_totals[month] += sale["quantity"]
        except:
            pass
    
    if not monthly_totals:
        return utf8_json_response({
            "success": True,
            "message": "Insufficient data for seasonal detection",
            "seasonal_pattern": None
        })
    
    # Find peak months
    peak_month = max(monthly_totals, key=monthly_totals.get)
    
    month_names = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December"
    }
    
    seasonal_pattern = None
    if peak_month in [3, 4]:
        seasonal_pattern = f"Peak demand in {month_names[peak_month]} (planting season)"
    elif peak_month in [10, 11]:
        seasonal_pattern = f"Peak demand in {month_names[peak_month]} (harvest season)"
    else:
        seasonal_pattern = f"Peak demand in {month_names[peak_month]}"
    
    return utf8_json_response({
        "success": True,
        "item_code": item_code or "ALL",
        "seasonal_pattern": seasonal_pattern,
        "peak_month": month_names.get(peak_month, "Unknown"),
        "monthly_distribution": {month_names.get(m, str(m)): round(qty, 0) for m, qty in monthly_totals.items()},
        "data_source": "real"
    })


# ---------------------------------------------------------------------------
# ANOMALY DETECTION ENDPOINTS (Manager Only)
# ---------------------------------------------------------------------------

@router.post("/anomalies/scan")
async def scan_anomalies(
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Run anomaly detection scan.
    Manager-only endpoint.
    """
    anomaly_service = get_anomaly_detection_service()
    
    results = await anomaly_service.scan_all_anomalies(
        tenant_code=company_code,
        user_token=user_token
    )
    
    # Convert dataclasses to dicts for JSON response
    from dataclasses import asdict
    response = {
        "success": True,
        "sales_anomalies": [asdict(a) for a in results["sales_anomalies"]],
        "stock_anomalies": [asdict(a) for a in results["stock_anomalies"]],
        "pricing_anomalies": [asdict(a) for a in results["pricing_anomalies"]],
        "total_count": len(results["sales_anomalies"]) + len(results["stock_anomalies"]) + len(results["pricing_anomalies"]),
        "timestamp": datetime.now().isoformat()
    }
    
    return utf8_json_response(response)


@router.get("/anomalies/sales")
async def get_sales_anomalies(
    item_code: str = None,
    days: int = Query(30, ge=7, le=90),
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Detect sales anomalies.
    Manager-only endpoint.
    """
    anomaly_service = get_anomaly_detection_service()
    
    anomalies = await anomaly_service.detect_sales_anomalies(
        tenant_code=company_code,
        item_code=item_code,
        days=days,
        user_token=user_token
    )
    
    from dataclasses import asdict
    return utf8_json_response({
        "success": True,
        "anomalies": [asdict(a) for a in anomalies],
        "count": len(anomalies),
        "item_code": item_code or "ALL",
        "days_analyzed": days
    })


@router.get("/anomalies/stock")
async def get_stock_anomalies(
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Detect stock anomalies.
    Manager-only endpoint.
    """
    anomaly_service = get_anomaly_detection_service()
    
    anomalies = await anomaly_service.detect_stock_anomalies(
        tenant_code=company_code,
        user_token=user_token
    )
    
    from dataclasses import asdict
    return utf8_json_response({
        "success": True,
        "anomalies": [asdict(a) for a in anomalies],
        "count": len(anomalies)
    })


@router.get("/anomalies/pricing")
async def get_pricing_anomalies(
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Detect pricing anomalies.
    Manager-only endpoint.
    """
    anomaly_service = get_anomaly_detection_service()
    
    anomalies = await anomaly_service.detect_pricing_anomalies(
        tenant_code=company_code,
        user_token=user_token
    )
    
    from dataclasses import asdict
    return utf8_json_response({
        "success": True,
        "anomalies": [asdict(a) for a in anomalies],
        "count": len(anomalies)
    })


# ---------------------------------------------------------------------------
# RAG (RETRIEVAL-AUGMENTED GENERATION) ENDPOINTS (Manager Only)
# ---------------------------------------------------------------------------

@router.post("/knowledge/ingest")
async def ingest_knowledge_base(
    context: Dict = Depends(require_manager_role)
):
    """
    Ingest all knowledge base content into vector store.
    Manager-only endpoint.
    """
    ingestion_service = get_knowledge_ingestion_service()
    results = await ingestion_service.ingest_all()
    
    vector_store = get_vector_store()
    total_docs = await vector_store.count()
    
    return utf8_json_response({
        "success": True,
        "documents_ingested": results,
        "total_documents": total_docs,
        "message": "Knowledge base ingestion complete"
    })


@router.get("/knowledge/search")
async def search_knowledge_base(
    query: str,
    limit: int = Query(5, ge=1, le=10),
    context: Dict = Depends(require_manager_role)
):
    """
    Search the knowledge base.
    Manager-only endpoint.
    """
    vector_store = get_vector_store()
    results = await vector_store.search(query, limit=limit)
    
    return utf8_json_response({
        "success": True,
        "query": query,
        "results": [
            {
                "content": r["content"],
                "metadata": r["metadata"],
                "similarity": r["similarity"]
            }
            for r in results
        ]
    })


@router.get("/knowledge/stats")
async def get_knowledge_stats(
    context: Dict = Depends(require_manager_role)
):
    """
    Get knowledge base statistics.
    Manager-only endpoint.
    """
    vector_store = get_vector_store()
    total_docs = await vector_store.count()
    
    return utf8_json_response({
        "success": True,
        "total_documents": total_docs,
        "vector_store_type": "postgresql" if vector_store._pg_connection else "in_memory",
        "embedding_dimension": 384
    })


# ---------------------------------------------------------------------------
# KNOWLEDGE GRAPH ENDPOINTS (Manager Only)
# ---------------------------------------------------------------------------

@router.post("/graph/build")
async def build_knowledge_graph(
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Build knowledge graph from sales data.
    Manager-only endpoint.
    """
    from app.services.leysco_api_service import create_api_service
    
    api_service = create_api_service(user_token=user_token)
    kg_service = get_knowledge_graph()
    
    # Fetch data
    logger.info("Fetching data for knowledge graph...")
    
    # Get items
    items = api_service.get_items(limit=1000)
    logger.info(f"Loaded {len(items)} items")
    
    # Get customers
    customers = api_service.get_customers(limit=500)
    logger.info(f"Loaded {len(customers)} customers")
    
    # Get orders for purchase patterns
    orders = []
    for customer in customers[:50]:  # Limit for performance
        customer_orders = api_service.get_customer_orders(
            customer_code=customer.get("CardCode"),
            limit=50
        )
        orders.extend(customer_orders)
    logger.info(f"Loaded {len(orders)} orders")
    
    # Get warehouses
    warehouses = api_service.get_warehouses()
    logger.info(f"Loaded {len(warehouses)} warehouses")
    
    # Build graph
    await kg_service.build_from_sales_data(
        orders=orders,
        items=items,
        customers=customers,
        warehouses=warehouses
    )
    
    stats = kg_service.get_graph_stats()
    
    return utf8_json_response({
        "success": True,
        "message": "Knowledge graph built successfully",
        "stats": stats
    })


@router.get("/graph/recommendations/cross-sell/{product_code}")
async def get_cross_sell_recommendations_graph(
    product_code: str,
    limit: int = Query(5, ge=1, le=20),
    context: Dict = Depends(require_manager_role)
):
    """
    Get cross-sell recommendations from knowledge graph.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    recommendations = await kg_service.get_cross_sell_recommendations(
        product_code=product_code,
        limit=limit
    )
    
    return utf8_json_response({
        "success": True,
        "product_code": product_code,
        "recommendations": recommendations,
        "source": "knowledge_graph"
    })


@router.get("/graph/recommendations/upsell/{product_code}")
async def get_upsell_recommendations_graph(
    product_code: str,
    limit: int = Query(5, ge=1, le=20),
    context: Dict = Depends(require_manager_role)
):
    """
    Get upsell recommendations from knowledge graph.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    recommendations = await kg_service.get_upsell_recommendations(
        product_code=product_code,
        limit=limit
    )
    
    return utf8_json_response({
        "success": True,
        "product_code": product_code,
        "recommendations": recommendations,
        "source": "knowledge_graph"
    })


@router.get("/graph/customer/{customer_code}")
async def get_customer_graph_insights(
    customer_code: str,
    context: Dict = Depends(require_manager_role)
):
    """
    Get customer insights from knowledge graph.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    insights = await kg_service.get_customer_purchase_pattern(customer_code)
    
    return utf8_json_response({
        "success": True,
        **insights,
        "source": "knowledge_graph"
    })


@router.get("/graph/substitutes/{product_code}")
async def get_product_substitutes(
    product_code: str,
    limit: int = Query(5, ge=1, le=20),
    context: Dict = Depends(require_manager_role)
):
    """
    Find substitute products from knowledge graph.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    substitutes = await kg_service.find_substitutes(product_code, limit)
    
    return utf8_json_response({
        "success": True,
        "product_code": product_code,
        "substitutes": substitutes,
        "source": "knowledge_graph"
    })


@router.get("/graph/complements/{product_code}")
async def get_product_complements(
    product_code: str,
    limit: int = Query(5, ge=1, le=20),
    context: Dict = Depends(require_manager_role)
):
    """
    Find complementary products from knowledge graph.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    complements = await kg_service.find_complements(product_code, limit)
    
    return utf8_json_response({
        "success": True,
        "product_code": product_code,
        "complements": complements,
        "source": "knowledge_graph"
    })


@router.get("/graph/stats")
async def get_graph_stats(
    context: Dict = Depends(require_manager_role)
):
    """
    Get knowledge graph statistics.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    stats = kg_service.get_graph_stats()
    
    return utf8_json_response({
        "success": True,
        **stats
    })


@router.get("/graph/export")
async def export_knowledge_graph(
    format: str = Query("json", pattern="^(json|cypher)$"),
    context: Dict = Depends(require_manager_role)
):
    """
    Export knowledge graph for visualization.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    if format == "json":
        export_data = await kg_service.export_graph("json")
        return utf8_json_response({
            "success": True,
            "format": "json",
            **export_data
        })
    else:
        return utf8_json_response({
            "success": True,
            "message": "Cypher export not implemented yet",
            "format": "cypher"
        })


# ---------------------------------------------------------------------------
# Helper Functions for ML Forecasting
# ---------------------------------------------------------------------------

async def _get_historical_sales(
    item_code: str = None,
    days: int = 365,
    user_token: str = None,
    company_code: str = None
) -> List[Dict]:
    """
    Fetch historical sales data from Leysco API for ML forecasting.
    
    Uses Sales Orders (DocType 17) to get demand data.
    """
    from app.services.leysco_api_service import create_api_service
    from collections import defaultdict
    from datetime import datetime, timedelta
    
    # Check cache first
    cache_key = f"historical_sales:{item_code or 'all'}:{days}"
    cache = get_cache_service()
    cached = await cache.get_simple_async(cache_key)
    if cached:
        logger.info(f"Historical sales cache hit for {item_code or 'all'}")
        return cached
    
    try:
        api_service = create_api_service(user_token=user_token)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        url = f"{api_service.base_url}/marketing/docs/17"
        params = {"page": 1, "per_page": 100, "isDoc": 1}
        
        all_orders = []
        page = 1
        total_pages = 1
        
        while page <= total_pages:
            params["page"] = page
            api_service._record_api_call()
            resp = api_service.session.get(url, params=params, timeout=30)
            
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch sales orders: {resp.status_code}")
                break
            
            data = resp.json()
            response_data = data.get("ResponseData", {})
            orders = response_data.get("data", [])
            all_orders.extend(orders)
            
            total = response_data.get("total", 0)
            per_page = response_data.get("per_page", 100)
            total_pages = (total + per_page - 1) // per_page if total > 0 else 1
            page += 1
            
            if len(all_orders) >= 500:
                break
        
        if not all_orders:
            logger.info("No sales orders found, using mock data for testing")
            mock_data = _generate_mock_sales_data(item_code, days)
            await cache.set_simple_async(cache_key, mock_data, ttl=3600)
            return mock_data
        
        daily_totals = defaultdict(float)
        
        for order in all_orders:
            doc_date = order.get("DocDate", "")
            if not doc_date:
                continue
            
            try:
                order_date = datetime.strptime(doc_date, "%Y-%m-%d")
                if order_date < start_date or order_date > end_date:
                    continue
            except:
                pass
            
            lines = order.get("document_lines", [])
            for line in lines:
                line_item_code = line.get("ItemCode", "")
                if item_code and line_item_code != item_code:
                    continue
                
                quantity = float(line.get("Quantity", 0))
                if quantity > 0:
                    daily_totals[doc_date] += quantity
        
        result = [
            {"date": date, "quantity": qty, "item_code": item_code or "ALL"}
            for date, qty in sorted(daily_totals.items())
        ]
        
        logger.info(f"Retrieved {len(result)} days of sales data for {item_code or 'all items'}")
        
        if not result:
            logger.info("No sales data found, using mock data for testing")
            result = _generate_mock_sales_data(item_code, days)
        
        await cache.set_simple_async(cache_key, result, ttl=86400)
        return result
        
    except Exception as e:
        logger.error(f"Error fetching historical sales: {e}", exc_info=True)
        return _generate_mock_sales_data(item_code, days)


def _generate_mock_sales_data(item_code: str = None, days: int = 365) -> List[Dict]:
    """Generate realistic mock sales data for ML forecasting testing."""
    import random
    from datetime import datetime, timedelta
    
    data = []
    start_date = datetime.now() - timedelta(days=days)
    
    if item_code:
        item_lower = item_code.lower()
        if "vegimax" in item_lower or "veg" in item_lower:
            base_demand = 500
        elif "seed" in item_lower:
            base_demand = 800
        elif "fert" in item_lower:
            base_demand = 600
        else:
            base_demand = 400
    else:
        base_demand = 500
    
    for i in range(days):
        date = start_date + timedelta(days=i)
        month = date.month
        
        if month in [3, 4]:
            seasonal_factor = 1.5
        elif month in [10, 11]:
            seasonal_factor = 1.8
        elif month in [12, 1]:
            seasonal_factor = 1.2
        elif month in [7, 8]:
            seasonal_factor = 0.7
        else:
            seasonal_factor = 1.0
        
        weekday = date.weekday()
        weekday_factor = 0.6 if weekday >= 5 else 1.0
        
        quantity = base_demand * seasonal_factor * weekday_factor
        quantity += random.uniform(-50, 50)
        quantity = max(0, round(quantity))
        
        data.append({
            "date": date.strftime("%Y-%m-%d"),
            "quantity": quantity,
            "item_code": item_code or "MOCK_ITEM"
        })
    
    logger.info(f"Generated {len(data)} days of mock sales data")
    return data


# ---------------------------------------------------------------------------
# Dashboard and Cache Endpoints
# ---------------------------------------------------------------------------

@router.get("/dashboard")
def get_dashboard() -> dict[str, Any]:
    svc = get_dashboard_service()
    return svc.get_dashboard()


@router.get("/cache/stats")
def cache_stats():
    return get_cache_service().get_stats()


@router.post("/cache/clear")
def cache_clear(intent: Optional[str] = None, session_id: Optional[str] = None):
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
    return performance_monitor.get_stats()