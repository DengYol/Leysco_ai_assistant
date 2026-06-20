"""
app/ai_engine/suggestions_engine.py
=====================================
Context-Aware Quick Reply Chip Generator

Generates 2-4 follow-up suggestion chips after every AI response.
Chips are chosen based on:
  - The intent that was just handled
  - Entities that were resolved (item_name, customer_name, warehouse)
  - Detected language  ('en' | 'sw' | 'mixed')

The Flutter frontend renders these as tappable chips below each AI
message bubble via the AIMessage.suggestions field.

Optimizations:
- Caching for generated suggestions
- Async support
- Enhanced suggestions for customer segmentation
- Better entity handling
"""

from __future__ import annotations
import logging
import asyncio
import hashlib
from typing import List, Dict, Any, Optional
from functools import lru_cache, wraps

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Suggestion templates: intent -> list of (en, sw, mixed) tuples
# ---------------------------------------------------------------------------

_SUGGESTIONS: dict[str, list[tuple[str, str, str]]] = {

    # Pricing
    "GET_ITEM_PRICE": [
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
        ("Customer price for {item}", "Bei ya mteja kwa {item}", "Customer price ya {item}"),
        ("Add {item} to a quote", "Ongeza {item} kwenye nukuu", "Add {item} to quote"),
        ("See similar products", "Ona bidhaa zinazofanana", "Ona similar products"),
    ],
    "GET_CUSTOMER_PRICE": [
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
        ("Create quote for {customer}", "Tengeneza nukuu kwa {customer}", "Create quote ya {customer}"),
        ("View orders for {customer}", "Ona maagizo ya {customer}", "View orders za {customer}"),
        ("Check {customer} deliveries", "Angalia usafirishaji wa {customer}", "Check deliveries za {customer}"),
    ],
    "GET_ITEM_BASE_PRICE": [
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
        ("Add {item} to a quote", "Ongeza {item} kwenye nukuu", "Add {item} to quote"),
        ("See customer price for {item}", "Ona bei ya mteja kwa {item}", "Customer price ya {item}"),
        ("Recommend similar items", "Pendekeza bidhaa zinazofanana", "Recommend similar items"),
    ],

    # Customer Segmentation (NEW)
    "FIND_CUSTOMERS_BY_ITEM": [
        ("Show customer details", "Onyesha maelezo ya mteja", "Show customer details"),
        ("Create quotation for these customers", "Unda nukuu kwa wateja hawa", "Create quotation for these customers"),
        ("Show orders for these customers", "Onyesha maagizo ya wateja hawa", "Show orders for these customers"),
        ("Find similar customers", "Tafuta wateja wanaofanana", "Find similar customers"),
        ("Show purchase history", "Onyesha historia ya ununuzi", "Show purchase history"),
        ("Check price of {item}", "Angalia bei ya {item}", "Check price ya {item}"),
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
    ],

    # Stock
    "GET_WAREHOUSE_STOCK": [
        ("Show low stock alerts", "Onyesha tahadhari za hisa chini", "Show low stock alerts"),
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
        ("List all warehouses", "Orodhesha maghala yote", "List warehouses zote"),
        ("Generate reorder list", "Tengeneza orodha ya kuagiza", "Generate reorder list"),
    ],
    "GET_LOW_STOCK_ALERTS": [
        ("Generate reorder list", "Tengeneza orodha ya kuagiza", "Generate reorder list"),
        ("View warehouse stock", "Ona hisa ya ghala", "View warehouse stock"),
        ("Show all warehouses", "Onyesha maghala yote", "Show warehouses zote"),
        ("Analyse inventory health", "Changanua afya ya hisa", "Analyse inventory health"),
    ],
    "GET_STOCK_LEVELS": [
        ("Show low stock alerts", "Onyesha tahadhari za hisa chini", "Show low stock alerts"),
        ("Check price of {item}", "Angalia bei ya {item}", "Check price ya {item}"),
        ("Add {item} to a quote", "Ongeza {item} kwenye nukuu", "Add {item} to quote"),
        ("View warehouse breakdown", "Ona mgawanyiko wa ghala", "View warehouse breakdown"),
    ],

    # Customers
    "GET_CUSTOMER_DETAILS": [
        ("View orders for {customer}", "Ona maagizo ya {customer}", "View orders za {customer}"),
        ("Check {customer} deliveries", "Angalia usafirishaji wa {customer}", "Check deliveries za {customer}"),
        ("Create quote for {customer}", "Tengeneza nukuu kwa {customer}", "Create quote ya {customer}"),
        ("Analyse {customer} behaviour", "Changanua tabia ya {customer}", "Analyse behaviour ya {customer}"),
    ],
    "GET_CUSTOMER_ORDERS": [
        ("Track delivery for {customer}", "Fuatilia usafirishaji wa {customer}", "Track delivery ya {customer}"),
        ("Create quote for {customer}", "Tengeneza nukuu kwa {customer}", "Create quote ya {customer}"),
        ("View {customer} invoices", "Ona ankara za {customer}", "View invoices za {customer}"),
        ("Analyse {customer} behaviour", "Changanua tabia ya {customer}", "Analyse behaviour ya {customer}"),
    ],
    "GET_CUSTOMER_INVOICES": [
        ("View orders for {customer}", "Ona maagizo ya {customer}", "View orders za {customer}"),
        ("Track delivery for {customer}", "Fuatilia usafirishaji wa {customer}", "Track delivery ya {customer}"),
        ("Create quote for {customer}", "Tengeneza nukuu kwa {customer}", "Create quote ya {customer}"),
    ],
    "ANALYZE_CUSTOMER_BEHAVIOR": [
        ("Create quote for {customer}", "Tengeneza nukuu kwa {customer}", "Create quote ya {customer}"),
        ("View orders for {customer}", "Ona maagizo ya {customer}", "View orders za {customer}"),
        ("Recommend items for {customer}", "Pendekeza bidhaa kwa {customer}", "Recommend items kwa {customer}"),
        ("Track delivery for {customer}", "Fuatilia usafirishaji wa {customer}", "Track delivery ya {customer}"),
    ],

    # Quotations
    "CREATE_QUOTATION": [
        ("Add more items to quote", "Ongeza bidhaa zaidi kwenye nukuu", "Add more items to quote"),
        ("View all quotations", "Ona nukuu zote", "View quotations zote"),
        ("Create another quote", "Tengeneza nukuu nyingine", "Create another quote"),
        ("Recommend items for {customer}", "Pendekeza bidhaa kwa {customer}", "Recommend items kwa {customer}"),
    ],
    "GET_QUOTATIONS": [
        ("Create new quotation", "Tengeneza nukuu mpya", "Create new quotation"),
        ("Track delivery for {customer}", "Fuatilia usafirishaji wa {customer}", "Track delivery ya {customer}"),
        ("View orders for {customer}", "Ona maagizo ya {customer}", "View orders za {customer}"),
    ],

    # Deliveries
    "TRACK_DELIVERY": [
        ("View all outstanding deliveries", "Ona usafirishaji wote unaongoja", "View outstanding deliveries zote"),
        ("View orders for {customer}", "Ona maagizo ya {customer}", "View orders za {customer}"),
        ("Create quote for {customer}", "Tengeneza nukuu kwa {customer}", "Create quote ya {customer}"),
    ],
    "GET_OUTSTANDING_DELIVERIES": [
        ("Track specific delivery", "Fuatilia usafirishaji maalum", "Track specific delivery"),
        ("View delivery history", "Ona historia ya usafirishaji", "View delivery history"),
        ("View orders for {customer}", "Ona maagizo ya {customer}", "View orders za {customer}"),
    ],
    "GET_DELIVERY_HISTORY": [
        ("View outstanding deliveries", "Ona usafirishaji unaongoja", "View outstanding deliveries"),
        ("Create quote for {customer}", "Tengeneza nukuu kwa {customer}", "Create quote ya {customer}"),
        ("View orders for {customer}", "Ona maagizo ya {customer}", "View orders za {customer}"),
    ],

    # Warehouses
    "GET_WAREHOUSES": [
        ("Check stock in {warehouse}", "Angalia hisa katika {warehouse}", "Check stock katika {warehouse}"),
        ("Show low stock alerts", "Onyesha tahadhari za hisa chini", "Show low stock alerts"),
        ("Analyse inventory health", "Changanua afya ya hisa", "Analyse inventory health"),
    ],
    "GET_ITEMS_ADVANCED": [
        ("Check price of {item}", "Angalia bei ya {item}", "Check price ya {item}"),
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
        ("Add {item} to a quote", "Ongeza {item} kwenye nukuu", "Add {item} to quote"),
        ("Recommend similar items", "Pendekeza bidhaa zinazofanana", "Recommend similar items"),
    ],

    # Recommendations
    "GET_CROSS_SELL": [
        ("Add {item} to a quote", "Ongeza {item} kwenye nukuu", "Add {item} to quote"),
        ("Check price of {item}", "Angalia bei ya {item}", "Check price ya {item}"),
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
        ("Get seasonal recommendations", "Pata mapendekezo ya msimu", "Get seasonal recommendations"),
    ],
    "GET_UPSELL": [
        ("Check price of {item}", "Angalia bei ya {item}", "Check price ya {item}"),
        ("Add {item} to a quote", "Ongeza {item} kwenye nukuu", "Add {item} to quote"),
        ("Get cross-sell suggestions", "Pata mapendekezo ya msalaba", "Get cross-sell suggestions"),
    ],
    "GET_SEASONAL_RECOMMENDATIONS": [
        ("Check price of {item}", "Angalia bei ya {item}", "Check price ya {item}"),
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
        ("Add {item} to a quote", "Ongeza {item} kwenye nukuu", "Add {item} to quote"),
        ("Get trending products", "Pata bidhaa zinazoendelea", "Get trending products"),
    ],
    "GET_TRENDING_PRODUCTS": [
        ("Get seasonal recommendations", "Pata mapendekezo ya msimu", "Get seasonal recommendations"),
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
        ("Add {item} to a quote", "Ongeza {item} kwenye nukuu", "Add {item} to quote"),
    ],
    "RECOMMEND_ITEMS": [
        ("Check price of {item}", "Angalia bei ya {item}", "Check price ya {item}"),
        ("Add {item} to a quote", "Ongeza {item} kwenye nukuu", "Add {item} to quote"),
        ("Get seasonal recommendations", "Pata mapendekezo ya msimu", "Get seasonal recommendations"),
        ("Show trending products", "Onyesha bidhaa zinazoendelea", "Show trending products"),
    ],
    "RECOMMEND_CUSTOMERS": [
        ("View customer details", "Ona maelezo ya mteja", "View customer details"),
        ("Create quote for {customer}", "Tengeneza nukuu kwa {customer}", "Create quote ya {customer}"),
        ("Analyse customer behaviour", "Changanua tabia ya wateja", "Analyse customer behaviour"),
    ],

    # Analytics
    "FORECAST_DEMAND": [
        ("Check current stock of {item}", "Angalia hisa ya sasa ya {item}", "Check current stock ya {item}"),
        ("Analyse inventory health", "Changanua afya ya hisa", "Analyse inventory health"),
        ("Generate reorder list", "Tengeneza orodha ya kuagiza", "Generate reorder list"),
        ("Get reorder decisions", "Pata maamuzi ya kuagiza", "Get reorder decisions"),
    ],
    "ANALYZE_INVENTORY_HEALTH": [
        ("Show low stock alerts", "Onyesha tahadhari za hisa chini", "Show low stock alerts"),
        ("Generate reorder list", "Tengeneza orodha ya kuagiza", "Generate reorder list"),
        ("Get reorder decisions", "Pata maamuzi ya kuagiza", "Get reorder decisions"),
        ("View warehouse breakdown", "Ona mgawanyiko wa ghala", "View warehouse breakdown"),
    ],
    "GET_REORDER_DECISIONS": [
        ("Show low stock alerts", "Onyesha tahadhari za hisa chini", "Show low stock alerts"),
        ("Analyse inventory health", "Changanua afya ya hisa", "Analyse inventory health"),
        ("Forecast demand for {item}", "Tabiri mahitaji ya {item}", "Forecast demand ya {item}"),
    ],
    "ANALYZE_PRICING_OPPORTUNITIES": [
        ("Check competitor prices", "Angalia bei za washindani", "Check competitor prices"),
        ("Find best price for {item}", "Pata bei bora ya {item}", "Find best price ya {item}"),
        ("Analyse inventory health", "Changanua afya ya hisa", "Analyse inventory health"),
    ],

    # Competitor pricing
    "COMPETITOR_PRICE_CHECK": [
        ("Check our price of {item}", "Angalia bei yetu ya {item}", "Check our price ya {item}"),
        ("Find best price for {item}", "Pata bei bora ya {item}", "Find best price ya {item}"),
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
        ("Analyse pricing opportunities", "Changanua fursa za bei", "Analyse pricing opportunities"),
    ],
    "FIND_BEST_PRICE": [
        ("Check our price of {item}", "Angalia bei yetu ya {item}", "Check our price ya {item}"),
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
        ("Add {item} to a quote", "Ongeza {item} kwenye nukuu", "Add {item} to quote"),
    ],
    "MARKET_INTELLIGENCE": [
        ("Check competitor prices", "Angalia bei za washindani", "Check competitor prices"),
        ("Analyse pricing opportunities", "Changanua fursa za bei", "Analyse pricing opportunities"),
        ("Forecast demand", "Tabiri mahitaji", "Forecast demand"),
    ],

    # Knowledge base & conversational
    "COMPANY_INFO": [
        ("How do I place an order?", "Ninawezaje kuweka agizo?", "Ninawezaje place an order?"),
        ("What are your payment methods?", "Njia gani za malipo mnapokubali?", "Njia gani za payment mnazokubali?"),
        ("Contact Leysco", "Wasiliana na Leysco", "Contact Leysco"),
    ],
    "PRODUCT_INFO": [
        ("Check price of {item}", "Angalia bei ya {item}", "Check price ya {item}"),
        ("Check stock of {item}", "Angalia hisa ya {item}", "Check stock ya {item}"),
        ("Add {item} to a quote", "Ongeza {item} kwenye nukuu", "Add {item} to quote"),
    ],
    "GREETING": [
        ("Check price of an item", "Angalia bei ya bidhaa", "Check price ya item"),
        ("Show me stock levels", "Nionyeshe viwango vya hisa", "Show me stock levels"),
        ("Create a quotation", "Tengeneza nukuu", "Create quotation"),
        ("What can you help me with?", "Unaweza kunisaidia na nini?", "What can you help me with?"),
    ],
    "HOW_TO_ORDER": [
        ("Create a quotation", "Tengeneza nukuu", "Create quotation"),
        ("Check item prices", "Angalia bei za bidhaa", "Check item prices"),
        ("Find a customer", "Tafuta mteja", "Find customer"),
    ],
    "SMALL_TALK": [
        ("Check item price", "Angalia bei ya bidhaa", "Check item price"),
        ("Show stock levels", "Onyesha viwango vya hisa", "Show stock levels"),
        ("Create a quotation", "Tengeneza nukuu", "Create quotation"),
    ],

    "FOLLOW_UP_QUOTATIONS": [
        ("Create quote for {customer}", "Tengeneza nukuu kwa {customer}", "Create quote ya {customer}"),
        ("View stale quotations", "Ona nukuu za zamani", "View stale quotations"),
        ("Check quotation conversion rate", "Angalia kiwango cha ubadilishaji", "Check conversion rate"),
        ("View all quotations", "Ona nukuu zote", "View quotations zote"),
    ],
    # Fallback — used when intent has no specific entry
    "_DEFAULT": [
        ("Check item price", "Angalia bei ya bidhaa", "Check item price"),
        ("Check stock levels", "Angalia viwango vya hisa", "Check stock levels"),
        ("Create a quotation", "Tengeneza nukuu", "Create quotation"),
        ("Show warehouses", "Onyesha maghala", "Show warehouses"),
    ],
}

# Unit suffixes kept lowercase when title-casing
_UNIT_SUFFIXES = {"ml", "kg", "g", "l", "lt", "gm", "mg"}


def _unwrap_entity(val):
    """
    Entity extractors sometimes return (value, is_exact_match) tuples
    instead of plain strings (e.g. the item/customer fuzzy matcher).
    Normalize to a plain string/None here so downstream .strip() calls
    never raise AttributeError: 'tuple' object has no attribute 'strip'.
    """
    if isinstance(val, tuple):
        val = val[0] if val else None
    return val


def _title_item(name: str) -> str:
    """
    'vegimax 10ml'       -> 'Vegimax 10ml'
    'magomano suppliers' -> 'Magomano Suppliers'
    Unit suffixes stay lowercase.
    """
    if not name:
        return name
    return " ".join(
        w.lower() if w.lower() in _UNIT_SUFFIXES else w.capitalize()
        for w in name.split()
    )


class SuggestionsEngine:
    """
    Generates context-aware quick reply chips for the Flutter frontend.
    Optimized with caching for better performance.

    Usage
    -----
    chips = suggestions_engine.get(
        intent   = "GET_ITEM_PRICE",
        entities = {"item_name": "vegimax 10ml"},
        language = "en",
    )
    # -> ["Check stock of Vegimax 10ml", "Customer price for Vegimax 10ml",
    #     "Add Vegimax 10ml to a quote", "See similar products"]
    """

    MAX_CHIPS = 4

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes

    def _get_cache_key(self, intent: str, entities: dict, language: str) -> str:
        """Generate cache key for suggestions."""
        # Create a stable representation of entities. Unwrap tuple-valued
        # entities (item_name/customer_name may be (value, is_exact)) so
        # equivalent entities produce the same cache key.
        entity_str = "|".join(
            f"{k}:{_unwrap_entity(v)}"
            for k, v in sorted(entities.items())
            if v and not k.startswith('_')
        )
        return f"suggestions:{intent}:{language}:{entity_str}"

    @lru_cache(maxsize=256)
    def _get_cached(self, intent: str, entity_str: str, language: str) -> Optional[list]:
        """
        LRU-cached version of suggestions generation.
        Uses entity_str instead of full dict for caching.
        """
        # This is a cache decorator - the actual logic is in _generate
        pass

    def get(
        self,
        intent: str,
        entities: dict,
        language: str = "en",
        use_cache: bool = True
    ) -> list[str]:
        """
        Return up to MAX_CHIPS ready-to-send suggestion strings.
        Optimized with caching.

        Args:
            intent:   Intent that was just handled.
            entities: Entity dict from EntityExtractor.
            language: 'en', 'sw', or 'mixed'.  Defaults to 'en'.
            use_cache: Whether to use cached results.

        Returns:
            List of strings, 0-MAX_CHIPS items.
        """
        lang = (language or "en").lower().strip()
        col = {"en": 0, "sw": 1, "mixed": 2}.get(lang, 0)

        # Check cache first
        if use_cache:
            cache_key = self._get_cache_key(intent, entities, language)
            if cache_key in self._cache:
                logger.info(f"⚡ Suggestions cache hit: {intent}")
                return self._cache[cache_key]

        templates = _SUGGESTIONS.get(intent.upper(), _SUGGESTIONS["_DEFAULT"])

        # Entity extractors may return (value, is_exact_match) tuples for
        # item_name / customer_name — unwrap before calling .strip().
        item = (_unwrap_entity(entities.get("item_name")) or "").strip()
        customer = (_unwrap_entity(entities.get("customer_name")) or "").strip()
        warehouse = (_unwrap_entity(entities.get("warehouse")) or "").strip()

        chips: list[str] = []

        for tpl_tuple in templates:
            tpl = tpl_tuple[col]

            if "{item}" in tpl and not item:
                continue
            if "{customer}" in tpl and not customer:
                continue
            if "{warehouse}" in tpl and not warehouse:
                continue

            chip = tpl
            if item:
                chip = chip.replace("{item}", _title_item(item))
            if customer:
                chip = chip.replace("{customer}", _title_item(customer))
            if warehouse:
                chip = chip.replace("{warehouse}", _title_item(warehouse))

            chips.append(chip)
            if len(chips) >= self.MAX_CHIPS:
                break

        # Pad to at least 2 chips with entity-free fallbacks
        if len(chips) < 2:
            for tpl_tuple in _SUGGESTIONS["_DEFAULT"]:
                tpl = tpl_tuple[col]
                if any(p in tpl for p in ("{item}", "{customer}", "{warehouse}")):
                    continue
                if tpl not in chips:
                    chips.append(tpl)
                if len(chips) >= self.MAX_CHIPS:
                    break

        # Cache the result
        if use_cache:
            cache_key = self._get_cache_key(intent, entities, language)
            self._cache[cache_key] = chips
            # Clean old cache entries if needed
            if len(self._cache) > 500:
                # Remove oldest 100 entries
                oldest_keys = list(self._cache.keys())[:100]
                for key in oldest_keys:
                    del self._cache[key]

        logger.debug(
            "SuggestionsEngine: intent=%s lang=%s -> %d chips: %s",
            intent, lang, len(chips), chips,
        )
        return chips

    async def get_async(
        self,
        intent: str,
        entities: dict,
        language: str = "en",
        use_cache: bool = True
    ) -> list[str]:
        """
        Async version of get() - runs in thread pool.
        """
        return await asyncio.to_thread(self.get, intent, entities, language, use_cache)

    def clear_cache(self):
        """Clear the suggestions cache."""
        self._cache.clear()
        logger.info("Suggestions cache cleared")


# Module-level singleton — import this in ai_routes.py
suggestions_engine = SuggestionsEngine()