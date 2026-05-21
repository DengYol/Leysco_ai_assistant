"""Utility functions for AI routes"""

from fastapi.responses import JSONResponse
import json
import re
import logging
from typing import Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


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


def ensure_utf8_string(text: str) -> str:
    """Ensure string is properly encoded as UTF-8."""
    if not text:
        return text
    try:
        return text.encode('utf-8', errors='ignore').decode('utf-8')
    except Exception:
        return str(text)


def extract_delivery_number(message: str, entities: dict) -> Optional[str]:
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


def extract_customer_for_delivery(message: str, entities: dict) -> Optional[str]:
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


def truncate_large_data(data: Any, max_items: int = 10) -> Any:
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


def create_summary_from_analysis(intent: str, analysis: dict) -> str:
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