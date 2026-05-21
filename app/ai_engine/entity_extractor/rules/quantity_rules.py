"""Quantity and limit extraction rules"""

import re
import logging
from ..constants import NUMBER_WORDS, SWAHILI_NUMBER_WORDS, LISTING_INDICATORS

logger = logging.getLogger(__name__)


class QuantityRules:
    """Rules for quantity and limit extraction"""
    
    @staticmethod
    def extract_quantity(text: str, is_seasonal: bool = False) -> int:
        """Extract quantity number from text."""
        text_lower = text.lower()
        quantity = None
        
        if not is_seasonal:
            digit_match = re.search(r"\b(\d+)\b", text_lower)
            if digit_match:
                quantity = int(digit_match.group(1))
            else:
                for word, num in NUMBER_WORDS.items():
                    if re.search(rf"\b{word}\b", text_lower):
                        quantity = num
                        break
                if not quantity:
                    for sw_word, num in SWAHILI_NUMBER_WORDS.items():
                        if re.search(rf"\b{sw_word}\b", text_lower):
                            quantity = num
                            break
        
        return quantity
    
    @staticmethod
    def extract_listing_limit(text: str, is_listing: bool = False) -> int:
        """Extract limit from listing queries (e.g., '5 customers')."""
        if not is_listing:
            return None
            
        text_lower = text.lower()
        
        match = re.search(r'\b(\d+)\s+(?:customers|clients|wateja)\b', text_lower)
        if match:
            return int(match.group(1))
        
        for word, num in NUMBER_WORDS.items():
            if re.search(rf'\b{word}\s+(?:customers|clients|wateja)\b', text_lower):
                return num
        
        for sw_word, num in SWAHILI_NUMBER_WORDS.items():
            if re.search(rf'\b{sw_word}\s+(?:wateja)\b', text_lower):
                return num
        
        return None
    
    @staticmethod
    def clean_text_for_entities(text: str) -> str:
        """Remove numbers and command verbs from text for cleaner entity extraction."""
        text_lower = text.lower()
        
        # Remove digits
        cleaned_text = re.sub(r"\b\d+\b", "", text_lower)
        
        # Remove number words
        for word in NUMBER_WORDS.keys():
            cleaned_text = re.sub(rf"\b{word}\b", "", cleaned_text)
        for sw_word in SWAHILI_NUMBER_WORDS.keys():
            cleaned_text = re.sub(rf"\b{sw_word}\b", "", cleaned_text)
        
        # Remove command verbs
        COMMAND_VERBS = r"\b(show|list|get|find|search|display|tell|give|look|create|make|generate|onyesha|taja|tafuta|pata|unda|tengeneza)\b"
        cleaned_text = re.sub(COMMAND_VERBS, "", cleaned_text)
        cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
        
        return cleaned_text