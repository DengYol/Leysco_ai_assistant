"""Utility functions for DB Query Service"""

import re
from typing import Optional, List, Dict
from datetime import datetime, timedelta


def date_range(days_back: int = 30) -> tuple[str, str]:
    """Returns (start_date, end_date) strings for CRM API calls."""
    end = datetime.now()
    start = end - timedelta(days=days_back)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def normalize_size_for_comparison(size_str: str) -> str:
    """Normalize size string for comparison. E.g., '10 ml' -> '10ml'"""
    if not size_str:
        return ""
    normalized = re.sub(r'\s+', '', size_str.lower())
    return normalized


def extract_size_from_item_name(item_name: str) -> Optional[str]:
    """Extract size from item name like 'VEGIMAX-250ML' -> '250ml'"""
    if not item_name:
        return None
    
    patterns = [
        r'(\d+(?:\.\d+)?)\s*(ml|ML|mL|kg|KG|g|G|l|L)',
        r'(?:-|\s)(\d+)(?:ml|ML|mL|kg|KG|g|G|l|L)',
        r'(\d+)(?:ml|ML|mL|kg|KG|g|G|l|L)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, item_name)
        if match:
            if len(match.groups()) == 2:
                num, unit = match.groups()
                return normalize_size_for_comparison(f"{num}{unit}")
            elif match.group(1):
                return normalize_size_for_comparison(match.group(1))
    return None


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert to float, handling None and errors."""
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def is_already_transformed(data: list) -> bool:
    """Check if data is already in transformed format."""
    if not data or not isinstance(data, list) or len(data) == 0:
        return False
    
    first_item = data[0]
    if not isinstance(first_item, dict):
        return False
    
    transformed_indicators = ['code', 'name', 'id']
    has_transformed = any(field in first_item for field in transformed_indicators)
    has_raw_sap = any(field in first_item for field in ['WhsCode', 'WhsCode', 'ItemCode', 'CardCode'])
    has_summary = any('_summary' in item for item in data)
    
    return (has_transformed and not has_raw_sap) or has_summary