"""Main ResponseFormatter class - orchestrates all formatters"""

from typing import Any, Dict, Optional  # Add this import
import logging

from .forms import (
    QuotationFormatter,
    PriceFormatter,
    AnalyticsFormatter,
    DeliveryFormatter,
    CustomerFormatter,
    ListFormatter,
    CrossSellFormatter
)
from .base import BaseFormatter
from .utils import format_price, format_date, extract_list
from .constants import OPENERS, CLOSERS, NO_RESULTS, TIPS
from .conversational import conversational_enhancer

logger = logging.getLogger(__name__)


class ResponseFormatter(
    QuotationFormatter,
    PriceFormatter,
    AnalyticsFormatter,
    DeliveryFormatter,
    CustomerFormatter,
    ListFormatter,
    CrossSellFormatter,
    BaseFormatter
):
    """Main ResponseFormatter class that combines all formatters"""
    
    # Re-export constants for backward compatibility
    OPENERS = OPENERS
    CLOSERS = CLOSERS
    NO_RESULTS = NO_RESULTS
    TIPS = TIPS
    MAX_RESULTS = BaseFormatter.MAX_RESULTS
    MAX_CUSTOMERS_DISPLAY = BaseFormatter.MAX_CUSTOMERS_DISPLAY
    
    @classmethod
    def format_response(cls, message: str, intent: str, data: Any = None, language: str = "en") -> Dict[str, Any]:
        """Main entry point for formatting responses with conversational enhancements"""
        
        # Get the base formatted response
        result = None
        if intent == "GET_ITEM_PRICE":
            if data and isinstance(data, dict):
                result = cls.format_item_price(data, language)
            elif data and isinstance(data, list):
                # Handle list of price items
                result = cls.format_item_price({"item": data[0] if data else {}, "prices": data}, language)
        elif intent == "GET_TOP_SELLING_ITEMS":
            items = data if isinstance(data, list) else (data.get("items", []) if data else [])
            result = cls.format_top_selling_items(items, language=language)
        elif intent == "GET_SLOW_MOVING_ITEMS":
            items = data if isinstance(data, list) else (data.get("items", []) if data else [])
            result = cls.format_slow_moving_items(items, language=language)
        elif intent == "CREATE_QUOTATION":
            if data and isinstance(data, dict):
                result = cls.format_quotation_creation_success(
                    customer_name=data.get("customer_name", ""),
                    items=data.get("items", []),
                    total_amount=data.get("total_amount", 0),
                    valid_until=data.get("valid_until", ""),
                    doc_num=data.get("quotation_id"),
                    language=language
                )
        else:
            result = {"message": message, "data": data or []}
        
        if not result:
            result = {"message": cls._not_available()["message"], "data": []}
        
        # Apply conversational enhancements
        has_error = result.get("message", "").startswith(("Sorry", "Hmm", "I couldn't"))
        enhanced_message = conversational_enhancer.enhance(
            response=result["message"],
            intent=intent,
            language=language,
            has_error=has_error,
            data=result.get("data")
        )
        
        result["message"] = enhanced_message
        return result


# Create singleton instance for backward compatibility
response_formatter = ResponseFormatter()