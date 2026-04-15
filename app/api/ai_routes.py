"""
app/api/ai_routes.py
====================
AI Chat Endpoint - Optimized with async, caching, and streaming support
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.ai_engine.intent_classifier import IntentClassifier
from app.ai_engine.entity_extractor import EntityExtractor
from app.ai_engine.swahili_support import SwahiliSupport
from app.ai_engine.action_router import ActionRouter
from app.ai_engine.response_formatter import ResponseFormatter
from app.ai_engine.intent_overrides import apply_intent_overrides
from app.ai_engine.decision_support import DecisionSupport
from app.ai_engine.suggestions_engine import suggestions_engine
from app.services.cache_service import get_cache_service
from app.services.db_query_service import DBQueryService
from app.services.llm_service import get_llm_service
from app.services.pricing_service import PricingService
from app.services.dashboard_service import get_dashboard_service
from app.services.session_context import session_ctx
from app.services.performance_monitor import performance_monitor
import logging
import uuid
import re
import json
import asyncio
from typing import Optional, Any, AsyncGenerator

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
action_router = ActionRouter()
formatter = ResponseFormatter()
db = DBQueryService()
llm = get_llm_service(provider="auto")  # Auto-select Gemini or Groq
pricing_service = PricingService()

decision_support = DecisionSupport(
    api=db.api,
    pricing=pricing_service,
    warehouse=None,
    recommender=None,
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
    "GET_TOP_SELLING_ITEMS",      # NEW: Top selling items analytics
    "GET_SLOW_MOVING_ITEMS",       # NEW: Slow moving items analytics
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


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _suggest(intent: str, entities: dict, language: str) -> list[str]:
    """Get suggestion chips for the response."""
    # Analytics-specific suggestions
    if intent == "GET_TOP_SELLING_ITEMS":
        if language == "sw":
            return ["Top 5 bidhaa", "Top 10 bidhaa", "Bidhaa bora mwezi huu"]
        return ["Top 5 items", "Top 10 items", "Best sellers this month"]
    
    if intent == "GET_SLOW_MOVING_ITEMS":
        if language == "sw":
            return ["Bidhaa polepole", "Dead stock", "Bidhaa zisizouzwa"]
        return ["Slow movers", "Dead stock", "Non-moving items"]
    
    return suggestions_engine.get(intent=intent, entities=entities, language=language)


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
    else:
        return formatter.format_generic_error({"error": "Data not available."})


def _truncate_large_data(data: Any, max_items: int = 10) -> Any:
    """
    Truncate large data structures to prevent token limit issues.
    """
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
    """
    Create a text summary from analysis data for LLM narration.
    """
    if intent == "FIND_CUSTOMERS_BY_ITEM":
        if isinstance(analysis, list) and len(analysis) > 0:
            item_name = analysis[0].get("ItemName", "this product") if analysis else "this product"
            summary = f"Found {len(analysis)} customers who purchase {item_name}"
            if len(analysis) > 0:
                top_customers = [c.get("CardName", "Unknown") for c in analysis[:5]]
                summary += f"\nTop customers: {', '.join(top_customers)}"
            return summary
        return "Customer segmentation analysis completed."

    # FIXED: Top selling items summary
    elif intent == "GET_TOP_SELLING_ITEMS":
        if isinstance(analysis, list):
            total_items = len(analysis)
            summary = f"📊 **Top {total_items} Selling Items**\n\n"
            
            for i, item in enumerate(analysis[:10], 1):
                # Get item name - handle different field names
                item_name = item.get("ItemName") or item.get("name") or item.get("Item_Name") or "Unknown"
                item_code = item.get("ItemCode") or item.get("code") or item.get("Item_Code") or ""
                score = item.get("PopularityScore") or item.get("score") or 0
                velocity = item.get("Velocity") or item.get("velocity") or "MEDIUM"
                on_hand = item.get("CurrentOnHand") or item.get("on_hand") or 0
                committed = item.get("CurrentIsCommited") or item.get("committed") or 0
                
                # Choose icon based on velocity
                if velocity == "VERY_HIGH":
                    icon = "🔥🔥"
                elif velocity == "HIGH":
                    icon = "🔥"
                elif velocity == "MEDIUM":
                    icon = "📈"
                elif velocity == "LOW":
                    icon = "📉"
                else:
                    icon = "⭐"
                
                summary += f"{i}. {icon} **{item_name}**"
                if item_code:
                    summary += f" ({item_code})"
                summary += "\n"
                
                if score > 0:
                    summary += f"   • Popularity Score: {score:.0f}/100\n"
                if on_hand > 0:
                    summary += f"   • Current Stock: {on_hand:,.0f} units\n"
                if committed > 0:
                    summary += f"   • Committed Orders: {committed:,.0f} units\n"
                summary += "\n"
            
            if total_items > 10:
                summary += f"\n... and {total_items - 10} more items.\n"
            
            summary += "\n💡 **Tip:** Ask 'Show stock of [item]' to check availability."
            return summary
        
        elif isinstance(analysis, dict):
            items = analysis.get("items", analysis.get("data", []))
            if items:
                return _create_summary_from_analysis(intent, items)
        
        return "Top selling items analysis completed. No data available."

    # FIXED: Slow moving items summary
    elif intent == "GET_SLOW_MOVING_ITEMS":
        if isinstance(analysis, list):
            total_items = len(analysis)
            summary = f"📉 **{total_items} Slow Moving Items**\n\n"
            summary += "⚠️ These items have low sales velocity and may need attention:\n\n"
            
            for i, item in enumerate(analysis[:10], 1):
                # Get item name - handle different field names
                item_name = item.get("ItemName") or item.get("name") or item.get("Item_Name") or "Unknown"
                item_code = item.get("ItemCode") or item.get("code") or item.get("Item_Code") or ""
                turnover = item.get("TurnoverRate") or item.get("turnover") or 0
                on_hand = item.get("CurrentOnHand") or item.get("on_hand") or 0
                committed = item.get("CurrentIsCommited") or item.get("committed") or 0
                severity = item.get("Severity") or item.get("severity") or "monitor"
                recommendation = item.get("Recommendation") or item.get("recommendation") or "Monitor sales"
                
                # Choose icon based on severity
                if severity == "critical":
                    icon = "🔴"
                elif severity == "warning":
                    icon = "🟡"
                else:
                    icon = "🟢"
                
                summary += f"{i}. {icon} **{item_name}**"
                if item_code:
                    summary += f" ({item_code})"
                summary += "\n"
                
                if turnover:
                    summary += f"   • Turnover rate: {turnover}x/year\n"
                if on_hand > 0:
                    summary += f"   • Current stock: {on_hand:,.0f} units\n"
                if committed > 0:
                    summary += f"   • Committed orders: {committed:,.0f} units\n"
                summary += f"   • Recommendation: {recommendation}\n\n"
            
            if total_items > 10:
                summary += f"\n... and {total_items - 10} more slow moving items.\n"
            
            summary += "\n💡 **Tip:** Consider markdowns, promotions, or bundling to clear slow-moving inventory."
            return summary
        
        elif isinstance(analysis, dict):
            items = analysis.get("items", analysis.get("data", []))
            if items:
                return _create_summary_from_analysis(intent, items)
        
        return "Slow moving items analysis completed. No data available."

    elif intent == "ANALYZE_INVENTORY_HEALTH":
        summary = analysis.get("summary", {})
        health_score = analysis.get("health_score", 0)
        health_rating = summary.get("health_rating", "Unknown")
        critical = summary.get("critical_items_count", 0)
        low = summary.get("low_items_count", 0)
        overstock = summary.get("overstock_items_count", 0)
        out_of_stock = summary.get("out_of_stock_count", 0)
        total_value = summary.get("total_inventory_value", 0)
        
        summary_text = f"""
        Inventory Health Analysis:
        - Health Score: {health_score}/100 ({health_rating})
        - Total Value: KES {total_value:,.2f}
        - Critical Items: {critical}
        - Low Stock: {low}
        - Out of Stock: {out_of_stock}
        - Overstock: {overstock}
        - Healthy: {summary.get('healthy_items_count', 0)}
        """
        
        if analysis.get("critical_items") and len(analysis["critical_items"]) > 0:
            summary_text += "\n\nTop Critical Items:\n"
            for item in analysis["critical_items"][:5]:
                summary_text += f"- {item['name']}: {item['available']} units left ({item['days_left']} days)\n"
        
        if analysis.get("reorder_recommendations") and len(analysis["reorder_recommendations"]) > 0:
            summary_text += "\n\nTop Reorder Recommendations:\n"
            for rec in analysis["reorder_recommendations"][:5]:
                summary_text += f"- {rec['name']}: Order {rec['recommended_qty']} units (Current: {rec['current']}, {rec['urgency']} urgency)\n"
        
        return summary_text
    
    elif intent == "GET_REORDER_DECISIONS":
        # Get summary data - handle both direct and nested structures
        if "summary" in analysis:
            summary_data = analysis["summary"]
        else:
            summary_data = analysis
        
        immediate = analysis.get("immediate_orders", [])
        planned = analysis.get("planned_orders", [])
        total_cost = analysis.get("total_reorder_cost", 0)
        priority_summary = analysis.get("priority_summary", {})
        
        critical_count = priority_summary.get("CRITICAL", 0)
        high_count = priority_summary.get("HIGH", 0)
        medium_count = priority_summary.get("MEDIUM", 0)
        
        total_needing_reorder = critical_count + high_count + medium_count
        
        summary_text = f"""
        📊 **Reorder Recommendations**
        
        **Summary:**
        • Items needing reorder: {total_needing_reorder}
        • Critical (out of stock): {critical_count}
        • High priority: {high_count}
        • Medium priority: {medium_count}
        • Estimated total cost: KES {total_cost:,.2f}
        """
        
        # Critical items (immediate orders with CRITICAL urgency)
        critical_items = [item for item in immediate if item.get("urgency") == "CRITICAL"]
        if critical_items:
            summary_text += "\n\n🔴 **CRITICAL - Order Immediately:**\n"
            for item in critical_items[:5]:
                # Handle different field name variations safely
                item_name = item.get("name", item.get("ItemName", "Unknown"))
                available = item.get("available", item.get("current_stock", item.get("Available", 0)))
                days_left = item.get("days_of_stock_left", item.get("days_left", "N/A"))
                recommended_qty = item.get("recommended_qty", item.get("RecommendedQty", 0))
                summary_text += f"• {item_name}: Order {recommended_qty} units (Available: {available}, Days left: {days_left})\n"
        
        # High priority items
        high_items = [item for item in immediate if item.get("urgency") == "HIGH"]
        if high_items:
            summary_text += "\n\n🟠 **HIGH Priority - Order This Week:**\n"
            for item in high_items[:5]:
                item_name = item.get("name", item.get("ItemName", "Unknown"))
                available = item.get("available", item.get("current_stock", item.get("Available", 0)))
                days_left = item.get("days_of_stock_left", item.get("days_left", "N/A"))
                recommended_qty = item.get("recommended_qty", item.get("RecommendedQty", 0))
                summary_text += f"• {item_name}: Order {recommended_qty} units (Available: {available}, Days left: {days_left})\n"
        
        # Medium priority items
        if planned:
            summary_text += f"\n\n🟡 **MEDIUM Priority - Plan for Next Week ({len(planned)} items):**\n"
            for item in planned[:5]:
                item_name = item.get("name", item.get("ItemName", "Unknown"))
                available = item.get("available", item.get("current_stock", item.get("Available", 0)))
                recommended_qty = item.get("recommended_qty", item.get("RecommendedQty", 0))
                summary_text += f"• {item_name}: Order {recommended_qty} units (Available: {available})\n"
        
        if total_needing_reorder == 0:
            summary_text += "\n\n✅ No reorder needed at this time. All inventory levels are adequate."
        
        return summary_text
    
    elif intent == "ANALYZE_PRICING_OPPORTUNITIES":
        drops = analysis.get("price_drops", [])
        hikes = analysis.get("price_hikes", [])
        summary = analysis.get("summary", {})
        
        summary_text = f"""
        Pricing Opportunities:
        - Price Drops: {summary.get('price_drops_found', 0)}
        - Price Hikes: {summary.get('price_hikes_found', 0)}
        - Volume Discount Opportunities: {summary.get('volume_opportunities', 0)}
        """
        
        if drops:
            summary_text += "\n\nBest Price Drops:\n"
            for drop in drops[:3]:
                summary_text += f"- {drop['name']}: Down {drop['drop_percent']}% to KES {drop['current']:,.2f}\n"
        
        if hikes:
            summary_text += "\n\nPrice Increases to Monitor:\n"
            for hike in hikes[:3]:
                summary_text += f"- {hike['name']}: Up {hike['hike_percent']}% to KES {hike['current']:,.2f}\n"
        
        return summary_text
    
    elif intent == "GET_INVENTORY_TURNOVER":
        summary = analysis.get("summary", {})
        
        summary_text = f"""
        Inventory Turnover Analysis:
        - Average Turnover: {summary.get('average_turnover', 0)}x/year
        - High Turnover Items: {summary.get('high_turnover_count', 0)}
        - Low Turnover Items: {summary.get('low_turnover_count', 0)}
        """
        
        if summary.get("top_performers"):
            summary_text += "\n\nTop Performers:\n"
            for item in summary["top_performers"][:3]:
                summary_text += f"- {item.get('ItemName', 'Unknown')}: {item.get('TurnoverRate', 0)}x/year\n"
        
        if summary.get("slow_movers"):
            summary_text += "\n\nSlow Movers:\n"
            for item in summary["slow_movers"][:3]:
                summary_text += f"- {item.get('ItemName', 'Unknown')}: {item.get('TurnoverRate', 0)}x/year\n"
        
        return summary_text
    
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
    """
    Format delivery data into a readable response.
    Shows completed deliveries from previous weeks clearly.
    """
    if not data:
        if language == "sw":
            return "Hakuna taarifa za usafirishaji zilizopatikana."
        else:
            return "No delivery information found."
    
    if isinstance(data, dict):
        # Handle delivery status summary
        if "analysis_type" in data and data["analysis_type"] == "delivery_status":
            summary = data.get("summary", {})
            customer = data.get("customer", "All Customers")
            
            response = f"📦 **Delivery Status Report**\n"
            if customer != "All Customers":
                response += f"**Customer:** {customer}\n"
            response += f"**As of:** {data.get('as_of_date', 'Today')}\n\n"
            
            # Get summary stats
            completed_today = summary.get('completed_today', 0)
            completed_this_week = summary.get('completed_this_week', 0)
            in_transit = summary.get('in_transit', 0)
            pending = summary.get('pending', 0)
            overdue = summary.get('overdue', 0)
            total_deliveries = summary.get('total', 0)
            
            # Calculate completed from previous weeks
            completed_previous = total_deliveries - (completed_today + completed_this_week + in_transit + pending + overdue)
            
            response += f"**Summary:**\n"
            response += f"• ✅ Completed Today: {completed_today}\n"
            response += f"• ✅ Completed This Week: {completed_this_week}\n"
            if completed_previous > 0:
                response += f"• ✅ Completed Previously: {completed_previous}\n"
            response += f"• 🚚 In Transit: {in_transit}\n"
            response += f"• ⏳ Pending: {pending}\n"
            response += f"• ⚠️ Overdue: {overdue}\n"
            response += f"• 📦 Total Deliveries: {total_deliveries}\n\n"
            
            # Show completed today
            if data.get("completed_today"):
                response += f"**✅ Completed Today ({len(data['completed_today'])})**\n"
                for delivery in data["completed_today"][:5]:
                    if isinstance(delivery, dict):
                        response += f"• Delivery #{delivery.get('doc_num', 'N/A')} - {delivery.get('customer_name', 'Unknown')}\n"
                response += "\n"
            
            # Show completed this week
            if data.get("completed_this_week"):
                response += f"**✅ Completed This Week ({len(data['completed_this_week'])})**\n"
                for delivery in data["completed_this_week"][:5]:
                    if isinstance(delivery, dict):
                        response += f"• Delivery #{delivery.get('doc_num', 'N/A')} - {delivery.get('customer_name', 'Unknown')}\n"
                        if delivery.get('doc_date'):
                            response += f"  Completed: {delivery.get('doc_date')}\n"
                response += "\n"
            
            # Show completed previously (sample)
            if completed_previous > 0:
                response += f"**✅ Completed Previously ({completed_previous} deliveries)**\n"
                all_completed = data.get("completed_this_week", []) + data.get("completed_today", [])
                if all_completed:
                    for delivery in all_completed[:3]:
                        if isinstance(delivery, dict):
                            response += f"• Delivery #{delivery.get('doc_num', 'N/A')} - {delivery.get('customer_name', 'Unknown')}\n"
                            if delivery.get('doc_date'):
                                response += f"  Completed: {delivery.get('doc_date')}\n"
                else:
                    response += f"These deliveries were completed before this week.\n"
                
                response += f"\n💡 **Tip:** To see older deliveries, ask: 'Show deliveries from last month' or 'Show completed deliveries for March 2026'\n\n"
            
            # Show in transit
            if data.get("in_transit"):
                response += f"**🚚 In Transit ({len(data['in_transit'])})**\n"
                for delivery in data["in_transit"][:5]:
                    if isinstance(delivery, dict):
                        progress = delivery.get('completion_percentage', 0)
                        response += f"• Delivery #{delivery.get('doc_num', 'N/A')} - {progress}% delivered\n"
                        if delivery.get('doc_due_date'):
                            response += f"  Expected: {delivery.get('doc_due_date')}\n"
                response += "\n"
            
            # Show pending
            if data.get("pending"):
                response += f"**⏳ Pending ({len(data['pending'])})**\n"
                for delivery in data["pending"][:5]:
                    if isinstance(delivery, dict):
                        response += f"• Delivery #{delivery.get('doc_num', 'N/A')} - Due: {delivery.get('doc_due_date', 'N/A')}\n"
                response += "\n"
            
            # Show overdue
            if data.get("overdue"):
                response += f"**⚠️ Overdue ({len(data['overdue'])})**\n"
                for delivery in data["overdue"][:5]:
                    if isinstance(delivery, dict):
                        response += f"• Delivery #{delivery.get('doc_num', 'N/A')} - Due: {delivery.get('doc_due_date', 'N/A')}\n"
                response += "\n"
            
            if overdue > 0:
                response += "⚠️ **Action Required:** Overdue deliveries need immediate attention.\n"
            
            return response
        
        # Handle single delivery details
        elif "doc_num" in data:
            response = f"📦 **Delivery #{data.get('doc_num', 'N/A')}**\n\n"
            response += f"**Customer:** {data.get('customer_name', 'Unknown')}\n"
            response += f"**Date:** {data.get('doc_date', 'N/A')}\n"
            response += f"**Due Date:** {data.get('doc_due_date', 'N/A')}\n"
            response += f"**Status:** {data.get('status', 'Unknown')}\n"
            response += f"**Progress:** {data.get('completion_percentage', 0)}% completed\n"
            response += f"**Items:** {data.get('item_count', 0)} items\n"
            response += f"**Total Value:** KES {data.get('total_value', 0):,.2f}\n\n"
            
            if data.get("items"):
                response += f"**Items:**\n"
                for item in data["items"][:5]:
                    response += f"• {item.get('item_name', 'Unknown')}: {item.get('quantity', 0)} units"
                    if item.get('delivered', 0) > 0:
                        response += f" ({item.get('delivered', 0)} delivered)"
                    response += "\n"
            
            return response
    
    elif isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], dict):
            if "doc_num" in data[0]:
                response = f"📦 **Deliveries**\n\n"
                # Count by status
                status_counts = {}
                for delivery in data:
                    status = delivery.get('status', 'Unknown')
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                response += f"**Total: {len(data)} deliveries**\n"
                for status, count in status_counts.items():
                    response += f"• {status}: {count}\n"
                response += "\n"
                
                # Show recent deliveries
                response += f"**Recent Deliveries:**\n"
                for delivery in data[:10]:
                    response += f"• Delivery #{delivery.get('doc_num', 'N/A')} - {delivery.get('customer_name', 'Unknown')}\n"
                    response += f"  Date: {delivery.get('doc_date', 'N/A')} | Status: {delivery.get('status', 'Unknown')}\n"
                if len(data) > 10:
                    response += f"\n... and {len(data) - 10} more deliveries."
                return response
    
    # Fallback to JSON string
    return str(data)[:2000]


def _extract_delivery_number(message: str, entities: dict) -> Optional[str]:
    """
    Extract delivery number from message or entities.
    """
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
    """
    Extract customer name from message or entities for delivery queries.
    """
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


# ---------------------------------------------------------------------------
# Streaming Response Generator
# ---------------------------------------------------------------------------

async def generate_streaming_response(
    message: str,
    intent: str,
    entities: dict,
    language: str,
    session_id: str,
) -> AsyncGenerator[str, None]:
    """Generate streaming response with progressive updates."""
    try:
        # Step 1: Send intent immediately
        yield f"data: {json.dumps({'type': 'intent', 'content': intent, 'data': None})}\n\n"
        
        # Step 2: Send entities
        yield f"data: {json.dumps({'type': 'entities', 'content': '', 'data': entities})}\n\n"
        
        # Step 3: Start processing
        yield f"data: {json.dumps({'type': 'status', 'content': '🔍 Processing your request...', 'data': None})}\n\n"
        
        # Step 4: Process the request
        start_time = asyncio.get_event_loop().time()
        
        # Route based on intent type
        if intent in KNOWLEDGE_BASE_INTENTS:
            response_text = await llm.generate_async(
                f"User asked: {message}",
                intent=intent,
                language=language,
                max_tokens=400,
            )
            
            # Stream the response word by word
            for word in response_text.split():
                yield f"data: {json.dumps({'type': 'text', 'content': word + ' ', 'data': None})}\n\n"
                await asyncio.sleep(0.02)  # Natural typing speed
            
        elif intent in ACTION_ROUTER_INTENTS:
            yield f"data: {json.dumps({'type': 'status', 'content': '📊 Fetching data from system...', 'data': None})}\n\n"
            
            # Call action router
            api_result = action_router.route(intent, entities, message, language=language)
            
            if isinstance(api_result, dict) and "message" in api_result:
                response_text = api_result["message"]
            else:
                formatted = _legacy_format(intent, api_result, formatter)
                response_text = formatted.get("message", "I couldn't process your request.")
            
            # Stream the response
            for word in response_text.split():
                yield f"data: {json.dumps({'type': 'text', 'content': word + ' ', 'data': None})}\n\n"
                await asyncio.sleep(0.01)
            
            # Send data if available
            if api_result.get("data"):
                yield f"data: {json.dumps({'type': 'data', 'content': '', 'data': api_result.get('data', [])[:10]})}\n\n"
        
        elif intent in DECISION_SUPPORT_INTENTS:
            yield f"data: {json.dumps({'type': 'status', 'content': '📈 Analyzing data...', 'data': None})}\n\n"
            
            # Handle top selling and slow moving items directly
            if intent == "GET_TOP_SELLING_ITEMS":
                limit = entities.get("quantity") or 10
                if isinstance(limit, str) and limit.isdigit():
                    limit = int(limit)
                elif not isinstance(limit, int):
                    limit = 10
                
                days = entities.get("days") or 30
                rows = db.api.get_top_selling_items(limit=limit, days=days)
                
                if rows:
                    truncated_data = _truncate_large_data(rows, max_items=limit)
                    summary = _create_summary_from_analysis(intent, truncated_data)
                    response_text = summary
                else:
                    response_text = "Unable to fetch top selling items at this time."
            
            elif intent == "GET_SLOW_MOVING_ITEMS":
                limit = entities.get("quantity") or 10
                if isinstance(limit, str) and limit.isdigit():
                    limit = int(limit)
                elif not isinstance(limit, int):
                    limit = 10
                
                days = entities.get("days") or 90
                turnover_threshold = entities.get("turnover_threshold") or 0.5
                rows = db.api.get_slow_moving_items(limit=limit, days=days, turnover_threshold=turnover_threshold)
                
                if rows:
                    truncated_data = _truncate_large_data(rows, max_items=limit)
                    summary = _create_summary_from_analysis(intent, truncated_data)
                    response_text = summary
                else:
                    response_text = "Unable to fetch slow moving items at this time."
            
            else:
                result_data = await decision_support.analyze(intent, entities)
                
                if result_data and isinstance(result_data, dict):
                    summary = _create_summary_from_analysis(intent, result_data)
                    response_text = summary
                else:
                    response_text = "Analysis complete. No significant findings."
            
            # Stream the response
            for word in response_text.split():
                yield f"data: {json.dumps({'type': 'text', 'content': word + ' ', 'data': None})}\n\n"
                await asyncio.sleep(0.01)
        
        else:
            # Tier 4: DB query
            yield f"data: {json.dumps({'type': 'status', 'content': '🔎 Searching database...', 'data': None})}\n\n"
            
            if intent in PRICE_INTENTS:
                rows = db.resolve_and_price(
                    item_name=entities.get("item_name") or "",
                    customer_name=entities.get("customer_name") or "" if intent == "GET_CUSTOMER_PRICE" else None,
                )
            else:
                rows = db.query(intent=intent, entities=entities, language=language)
            
            if rows:
                response_text = await llm.narrate_async(
                    question=message,
                    db_rows=rows[:20] if isinstance(rows, list) else rows,
                    intent=intent,
                    language=language,
                    max_tokens=500,
                )
            else:
                response_text = await llm.narrate_async(
                    question=message,
                    db_rows=[],
                    intent=intent,
                    language=language,
                    max_tokens=300,
                )
            
            # Stream the response
            for word in response_text.split():
                yield f"data: {json.dumps({'type': 'text', 'content': word + ' ', 'data': None})}\n\n"
                await asyncio.sleep(0.015)
        
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        
        # Step 5: Send suggestions
        suggestions = _suggest(intent, entities, language)
        yield f"data: {json.dumps({'type': 'suggestions', 'content': '', 'data': suggestions})}\n\n"
        
        # Step 6: Send completion
        yield f"data: {json.dumps({'type': 'done', 'content': '', 'data': {'processing_time_ms': processing_time}})}\n\n"
        
    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        error_msg = "I encountered an issue processing your request. Please try again."
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg, 'data': {'error': str(e)}})}\n\n"


# ---------------------------------------------------------------------------
# Chat Endpoint - Optimized with streaming
# ---------------------------------------------------------------------------

@router.post("/chat")
async def chat_ai(request: AIRequest):
    """Process chat messages with AI-powered intent recognition and optional streaming."""
    start_time = asyncio.get_event_loop().time()
    message = request.message.strip()
    
    if not message:
        return AIResponse(
            intent="EMPTY",
            entities={},
            result="Please enter a message.",
            data=[],
            suggestions=[],
            session_id=request.session_id or str(uuid.uuid4()),
            processing_time_ms=0,
        )
    
    cache = get_cache_service(ttl_seconds=300)
    session_id = request.session_id or str(uuid.uuid4())
    
    # Enable streaming if requested
    if request.stream:
        return StreamingResponse(
            generate_streaming_response(message, "", {}, "en", session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    
    # ── 0. Swahili detection ───────────────────────────────────────────────────
    sw_result = swahili_support.process_swahili_query(message)
    
    if sw_result.get("detected_language") != "en":
        logger.info("🇰🇪 Swahili detected, using Swahili processor")
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

    # ── 1. Extract intent and language ──────────────────────────────────────
    intent = intent_raw.get("intent") if isinstance(intent_raw, dict) else str(intent_raw)
    intent = intent.upper()
    language = (intent_raw.get("language") or "en").lower().strip() if isinstance(intent_raw, dict) else "en"

    logger.info(f"Detected intent: {intent} | language: {language}")
    performance_monitor.track_request(session_id, {"intent_detection": (asyncio.get_event_loop().time() - start_time) * 1000})

    # ── CLARIFY: low-confidence intent ──────────────────────────────────────
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
        
        chip_messages = [
            candidate_labels.get(c, c.replace("_", " ").title())
            for c in candidates[:3]
        ]
        
        if language == "sw":
            msg = "Samahani, sikuelewa vizuri. Je, unamaanisha:\n- " + "\n- ".join(chip_messages) + "\n\nTafadhali bonyeza chaguo moja au andika swali lako tena."
        else:
            msg = "I'm not quite sure what you're looking for. Did you mean:\n- " + "\n- ".join(chip_messages) + "\n\nTap one of the options or rephrase your question."

        return AIResponse(
            intent="CLARIFY",
            entities=initial_entities,
            result=msg,
            data=[],
            suggestions=chip_messages,
            session_id=session_id,
            processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
        )

    # ── 2. General AI fallback (UNKNOWN) ────────────────────────────────────
    if intent == "UNKNOWN":
        logger.info("Using General AI fallback response")
        ai_reply = await llm.generate_async(
            f"User asked: {message}\nReply naturally.",
            intent="GENERAL",
            language=language,
            max_tokens=300,
        )
        return AIResponse(
            intent="GENERAL_AI",
            entities=initial_entities,
            result=ai_reply.strip(),
            data=[],
            suggestions=_suggest("GENERAL", initial_entities, language),
            session_id=session_id,
            processing_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
        )

    # ── 3. Extract entities (async) ─────────────────────────────────────────
    fresh_entities = await entity_extractor.extract_async(normalized_message)
    logger.info(f"Fresh entities from current message: {fresh_entities}")
    
    entities = fresh_entities.copy()
    
    # Enhanced entity extraction for delivery queries
    if intent in DELIVERY_INTENTS:
        delivery_num = _extract_delivery_number(normalized_message, entities)
        if delivery_num:
            entities["delivery_number"] = delivery_num
            logger.info(f"Extracted delivery number: {delivery_num}")
        
        customer = _extract_customer_for_delivery(normalized_message, entities)
        if customer:
            entities["customer_name"] = customer
            logger.info(f"Extracted customer for delivery: {customer}")
    
    # Extract limit for analytics queries
    if intent in ["GET_TOP_SELLING_ITEMS", "GET_SLOW_MOVING_ITEMS"]:
        # Check for number in message like "top 5", "top 10"
        limit_match = re.search(r'top\s+(\d+)', normalized_message.lower())
        if limit_match:
            entities["quantity"] = int(limit_match.group(1))
            logger.info(f"Extracted limit from message: {entities['quantity']}")
        
        # Check for days in message like "last 30 days", "this month"
        days_match = re.search(r'last\s+(\d+)\s+days', normalized_message.lower())
        if days_match:
            entities["days"] = int(days_match.group(1))
            logger.info(f"Extracted days from message: {entities['days']}")
    
    logger.info(f"Final entities (current message priority): {entities}")
    performance_monitor.track_request(session_id, {"entity_extraction": (asyncio.get_event_loop().time() - start_time) * 1000})

    # ── 4. Apply intent overrides ───────────────────────────────────────────
    intent = apply_intent_overrides(intent, entities)
    logger.info(f"Final intent after overrides: {intent}")

    session_ctx.merge(session_id, entities)

    # ── 5. Cache check (optimized for price queries) ────────────────────────
    cached = None
    if intent in PRICE_INTENTS:
        # Use simple cache for faster lookup on price queries
        cache_key = f"response:{normalized_message}"
        cached = await cache.get_simple_async(cache_key)
    else:
        cached = await cache.get_async(intent, entities, normalized_message)
    
    if cached is not None:
        logger.info(f"⚡ Cache HIT for '{message}'")
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        return AIResponse(
            intent=cached.get("intent", intent),
            entities=cached.get("entities", entities),
            result=cached.get("result", ""),
            data=cached.get("data", []),
            suggestions=_suggest(intent, entities, language),
            session_id=session_id,
            processing_time_ms=processing_time,
        )

    # ── 6. Route (async) ────────────────────────────────────────────────────
    response = await _route_async(
        intent, entities, normalized_message, language, session_id,
        llm, db, action_router, formatter, decision_support,
    )

    # ── 7. Cache and return (optimized for price queries) ───────────────────
    if cache.should_cache(intent):
        logger.info(f"📝 Caching response for '{message}'")
        if intent in PRICE_INTENTS:
            # Use simple cache for price queries with longer TTL
            cache_key = f"response:{normalized_message}"
            await cache.set_simple_async(cache_key, response.dict(), ttl=3600)
        else:
            await cache.set_async(intent, entities, normalized_message, response.dict())
    
    response.processing_time_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
    performance_monitor.track_request(session_id, {"total": response.processing_time_ms})
    
    return response


# ---------------------------------------------------------------------------
# Async Routing Logic
# ---------------------------------------------------------------------------

async def _route_async(
    intent: str,
    entities: dict,
    message: str,
    language: str,
    session_id: str,
    llm,
    db: DBQueryService,
    action_router: ActionRouter,
    formatter: ResponseFormatter,
    decision_support: DecisionSupport,
) -> AIResponse:
    """
    Async routing with proper await for decision support and token limit handling.
    """
    # ── Tier 1: Fast conversational responses ───────────────────────────────
    if intent == "GREETING":
        if language == "sw":
            msg = "Habari! Mimi ni Msaidizi wa AI wa Leysco. Ninaweza kukusaidia na bei za bidhaa, hisa, wateja, maagizo, na zaidi. Unahitaji nini?"
        elif language == "mixed":
            msg = "Habari! I'm the Leysco AI Assistant. Ninaweza kukusaidia na items, pricing, stock levels, customers, orders, na zaidi. What would you like to know?"
        else:
            msg = "Hello! I'm the Leysco AI Assistant. I can help you with items, pricing, stock levels, customers, orders, and more. What would you like to know?"
        return AIResponse(
            intent=intent,
            entities=entities,
            result=msg,
            data=[],
            suggestions=_suggest(intent, entities, language),
            session_id=session_id,
        )

    if intent == "THANKS":
        if language == "sw":
            msg = "Karibu sana! Niambie kama una swali lingine lolote."
        elif language == "mixed":
            msg = "You're welcome! Niambie kama kuna kitu kingine ninachoweza kukusaidia nacho."
        else:
            msg = "You're welcome! Let me know if there's anything else I can help you with."
        return AIResponse(
            intent=intent,
            entities=entities,
            result=msg,
            data=[],
            suggestions=_suggest(intent, entities, language),
            session_id=session_id,
        )

    if intent == "SMALL_TALK":
        answer = await llm.generate_async(
            f"The user sent a short conversational message: \"{message}\"\n"
            f"Reply naturally and briefly as the Leysco AI Assistant. "
            f"If appropriate, invite them to ask about items, pricing, or customers.",
            intent="GENERAL",
            max_tokens=80,
            language=language,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=[],
            suggestions=_suggest(intent, entities, language),
            session_id=session_id,
        )

    # ── Tier 1: Knowledge base ──────────────────────────────────────────────
    if intent in KNOWLEDGE_BASE_INTENTS:
        logger.info(f"📚 Tier 1 — Knowledge base: {intent}")
        answer = await llm.generate_async(
            f"User asked: {message}",
            intent=intent,
            language=language,
            max_tokens=500,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=[],
            suggestions=_suggest(intent, entities, language),
            session_id=session_id,
        )

    # ── Tier 2: Delivery Tracking ───────────────────────────────────────────
    if intent in DELIVERY_INTENTS:
        logger.info(f"📦 Tier 2 — Delivery tracking: {intent}")
        
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
                suggestions=_suggest(intent, entities, language),
                session_id=session_id,
            )
        
        if isinstance(rows, list) and len(rows) > 0:
            result_message = _format_delivery_response(rows[0] if len(rows) == 1 else rows, intent, language)
            return AIResponse(
                intent=intent,
                entities=entities,
                result=result_message,
                data=rows,
                suggestions=_suggest(intent, entities, language),
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
            suggestions=_suggest(intent, entities, language),
            session_id=session_id,
        )

    # ── Tier 3: Decision support ────────────────────────────────────────────
    if intent in DECISION_SUPPORT_INTENTS:
        logger.info(f"📊 Tier 3 — Decision support: {intent}")

        # FIXED: Handle top selling items - pass actual data to LLM
        if intent == "GET_TOP_SELLING_ITEMS":
            limit = entities.get("quantity") or 10
            if isinstance(limit, str) and limit.isdigit():
                limit = int(limit)
            elif not isinstance(limit, int):
                limit = 10
            
            days = entities.get("days") or 30
            logger.info(f"📊 Fetching top {limit} selling items (last {days} days)")
            
            rows = db.api.get_top_selling_items(limit=limit, days=days)
            
            if rows and isinstance(rows, list) and len(rows) > 0:
                # Log the first item for debugging
                logger.info(f"Sample top item: {rows[0].get('ItemName')} (Score: {rows[0].get('PopularityScore')})")
                
                truncated_data = _truncate_large_data(rows, max_items=limit)
                
                try:
                    # Pass the actual data to LLM, not just the summary
                    answer = await llm.narrate_async(
                        question=message,
                        db_rows=truncated_data if isinstance(truncated_data, list) else rows[:limit],
                        intent=intent,
                        language=language,
                        max_tokens=800,
                    )
                except Exception as e:
                    logger.warning(f"LLM narration failed: {e}, using fallback")
                    summary = _create_summary_from_analysis(intent, truncated_data)
                    answer = f"Here are the top {limit} selling items:\n\n{summary}"
                
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=answer,
                    data=truncated_data if isinstance(truncated_data, list) else rows[:limit],
                    suggestions=_suggest(intent, entities, language),
                    session_id=session_id,
                )
            else:
                answer = "No top selling items data available at this time. Try again when there's more sales history."
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=answer,
                    data=[],
                    suggestions=_suggest(intent, entities, language),
                    session_id=session_id,
                )

        # FIXED: Handle slow moving items - pass actual data to LLM
        if intent == "GET_SLOW_MOVING_ITEMS":
            limit = entities.get("quantity") or 10
            if isinstance(limit, str) and limit.isdigit():
                limit = int(limit)
            elif not isinstance(limit, int):
                limit = 10
            
            days = entities.get("days") or 90
            turnover_threshold = entities.get("turnover_threshold") or 0.5
            
            logger.info(f"📊 Fetching slow moving items (limit={limit}, days={days}, threshold={turnover_threshold})")
            
            rows = db.api.get_slow_moving_items(limit=limit, days=days, turnover_threshold=turnover_threshold)
            
            if rows and isinstance(rows, list) and len(rows) > 0:
                # Log the first item for debugging
                logger.info(f"Sample slow item: {rows[0].get('ItemName')} (Turnover: {rows[0].get('TurnoverRate')})")
                
                truncated_data = _truncate_large_data(rows, max_items=limit)
                
                try:
                    # Pass the actual data to LLM, not just the summary
                    answer = await llm.narrate_async(
                        question=message,
                        db_rows=truncated_data if isinstance(truncated_data, list) else rows[:limit],
                        intent=intent,
                        language=language,
                        max_tokens=800,
                    )
                except Exception as e:
                    logger.warning(f"LLM narration failed: {e}, using fallback")
                    summary = _create_summary_from_analysis(intent, truncated_data)
                    answer = f"Here are the slow moving items:\n\n{summary}"
                
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=answer,
                    data=truncated_data if isinstance(truncated_data, list) else rows[:limit],
                    suggestions=_suggest(intent, entities, language),
                    session_id=session_id,
                )
            else:
                answer = "No slow moving items found. All inventory appears to be moving well!"
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=answer,
                    data=[],
                    suggestions=_suggest(intent, entities, language),
                    session_id=session_id,
                )

        try:
            result_data = await decision_support.analyze(intent, entities)
            
            if result_data and isinstance(result_data, dict) and result_data.get("error"):
                answer = await llm.generate_async(
                    f"User asked about {intent.lower().replace('_', ' ')}. "
                    f"Error: {result_data.get('message', 'Unable to process request')}. "
                    f"Provide a helpful response suggesting alternatives.",
                    intent=intent,
                    language=language,
                    max_tokens=300,
                )
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=answer,
                    data=[],
                    suggestions=_suggest(intent, entities, language),
                    session_id=session_id,
                )

            if result_data:
                truncated_data = _truncate_large_data(result_data, max_items=10)
                
                try:
                    answer = await llm.narrate_async(
                        question=message,
                        db_rows=truncated_data if isinstance(truncated_data, list) else [truncated_data],
                        intent=intent,
                        language=language,
                        max_tokens=600,
                    )
                except Exception as e:
                    logger.warning(f"LLM narration failed: {e}, using fallback")
                    summary = _create_summary_from_analysis(intent, truncated_data)
                    answer = f"Here's the {intent.lower().replace('_', ' ')}:\n\n{summary}"
                
                return AIResponse(
                    intent=intent,
                    entities=entities,
                    result=answer,
                    data=truncated_data if isinstance(truncated_data, list) else [truncated_data],
                    suggestions=_suggest(intent, entities, language),
                    session_id=session_id,
                )

        except Exception as e:
            logger.error(f"Error in decision support: {e}", exc_info=True)
            answer = await llm.generate_async(
                f"User asked about {intent.lower().replace('_', ' ')}. "
                f"There was an error processing your request.",
                intent=intent,
                language=language,
                max_tokens=200,
            )
            return AIResponse(
                intent=intent,
                entities=entities,
                result=answer,
                data=[],
                suggestions=_suggest(intent, entities, language),
                session_id=session_id,
            )
        
        answer = await llm.generate_async(
            f"No data available for {intent.lower().replace('_', ' ')}. "
            f"Inform the user briefly and suggest alternatives.",
            intent=intent,
            language=language,
            max_tokens=200,
        )
        return AIResponse(
            intent=intent,
            entities=entities,
            result=answer,
            data=[],
            suggestions=_suggest(intent, entities, language),
            session_id=session_id,
        )

    # ── Tier 4: DB → narrate ────────────────────────────────────────────────
    if intent not in ACTION_ROUTER_INTENTS:
        logger.info(f"🗄️ Tier 4 — DB query + narrate: {intent}")

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
                suggestions=_suggest(intent, entities, language),
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
                suggestions=_suggest(intent, entities, language),
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
            suggestions=_suggest(intent, entities, language),
            session_id=session_id,
        )

    # ── Tier 5: action_router ───────────────────────────────────────────────
    logger.info(f"⚙️ Tier 5 — Action router: {intent}")

    api_result = action_router.route(intent, entities, message, language=language)
    logger.info(f"API Result type: {type(api_result)}")

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
            suggestions=_suggest(intent, entities, language),
            session_id=session_id,
        )

    if isinstance(api_result, dict) and "message" in api_result and "ResponseData" not in api_result:
        return AIResponse(
            intent=intent,
            entities=entities,
            result=api_result["message"],
            data=api_result.get("data", []),
            suggestions=_suggest(intent, entities, language),
            session_id=session_id,
        )

    formatted = _legacy_format(intent, api_result, formatter)
    return AIResponse(
        intent=intent,
        entities=entities,
        result=formatted.get("message", "I couldn't process your request."),
        data=formatted.get("data", []),
        suggestions=_suggest(intent, entities, language),
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# Dashboard and Cache Endpoints
# ---------------------------------------------------------------------------

@router.get("/dashboard")
def get_dashboard() -> dict[str, Any]:
    """Proactive dashboard data for Flutter app startup."""
    svc = get_dashboard_service()
    return svc.get_dashboard()


@router.get("/cache/stats")
def cache_stats():
    """Get cache statistics."""
    return get_cache_service().get_stats()


@router.post("/cache/clear")
def cache_clear(intent: Optional[str] = None, session_id: Optional[str] = None):
    """Clear cache for specific intent or all."""
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