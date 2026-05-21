"""Date and month extraction rules"""

import re
import logging
from ..constants import MONTHS, SWAHILI_MONTHS

logger = logging.getLogger(__name__)


class DateRules:
    """Rules for date and month extraction"""
    
    @staticmethod
    def extract_month(text: str) -> str:
        """Extract month from text."""
        text_lower = text.lower()
        
        for month in MONTHS:
            if month in text_lower:
                logger.info(f"Detected month: {month}")
                return month
        
        for sw_month, en_month in SWAHILI_MONTHS.items():
            if sw_month in text_lower:
                logger.info(f"Detected Swahili month: {sw_month} -> {en_month}")
                return en_month
        
        return None
    
    @staticmethod
    def extract_date(text: str) -> str:
        """Extract date from text."""
        text_lower = text.lower()
        
        date_match = re.search(
            r"\b(today|tomorrow|yesterday|\d{4}-\d{2}-\d{2}|leo|kesho|jana)\b",
            text_lower,
        )
        
        if date_match:
            date_value = date_match.group(1)
            # Translate Swahili dates
            if date_value == "leo":
                return "today"
            elif date_value == "kesho":
                return "tomorrow"
            elif date_value == "jana":
                return "yesterday"
            return date_value
        
        return None