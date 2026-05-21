"""Utility functions for Response Formatter"""

from typing import Optional
from datetime import datetime


def format_price(value) -> str:
    """Format price value with commas and 2 decimal places."""
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return value or "0.00"


def format_date(date_str: Optional[str]) -> str:
    """Format date string to readable format."""
    if not date_str:
        return "N/A"
    try:
        if isinstance(date_str, str):
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            return dt.strftime("%b %d, %Y")
        return str(date_str)
    except Exception:
        return str(date_str)[:10]


def extract_list(data):
    """Extract list from various data structures."""
    if isinstance(data, dict):
        if "error" in data:
            return "error", data["error"]
        response = data.get("ResponseData")
        if isinstance(response, list):
            return "list", response
        if isinstance(response, dict) and "data" in response:
            return "list", response["data"]
        return "list", []
    if isinstance(data, list):
        return "list", data
    return "error", "Invalid data format"