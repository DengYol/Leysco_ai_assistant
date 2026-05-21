"""Utility functions for LLM Service"""

import re
from typing import Any, List, Dict


def clean_response(text: str, strip_markdown: bool = False) -> str:
    """
    Clean response for display.
    
    Args:
        text: The response text to clean
        strip_markdown: If True, remove markdown formatting (default False to preserve formatting)
    """
    if not text:
        return text
    
    # Remove code blocks but keep their content
    text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
    
    # Convert markdown links [text](url) -> text (keep the text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Only strip markdown if explicitly requested
    if strip_markdown:
        # Remove **bold** -> bold
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        # Remove *italic* -> italic
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        # Remove __bold__ -> bold
        text = re.sub(r'__([^_]+)__', r'\1', text)
    
    # Clean up excessive whitespace (but keep line breaks for readability)
    text = re.sub(r' +', ' ', text)  # Multiple spaces to single
    text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 line breaks
    
    # Fix spacing after periods
    text = re.sub(r'\.([A-Z])', r'. \1', text)
    
    # Ensure bullet points have proper spacing
    text = re.sub(r'\n•', '\n•', text)
    text = re.sub(r'^•', '•', text, flags=re.MULTILINE)
    
    return text.strip()


def count_items(data: Any) -> int:
    """Count items in data."""
    if not data:
        return 0
    if isinstance(data, list):
        return len(data)
    return 1


def get_response_styles() -> Dict[str, List[str]]:
    """Get available response styles per intent."""
    return {
        "GET_ITEM_PRICE": ["direct", "friendly", "enthusiastic"],
        "GET_STOCK_LEVELS": ["detailed", "clear", "informative"],
        "GET_TOP_SELLING_ITEMS": ["excited", "informative", "encouraging"],
        "GET_SLOW_MOVING_ITEMS": ["helpful", "constructive", "strategic"],
        "GET_CUSTOMER_ORDERS": ["detailed", "summary", "insightful"],
        "CREATE_QUOTATION": ["celebratory", "professional", "helpful"],
    }