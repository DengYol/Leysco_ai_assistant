"""Base formatter class with shared utilities"""

import random
from typing import Dict, Any
from .constants import OPENERS, CLOSERS, NO_RESULTS, TIPS
from .utils import format_price, format_date, extract_list


class BaseFormatter:
    """Base class for all formatters with shared helper methods"""
    
    MAX_RESULTS = 5
    MAX_CUSTOMERS_DISPLAY = 10
    
    @classmethod
    def _get_opener(cls, intent: str, language: str = "en") -> str:
        """Get random opener for the intent."""
        openers = OPENERS.get(intent, {}).get(language, [])
        if openers:
            return random.choice(openers)
        return ""
    
    @classmethod
    def _get_closer(cls, language: str = "en") -> str:
        """Get random closing message."""
        return random.choice(CLOSERS.get(language, CLOSERS["en"]))
    
    @classmethod
    def _get_no_results_message(cls, intent: str, language: str = "en") -> str:
        """Get no-results message for intent."""
        return NO_RESULTS.get(intent, {}).get(
            language,
            "I couldn't find what you're looking for. Try rephrasing your question! 🤔"
        )
    
    @classmethod
    def _get_tip(cls, intent: str, language: str = "en") -> str:
        """Get tip for the intent."""
        return TIPS.get(intent, {}).get(language, "")
    
    @classmethod
    def _not_available(cls, msg="That information is not available in Leysco right now."):
        """Return not available response."""
        return {"message": msg, "data": []}
    
    @classmethod
    def _format_price(cls, value):
        return format_price(value)
    
    @classmethod
    def _format_date(cls, date_str):
        return format_date(date_str)
    
    @classmethod
    def _extract_list(cls, data):
        return extract_list(data)