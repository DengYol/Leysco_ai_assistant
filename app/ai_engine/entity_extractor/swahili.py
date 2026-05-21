"""Swahili language support for entity extraction"""

import re
from .constants import SWAHILI_PREFIXES, SWAHILI_MONTHS, SWAHILI_NUMBER_WORDS


def is_swahili_query(text: str) -> bool:
    """Quick check if query appears to be Swahili."""
    text_lower = text.lower()
    swahili_indicators = [
        "nionyeshe", "onyesha", "angalia", "tafuta", "pata", "sema",
        "hisa", "viwango", "idadi", "zilizopo", "ghala", "maghala",
        "mteja", "wateja", "bidhaa", "mazao", "nukuu", "bei", "pesa",
        "leo", "jana", "kesho", "sasa", "mambo", "habari",
    ]
    for indicator in swahili_indicators:
        if indicator in text_lower:
            return True
    return False


def normalize_swahili_text(text: str) -> str:
    """Remove Swahili prefixes and convert to English-like query."""
    text_lower = text.lower()
    normalized = text_lower
    
    for prefix in SWAHILI_PREFIXES:
        normalized = re.sub(prefix, '', normalized, flags=re.IGNORECASE)
    
    # Translate common Swahili query patterns to English equivalents
    translations = [
        (r'viwango\s+vya\s+hisa', 'stock levels of'),
        (r'angalia\s+hisa', 'check stock'),
        (r'hisa\s+(?:ya|za)\s+', 'stock of '),
        (r'idadi\s+ya\s+', 'quantity of '),
        (r'bei\s+(?:ya|za)\s+', 'price of '),
        (r'gharama\s+ya\s+', 'cost of '),
        (r'onyesha\s+', 'show '),
        (r'taja\s+', 'list '),
        (r'orodhesha\s+', 'list '),
        (r'tafuta\s+', 'search for '),
        (r'pata\s+', 'get '),
        (r'tengeneza\s+nukuu', 'create quotation'),
        (r'unda\s+nukuu', 'create quotation'),
        (r'nukuu\s+kwa', 'quotation for'),
    ]
    
    for swahili, english in translations:
        normalized = re.sub(swahili, english, normalized, flags=re.IGNORECASE)
    
    # Translate months
    for sw_month, en_month in SWAHILI_MONTHS.items():
        normalized = normalized.replace(sw_month, en_month)
    
    # Translate numbers
    for sw_num, num in SWAHILI_NUMBER_WORDS.items():
        normalized = re.sub(rf'\b{sw_num}\b', str(num), normalized)
    
    return normalized.strip()


def translate_date(date_value: str) -> str:
    """Translate Swahili date values to English."""
    if date_value == "leo":
        return "today"
    elif date_value == "kesho":
        return "tomorrow"
    elif date_value == "jana":
        return "yesterday"
    return date_value