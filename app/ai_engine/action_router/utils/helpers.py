"""Helper utilities for Action Router"""

import difflib
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

logger = logging.getLogger(__name__)


def resolve_customer(
    customer_name: str, 
    item_name: str = "", 
    api=None, 
    cache: dict = None, 
    ttl: int = 300
) -> Tuple[Optional[Dict], str]:
    """Resolve customer with caching."""
    name = customer_name or item_name
    if not name:
        return None, None
    
    name = name.strip()
    
    # Check cache
    if cache is not None:
        cache_key = f"customer_resolve:{name.lower()}"
        if cache_key in cache:
            cached_time, cached_customer = cache[cache_key]
            if (datetime.now() - cached_time).seconds < ttl:
                logger.info(f"Customer cache hit: {name}")
                return cached_customer, name
    
    if not api:
        return None, name
    
    customer = api.resolve_customer(name)
    if customer:
        if cache is not None:
            cache[cache_key] = (datetime.now(), customer)
        return customer, name
    
    results = api.get_customers(search=name)
    if not results:
        return None, name
    
    name_lower = name.lower()
    for c in results:
        if (c.get("CardName") or "").lower() == name_lower:
            if cache is not None:
                cache[cache_key] = (datetime.now(), c)
            return c, name
    
    card_names = [c.get("CardName") for c in results if c.get("CardName")]
    matches = difflib.get_close_matches(name, card_names, n=1, cutoff=0.6)
    if matches:
        customer = next((c for c in results if c.get("CardName") == matches[0]), None)
        if customer:
            logger.info(f"Fuzzy matched customer: '{name}' -> '{matches[0]}'")
            if cache is not None:
                cache[cache_key] = (datetime.now(), customer)
            return customer, name
    
    return None, name


def extract_quantity_and_item(text: str) -> List[Tuple[int, str]]:
    """Extract quantity and item name from text."""
    matches = []
    
    # Pattern: quantity followed by item
    pattern1 = re.findall(r'(\d+)\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\s+and|\s+na|\s*,\s*|$)', text.lower())
    for qty, item in pattern1:
        matches.append((int(qty), item.strip()))
    
    # Pattern: item followed by quantity
    pattern2 = re.findall(r'([a-zA-Z0-9\-\(\)\s]+?)\s+(\d+)(?:\s+and|\s+na|\s*,\s*|$)', text.lower())
    for item, qty in pattern2:
        matches.append((int(qty), item.strip()))
    
    # If no quantity found, assume quantity 1
    if not matches:
        words = text.split()
        for word in words:
            if word not in ['and', 'with', 'for', 'na', 'kwa']:
                matches.append((1, word))
                break
    
    return matches


def clean_item_search_term(term: str) -> str:
    """Clean item search term by removing common words."""
    stop_words = ['and', 'with', 'for', 'units', 'pieces', 'vitengo', 'za', 'ya', 'kwa']
    term = term.lower()
    for word in stop_words:
        term = term.replace(f' {word} ', ' ')
        term = term.replace(f' {word}$', '')
        term = term.replace(f'^{word} ', '')
    return term.strip()