"""Utility functions for Leysco API Service"""

import re
import logging
from typing import List, Dict, Any, Optional
from .constants import STRIP_FROM_SEARCH

logger = logging.getLogger(__name__)


def clean_customer_search_term(name: str) -> str:
    """
    Strip generic business suffix words before API search.
    e.g. 'magomano suppliers' → 'magomano'
    """
    if not name:
        return name
    tokens = name.lower().split()
    cleaned = [t for t in tokens if t not in STRIP_FROM_SEARCH]
    result = " ".join(cleaned).strip()
    if result and result != name.lower():
        logger.info(f"Search term cleaned: '{name}' → '{result}'")
    return result or name


def is_html_response(text: str) -> bool:
    """Check if response is HTML (login page) instead of JSON."""
    if not text:
        return False
    text_lower = text.lower().strip()
    html_indicators = [
        '<html', '<!doctype html', '<!DOCTYPE HTML',
        'welcome back', 'sign in', 'login', 'signin',
        'username', 'password', 'enter your credentials'
    ]
    return any(indicator in text_lower for indicator in html_indicators)


def normalize_response(data: Any) -> List[Dict]:
    """Normalize API response to a standard list format."""
    if not isinstance(data, dict):
        return data if isinstance(data, list) else []

    response_data = data.get("ResponseData") or data.get("responseData")

    if isinstance(response_data, dict) and "stocks" in response_data:
        stocks = response_data["stocks"]
        if isinstance(stocks, dict) and "data" in stocks:
            return stocks["data"]
    
    if isinstance(response_data, dict):
        records = response_data.get("data")
        if isinstance(records, list):
            return records

    if isinstance(response_data, list):
        return response_data

    if isinstance(data.get("data"), list):
        return data["data"]
    
    if isinstance(data.get("items"), list):
        return data["items"]
    
    if isinstance(data.get("ResponseData"), list):
        return data["ResponseData"]

    return []


def normalize_warehouse_response(data: dict) -> List[Dict]:
    """Normalize warehouse response from the /warehouse endpoint."""
    try:
        if data.get("ResultState") and data.get("ResponseData"):
            response_data = data["ResponseData"]
            if isinstance(response_data, dict):
                if "data" in response_data:
                    return response_data["data"]
                elif "warehouses" in response_data:
                    return response_data["warehouses"]
            elif isinstance(response_data, list):
                return response_data
        
        if isinstance(data.get("data"), list):
            return data["data"]
        
        if isinstance(data, list):
            return data
        
        logger.warning(f"Unknown warehouse response format: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        return []
        
    except Exception as e:
        logger.error(f"Error normalizing warehouse response: {e}")
        return []


def apply_limit(records: List[Dict], limit: Optional[int]) -> List[Dict]:
    """Apply limit to records list."""
    return records[:limit] if limit and isinstance(limit, int) and limit > 0 else records


def match_by_name(records: List[Dict], search: str, keys: List[str]) -> Optional[Dict]:
    """Find record by name in list."""
    search = search.lower()
    for r in records:
        for k in keys:
            if search in str(r.get(k, "")).lower():
                return r
    return None


def format_price(value) -> str:
    """Format price for display."""
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return str(value) if value else "0.00"


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert to float, handling None values."""
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert to int, handling None values."""
    try:
        if value is None:
            return default
        return int(float(value))
    except (ValueError, TypeError):
        return default