"""Query type detection rules"""

import re
from ..constants import (
    INFO_QUERY_INDICATORS,
    FORECAST_INDICATORS,
    COMPETITOR_PRICING_INDICATORS,
    RECOMMENDATION_INDICATORS,
    SEASONAL_INDICATORS,
    LISTING_INDICATORS
)


class IntentRules:
    """Rules for detecting query intent types"""
    
    @staticmethod
    def is_info_query(text: str) -> bool:
        text_lower = text.lower()
        for indicator in INFO_QUERY_INDICATORS:
            if indicator in text_lower:
                return True
        if "about" in text_lower or "kuhusu" in text_lower:
            words = text_lower.split()
            for i, word in enumerate(words):
                if word in ["about", "kuhusu"] and i + 1 < len(words):
                    return True
        return False
    
    @staticmethod
    def is_forecast_query(text: str) -> bool:
        text_lower = text.lower()
        if IntentRules.is_seasonal_query(text_lower):
            return False
        for indicator in FORECAST_INDICATORS:
            if indicator in text_lower:
                return True
        forecast_patterns = [
            r'how many\s+([a-zA-Z0-9]+)\s+will\s+(?:we\s+)?sell',
            r'how much\s+([a-zA-Z0-9]+)\s+will\s+(?:we\s+)?sell',
            r'demand\s+(?:for|of)\s+([a-zA-Z0-9]+)',
            r'forecast\s+(?:for|of)\s+([a-zA-Z0-9]+)',
        ]
        for pattern in forecast_patterns:
            if re.search(pattern, text_lower):
                return True
        return False
    
    @staticmethod
    def is_seasonal_query(text: str) -> bool:
        text_lower = text.lower()
        for indicator in SEASONAL_INDICATORS:
            if indicator in text_lower:
                return True
        return False
    
    @staticmethod
    def is_recommendation_query(text: str) -> bool:
        text_lower = text.lower()
        for indicator in RECOMMENDATION_INDICATORS:
            if indicator in text_lower:
                return True
        return False
    
    @staticmethod
    def is_competitor_pricing_query(text: str) -> bool:
        text_lower = text.lower()
        for indicator in COMPETITOR_PRICING_INDICATORS:
            if indicator in text_lower:
                return True
        return False
    
    @staticmethod
    def is_listing_query(text: str) -> bool:
        text_lower = text.lower()
        for indicator in LISTING_INDICATORS:
            if indicator in text_lower:
                return True
        return False
    
    @staticmethod
    def is_best_price_query(text: str) -> bool:
        text_lower = text.lower()
        phrases = ["best price", "cheapest", "lowest price", "who sells", "where to buy", "best deal", "who has the best"]
        return any(phrase in text_lower for phrase in phrases)
    
    @staticmethod
    def is_compare_query(text: str) -> bool:
        text_lower = text.lower()
        phrases = ["compare", "comparison", "vs", "versus", "verses"]
        return any(phrase in text_lower for phrase in phrases)
    
    @staticmethod
    def is_price_alert_query(text: str) -> bool:
        text_lower = text.lower()
        phrases = ["price alert", "notify when", "alert me when", "track price"]
        return any(phrase in text_lower for phrase in phrases)