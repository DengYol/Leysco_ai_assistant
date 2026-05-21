"""Suggestion generation and feedback handling for AI responses"""

from typing import Dict, List, Optional
from app.services.feedback_service import get_feedback_service
from app.ai_engine.suggestions_engine import suggestions_engine
from app.ai_engine.response_formatter import ResponseFormatter
from .constants import PRICE_INTENTS
import logging

logger = logging.getLogger(__name__)


async def get_suggestions_with_feedback(
    intent: str,
    entities: dict,
    language: str,
    context: Dict = None,
    tenant_code: str = None,
    user_id: int = None
) -> list[str]:
    """Get suggestion chips reordered by feedback."""
    suggestions = get_base_suggestions(intent, entities, language, context)
    
    if not suggestions or not tenant_code:
        return suggestions
    
    feedback_service = get_feedback_service()
    reordered = await feedback_service.reorder_suggestions(
        tenant_code=tenant_code,
        intent=intent,
        suggestions=suggestions,
        user_id=user_id
    )
    
    return reordered[:5]


def get_base_suggestions(
    intent: str, 
    entities: dict, 
    language: str, 
    context: Dict = None
) -> list[str]:
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
    
    return suggestions[:5]


def legacy_format(intent: str, api_result, formatter: ResponseFormatter) -> dict:
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
        return formatter.format_outstanding_deliveries(api_result)
    else:
        return formatter.format_generic_error({"error": "Data not available."})


def format_delivery_response(data, intent: str, language: str, formatter: ResponseFormatter) -> str:
    """Format delivery data into a readable response."""
    if not data:
        if language == "sw":
            return "Hakuna taarifa za usafirishaji zilizopatikana."
        return "No delivery information found."
    
    if intent == "GET_OUTSTANDING_DELIVERIES":
        formatted = formatter.format_outstanding_deliveries(data, language)
        return formatted.get("message", str(data)[:2000])
    
    return str(data)[:2000]