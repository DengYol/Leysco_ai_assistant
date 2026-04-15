"""
entity_extractor.py
===================
Smart Hybrid Entity Extraction Engine.
Rule-first for speed, AI fallback for intelligence.
Optimized with async support, caching, and parallel processing.
"""

import logging
import json
import re
import time
import asyncio
import difflib
from typing import Optional, Dict, Any, List, Tuple
from functools import lru_cache
from app.services.llm_service import LLMService
from app.ai_engine.prompt_manager import PromptManager
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "couple": 2, "few": 3, "some": 5,
}

# Words that indicate a name is a business/customer, not an item
CUSTOMER_SUFFIX_WORDS = {
    "suppliers", "supplier", "vendor", "vendors", "traders", "trader",
    "enterprises", "enterprise", "solutions", "company", "co", "ltd",
    "limited", "inc", "group", "associates", "agency", "agencies",
    "industries", "industry", "international", "brothers", "bros",
    "holdings", "services", "distributors", "distributor",
    "technologies", "tech", "systems", "solutions", "consulting",
    "logistics", "transport", "shipping", "trading", "imports", "exports",
    "corporation", "corp", "llc", "l.l.c", "global", "worldwide",
    "partners", "ventures", "enterprise", "business", "firm", "shop",
    "store", "retail", "wholesale", "distributor", "dealer", "agency",
    "agrovet", "farm", "farms", "agro", "agri", "agriculture",
}

# Words that indicate the text is definitely a product/item, not a customer
PRODUCT_INDICATORS = {
    "vegimax", "cabbage", "tomato", "seed", "seeds", "fertilizer",
    "pesticide", "herbicide", "fungicide", "chemical", "insecticide",
    "maize", "wheat", "rice", "beans", "peas", "onion", "potato",
    "carrot", "kale", "spinach", "capsicum", "chili", "pepper",
    "cucumber", "pumpkin", "squash", "melon", "watermelon",
    "strawberry", "raspberry", "blueberry", "blackberry",
    "apple", "orange", "mango", "banana", "pineapple", "avocado",
    "grape", "lemon", "lime", "grapefruit", "herb", "spice",
    "easeed", "agriscope", "tosheka", "kh500", "mh401", "snowball",
    "yolo wonder", "blockies", "lumarx", "smd", "cti",
    "takii", "takii logo", "rmst0512", "takii seed", "takii seeds",
}

# Words to strip from a customer name before sending to the API
STRIP_FROM_SEARCH = {
    "suppliers", "supplier", "vendor", "vendors", "traders", "trader",
    "enterprises", "enterprise", "company", "ltd", "limited",
    "inc", "group", "associates", "agency", "agencies",
    "industries", "industry", "international", "brothers", "bros",
    "holdings", "services", "distributors", "distributor",
}

# Common warehouse names and keywords
WAREHOUSE_KEYWORDS = {
    "warehouse", "store", "branch", "depot", "facility", "storage",
    "dispatch", "shipping", "receiving", "main", "nairobi", "mombasa",
    "kisumu", "eldoret", "central", "north", "south", "east", "west",
    "inactive", "active", "quarantine", "quarntine", "bonded", "free",
}

# Words that should NOT be captured as warehouse names
WAREHOUSE_STOP_WORDS = {
    "is", "in", "at", "from", "the", "a", "an", "and", "or", "but",
    "show", "list", "get", "find", "tell", "me", "please", "can", "you",
    "what", "where", "how", "which", "when", "why",
}

# Words that indicate informational queries (not item searches)
INFO_QUERY_INDICATORS = {
    "tell me about", "what is", "about ", "information on", "info on",
    "details about", "learn about", "explain", "describe",
}

# Words that indicate forecast/demand prediction queries
FORECAST_INDICATORS = {
    "forecast", "predict", "projection", "future", "demand", "sales trend",
    "will sell", "expected", "anticipate", "estimate", "outlook",
    "how much will", "how many will", "predict demand", "forecast demand",
}

# Words that indicate competitor pricing queries
COMPETITOR_PRICING_INDICATORS = {
    "competitor price", "market price", "compare price", "price comparison",
    "market intelligence", "price alert", "best price", "cheapest",
    "lowest price", "who sells", "where to buy", "best deal",
}

# Words that indicate cross-sell/recommendation queries
RECOMMENDATION_INDICATORS = {
    "customers who bought", "also bought", "frequently bought",
    "people also buy", "others bought", "similar customers bought",
    "what else do customers buy with", "commonly bought with",
    "bundle with", "frequently purchased together", "who bougth",
    "who bought", "customers who buy", "people who buy",
    "recommend items", "suggest items", "recommend products",
    "suggest products", "what to sell", "items to sell",
    "cross sell", "cross-sell", "upsell", "up-sell",
    "also buys what", "buys what", "also purchases",
}

# Words that indicate seasonal queries
SEASONAL_INDICATORS = {
    "seasonal", "what to plant", "best for this season", "what grows in",
    "planting guide", "seasonal picks", "this month", "current month",
    "in season", "spring", "summer", "fall", "autumn", "winter",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december"
}

# Words that should NOT be treated as item names in recommendation queries
RECOMMENDATION_IGNORE_WORDS = {
    "customer", "customers", "to", "sell", "for", "recommend",
    "suggest", "items", "products", "cross", "cross-sell", "upsell",
    "up-sell", "to", "for", "with", "and", "the", "a", "an",
    "who", "bought", "buys", "what", "also", "buys", "purchases",
}

# Words that indicate listing queries (should not extract customer name)
LISTING_INDICATORS = {
    "all", "list", "show", "display", "view", "get", "find",
}

# Pronoun words for context resolution
PRONOUN_WORDS = {
    "their", "them", "they", "him", "her", "it", "that", "this", "these", "those"
}

# Month mapping
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]

# ── Item fuzzy matching config ────────────────────────────────────────────────
ITEM_FUZZY_CUTOFF = 0.70
ITEM_FUZZY_N = 1
ITEM_CACHE_TTL = 300

# Size patterns for product variants (ml, kg, g, l, etc.)
SIZE_PATTERNS = [
    r'(\d+(?:\.\d+)?)\s*(ml|ML|mL|kg|KG|g|G|l|L|lt|LT)',
    r'(ml|ML|mL|kg|KG|g|G|l|L|lt|LT)\s*(\d+(?:\.\d+)?)',
    r'(\d+)\s*(?:ml|ML|mL|kg|KG|g|G|l|L|lt|LT)',
]

# Common size values for prioritization with normalized keys
COMMON_SIZES = {
    "10ml": 100, "10 ml": 100, "10ml": 100,
    "30ml": 90, "30 ml": 90, "30ml": 90,
    "125ml": 70, "125 ml": 70, "125ml": 70,
    "250ml": 60, "250 ml": 60, "250ml": 60,
    "500ml": 50, "500 ml": 50, "500ml": 50,
    "1kg": 100, "1 kg": 100, "1kg": 100,
    "2kg": 90, "2 kg": 90, "2kg": 90,
    "5kg": 70, "5 kg": 70, "5kg": 70,
    "10kg": 60, "10 kg": 60, "10kg": 60,
    "25kg": 50, "25 kg": 50, "25kg": 50,
    "50kg": 40, "50 kg": 40, "50kg": 40,
}

# ── Customer name noise prefix pattern (FIXED) ────────────────────────────────
# Strips leading noise like "orders for", "customer orders for", etc.
_CUSTOMER_NAME_NOISE = re.compile(
    r"^\s*(?:"
    r"orders?\s+for|"
    r"customer\s+orders?\s+for|"
    r"client\s+orders?\s+for|"
    r"details?\s+for|"
    r"invoices?\s+for|"
    r"info\s+(?:for|on)|"
    r"information\s+(?:for|on)|"
    r"quotations?\s+for|"
    r"show\s+(?:me\s+)?"
    r")\s*",
    re.IGNORECASE,
)


def clean_customer_search_term(name: str) -> str:
    """
    Strip generic business suffix words from a customer name before
    passing it to the API search, so 'magomano suppliers' → 'magomano'.
    Falls back to the original name if stripping would leave nothing.
    """
    if not name:
        return name
    tokens = name.lower().split()
    cleaned = [t for t in tokens if t not in STRIP_FROM_SEARCH]
    return " ".join(cleaned).strip() or name


def clean_customer_name(raw: str) -> str:
    """
    Strip leading noise phrases from a raw extracted customer name.
    E.g. 'orders for Maa's Agrovet' → 'Maa's Agrovet'
    Falls back to original if cleaning leaves nothing.
    """
    if not raw:
        return raw
    cleaned = _CUSTOMER_NAME_NOISE.sub("", raw).strip()
    return cleaned if cleaned else raw


def normalize_size(size_str: str) -> str:
    """
    Normalize size string to a standard format for comparison.
    E.g., '10 ml' → '10ml', '250 ML' → '250ml'
    """
    if not size_str:
        return ""
    # Remove spaces and convert to lowercase
    normalized = re.sub(r'\s+', '', size_str.lower())
    # Ensure unit is standardized
    normalized = re.sub(r'ml$', 'ml', normalized)
    normalized = re.sub(r'kg$', 'kg', normalized)
    normalized = re.sub(r'g$', 'g', normalized)
    normalized = re.sub(r'l$', 'l', normalized)
    return normalized


class EntityExtractor:
    """
    Smart Hybrid Entity Extraction Engine.
    Rule-first for speed, AI fallback for intelligence.
    """

    def __init__(self):
        self.llm = LLMService()
        self.prompt_manager = PromptManager()

        # ── Item name cache (shared across calls, refreshed by TTL) ──────────
        self._item_names_cache: list[str] = []
        self._item_cache_loaded_at: float = 0.0
        self._customer_names_cache: list[str] = []
        self._customer_cache_loaded_at: float = 0.0

        # Simple in-memory cache for extracted entities
        self._extract_cache = {}
        self._extract_cache_ttl = 300  # 5 minutes

        # Lazy-loaded API service
        self._api_service = None

    @property
    def api_service(self):
        """Lazy load API service to avoid circular imports."""
        if self._api_service is None:
            from app.services.leysco_api_service import get_leysco_api_service
            self._api_service = get_leysco_api_service()
        return self._api_service

    # -------------------------------------------------
    # QUICK SKIP LOGIC
    # -------------------------------------------------
    def _should_skip_ai(self, text: str) -> bool:
        words = text.lower().split()
        generic_patterns = [
            "show items", "list items", "show customers",
            "list customers", "show invoices", "recommend items",
            "forecast demand", "predict sales", "demand forecast",
        ]
        if len(words) <= 3:
            return True
        return any(p in text.lower() for p in generic_patterns)

    # -------------------------------------------------
    # FUZZY CUSTOMER CORRECTION (with caching)
    # -------------------------------------------------
    def _correct_customer_typo(self, name: str) -> str:
        """Correct customer name typo with caching."""
        customers = self._load_customers()
        if not customers:
            return name

        matches = difflib.get_close_matches(
            name.lower(),
            customers,
            n=1,
            cutoff=0.75,
        )

        if matches:
            corrected = matches[0]
            if corrected != name.lower():
                logger.info(f"Customer typo corrected: '{name}' → '{corrected}'")
            return corrected

        return name

    # -------------------------------------------------
    # FUZZY ITEM CORRECTION (with caching)
    # -------------------------------------------------
    @lru_cache(maxsize=500)
    def _correct_item_typo_cached(self, name: str) -> str:
        """Cached version of item typo correction."""
        items = self._load_item_names()
        if not items:
            return name

        query = name.lower().strip()
        query_len = len(query)

        # ── Pass 1: match query against the leading portion of each name ──────
        prefix_map: dict[str, str] = {}
        for full_name in items:
            words = full_name.split()

            # First N chars (length-matched prefix)
            prefix = full_name[:query_len + 2].strip()
            if prefix and prefix not in prefix_map:
                prefix_map[prefix] = full_name

            # First word alone
            if words:
                fw = words[0]
                if fw not in prefix_map:
                    prefix_map[fw] = full_name

            # All consecutive word-group substrings
            for i in range(len(words)):
                for j in range(i + 1, len(words) + 1):
                    sub = " ".join(words[i:j])
                    if sub not in prefix_map:
                        prefix_map[sub] = full_name

        prefix_matches = difflib.get_close_matches(
            query,
            list(prefix_map.keys()),
            n=ITEM_FUZZY_N,
            cutoff=ITEM_FUZZY_CUTOFF,
        )
        if prefix_matches:
            corrected = prefix_map[prefix_matches[0]]
            if corrected != query:
                logger.info(f"Item typo corrected (pass 1): '{name}' → '{corrected}'")
            return corrected

        # ── Pass 2: full-string match ─────────────────────────────────────────
        full_matches = difflib.get_close_matches(
            query,
            items,
            n=ITEM_FUZZY_N,
            cutoff=ITEM_FUZZY_CUTOFF,
        )
        if full_matches:
            corrected = full_matches[0]
            if corrected != query:
                logger.info(f"Item typo corrected (pass 2): '{name}' → '{corrected}'")
            return corrected

        logger.debug(f"No fuzzy match for item: '{name}' (cutoff={ITEM_FUZZY_CUTOFF})")
        return name

    def _correct_item_typo(self, name: str) -> str:
        """Wrapper for cached item typo correction."""
        return self._correct_item_typo_cached(name)

    # -------------------------------------------------
    # LOAD CUSTOMERS FOR FUZZY MATCHING (with TTL)
    # -------------------------------------------------
    def _load_customers(self) -> list:
        """Load customer names for fuzzy matching with TTL."""
        now = time.monotonic()
        if self._customer_names_cache and (now - self._customer_cache_loaded_at) < ITEM_CACHE_TTL:
            return self._customer_names_cache

        try:
            customers = self.api_service.get_all_customers(limit=2000)
            self._customer_names_cache = [c.get("CardName", "").lower() for c in customers if c.get("CardName")]
            self._customer_cache_loaded_at = now
            logger.info(f"Customer name cache refreshed: {len(self._customer_names_cache)} customers loaded")
            return self._customer_names_cache
        except Exception as e:
            logger.warning(f"Could not load customers: {e}")
            return []

    # -------------------------------------------------
    # LOAD ITEM NAMES FOR FUZZY MATCHING (with TTL)
    # -------------------------------------------------
    def _load_item_names(self) -> list[str]:
        """Return a cached list of lowercase item names from the SAP catalogue."""
        now = time.monotonic()
        if self._item_names_cache and (now - self._item_cache_loaded_at) < ITEM_CACHE_TTL:
            return self._item_names_cache

        try:
            raw_items = self.api_service.get_items(limit=2000)

            names: list[str] = []
            for item in raw_items:
                for field in ("ItemName", "itemName", "name", "Description"):
                    val = item.get(field)
                    if val and isinstance(val, str):
                        names.append(val.lower().strip())
                        break

            self._item_names_cache = names
            self._item_cache_loaded_at = now
            logger.info(f"Item name cache refreshed: {len(names)} items loaded")

        except Exception as exc:
            logger.warning(f"Could not load item names for fuzzy matching: {exc}")
            if not self._item_names_cache:
                self._item_names_cache = []

        return self._item_names_cache

    # -------------------------------------------------
    # CUSTOMER NAME DETECTION HELPERS
    # -------------------------------------------------
    def _looks_like_company(self, text: str) -> bool:
        """Check if text looks like a company/customer name."""
        if not text or len(text) < 3:
            return False

        text_lower = text.lower()

        for suffix in CUSTOMER_SUFFIX_WORDS:
            if suffix in text_lower:
                return True

        original_words = text.split()
        capitalized_count = sum(1 for w in original_words if w and w[0].isupper())
        if len(original_words) >= 2 and capitalized_count >= len(original_words) - 1:
            for product in PRODUCT_INDICATORS:
                if product in text_lower:
                    return False
            return True

        company_patterns = [
            r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$',
            r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Ltd|Limited|Inc|Corp|LLC|Co)$',
            r'^(?:The\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Company|Corporation)$',
            r'^[A-Z]{2,}(?:\s+[A-Z]{2,})*$',
            r'^[A-Z][A-Z\s\']+(?:\s+-\s+[A-Z]+)?$',
        ]

        for pattern in company_patterns:
            if re.match(pattern, text):
                return True

        return False

    def _is_product_name(self, text: str) -> bool:
        """Check if text is likely a product name."""
        if not text:
            return False

        text_lower = text.lower()

        for product in PRODUCT_INDICATORS:
            if product in text_lower:
                return True

        words = text_lower.split()
        if len(words) == 1 and not words[0][0].isupper():
            return True

        return False

    def _is_customer_code(self, text: str) -> bool:
        """Check if text looks like a customer code (e.g., CL01243, V50000)."""
        return bool(re.match(r'^[A-Z]{2,3}\d{4,8}$', text.upper()))

    def _is_pronoun_query(self, text: str) -> bool:
        """Check if query contains pronoun words (no specific customer name)."""
        text_lower = text.lower()
        has_pronoun = any(word in text_lower for word in PRONOUN_WORDS)
        pronoun_phrases = [
            r'\b(?:their|his|her|its)\s+(?:orders?|details?|info|quotation|delivery|invoices?)\b',
            r'(?:show|get|find|check)\s+(?:their|his|her|its)\s+(?:orders?|details?)\b',
        ]
        has_pronoun_phrase = any(re.search(pattern, text_lower) for pattern in pronoun_phrases)
        return has_pronoun or has_pronoun_phrase

    def _is_listing_query(self, text: str) -> bool:
        """Check if query is asking to list customers (not a specific one)."""
        text_lower = text.lower()

        if self._is_customer_code(text_lower):
            return False

        if re.search(r'[A-Z][A-Za-z\s\']+\s*-\s*[A-Z]+', text):
            return False

        listing_patterns = [
            r'\b(?:all|list|show|display|view)\s+(?:customers|clients|companies)\b',
            r'\b(?:customers|clients|companies)\s+(?:list|all)\b',
            r'^show\s+me\s+(?:customers|clients)$',
            r'^list\s+(?:customers|clients)$',
            r'^get\s+(?:customers|clients)$',
            r'^all\s+(?:customers|clients)$',
            r'^customers\s*$',
        ]

        for pattern in listing_patterns:
            if re.search(pattern, text_lower):
                return True

        if re.search(r'\b\d+\s+(?:customers|clients)\b', text_lower) and not re.search(r'[A-Z][A-Za-z\s\']+', text):
            return True

        return False

    def _extract_limit_from_query(self, text: str) -> Optional[int]:
        """Extract a limit number from listing queries (e.g., '5 customers')."""
        text_lower = text.lower()

        match = re.search(r'\b(\d+)\s+(?:customers|clients)\b', text_lower)
        if match:
            return int(match.group(1))

        for word, num in NUMBER_WORDS.items():
            if re.search(rf'\b{word}\s+(?:customers|clients)\b', text_lower):
                return num

        return None

    # -------------------------------------------------
    # QUERY TYPE DETECTION
    # -------------------------------------------------
    def _is_info_query(self, text: str) -> bool:
        text_lower = text.lower()
        for indicator in INFO_QUERY_INDICATORS:
            if indicator in text_lower:
                return True
        if "about" in text_lower:
            words = text_lower.split()
            for i, word in enumerate(words):
                if word == "about" and i + 1 < len(words):
                    potential_product = words[i + 1]
                    if potential_product in PRODUCT_INDICATORS:
                        return True
        return False

    def _is_forecast_query(self, text: str) -> bool:
        text_lower = text.lower()
        if self._is_seasonal_query(text_lower):
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

    def _is_seasonal_query(self, text: str) -> bool:
        text_lower = text.lower()
        for indicator in SEASONAL_INDICATORS:
            if indicator in text_lower:
                return True
        return False

    def _is_recommendation_query(self, text: str) -> bool:
        text_lower = text.lower()
        for indicator in RECOMMENDATION_INDICATORS:
            if indicator in text_lower:
                return True
        return False

    def _extract_month(self, text: str) -> str | None:
        text_lower = text.lower()
        for month in MONTHS:
            if month in text_lower:
                logger.info(f"Detected month: {month}")
                return month
        return None

    def _is_competitor_pricing_query(self, text: str) -> bool:
        text_lower = text.lower()
        for indicator in COMPETITOR_PRICING_INDICATORS:
            if indicator in text_lower:
                return True
        return False

    # -------------------------------------------------
    # WAREHOUSE DETECTION - ENHANCED
    # -------------------------------------------------
    def _extract_warehouse(self, text: str) -> str | None:
        """Extract warehouse name with improved patterns."""
        text_lower = text.lower()
        original_text = text

        pattern_in = r'\b(?:in|from|at)\s+([a-zA-Z0-9\s\-]+)(?:\s+warehouse|\s+stock|\s+items?)?(?:\?|$)'
        match = re.search(pattern_in, text_lower)
        if match:
            candidate = match.group(1).strip()
            candidate = re.sub(r'\b(warehouse|stock|items|item|the|a|an)\b', '', candidate).strip()
            if candidate and len(candidate) > 2:
                logger.info(f"🏭 Extracted warehouse from 'in/from/at' pattern: '{candidate}'")
                return candidate

        pattern_warehouse = r'\bwarehouse\s+([a-zA-Z0-9\s\-]+?)(?:\s+stock|\s+items?|\?|$)'
        match = re.search(pattern_warehouse, text_lower)
        if match:
            candidate = match.group(1).strip()
            if candidate and len(candidate) > 2:
                logger.info(f"🏭 Extracted warehouse from 'warehouse X' pattern: '{candidate}'")
                return candidate

        pattern_name_warehouse = r'([a-zA-Z0-9\s\-]+?)\s+warehouse(?:\s+stock|\s+items?|\?|$)'
        match = re.search(pattern_name_warehouse, text_lower)
        if match:
            candidate = match.group(1).strip()
            if candidate and len(candidate) > 2:
                logger.info(f"🏭 Extracted warehouse from 'X warehouse' pattern: '{candidate}'")
                return candidate

        if self._is_competitor_pricing_query(text_lower):
            location_match = re.search(
                r'(?:in|at)\s+([a-zA-Z]+(?:[\s-][a-zA-Z]+)?)\s*$', text_lower
            )
            if location_match:
                candidate = location_match.group(1).strip()
                if candidate in {"nairobi", "mombasa", "kisumu", "eldoret"}:
                    return candidate
            return None

        cleaned_for_warehouse = re.sub(
            r'\b(show|list|get|find|tell|me|please|can|you|what|where|how|which)\b',
            '', text_lower
        )

        pattern1 = r'(?:in|at|from)\s+([a-zA-Z0-9]+(?:\s+[a-zA-Z0-9]+)?)\s+(?:warehouse|store|branch|depot)'
        match = re.search(pattern1, cleaned_for_warehouse)
        if match:
            candidate = match.group(1).strip()
            if all(w not in WAREHOUSE_STOP_WORDS for w in candidate.split()):
                return candidate

        pattern2 = r'([a-zA-Z0-9]+)\s+(?:warehouse|store|branch|depot)(?:\s|$)'
        match = re.search(pattern2, cleaned_for_warehouse)
        if match:
            candidate = match.group(1).strip()
            if candidate not in WAREHOUSE_STOP_WORDS:
                return candidate

        pattern3 = r'(?:warehouse|store|branch|depot)\s+([a-zA-Z0-9]+)'
        match = re.search(pattern3, cleaned_for_warehouse)
        if match:
            candidate = match.group(1).strip()
            if candidate not in WAREHOUSE_STOP_WORDS:
                return candidate

        for warehouse in ["main", "nairobi", "mombasa", "kisumu", "eldoret",
                          "central", "north", "south", "east", "west",
                          "dispatch", "shipping", "receiving", "quarantine"]:
            if warehouse in cleaned_for_warehouse:
                if warehouse == "west" and "lowest" in text_lower:
                    continue
                return warehouse

        return None

    # -------------------------------------------------
    # RULE-BASED EXTRACTION (Optimized with caching)
    # -------------------------------------------------
    @lru_cache(maxsize=256)
    def _rule_based_entities_cached(self, text: str) -> dict:
        """Cached version of rule-based entity extraction."""
        return self._rule_based_entities_impl(text)

    def _rule_based_entities_impl(self, text: str) -> dict:
        """Implementation of rule-based entity extraction."""
        text_lower = text.lower()
        original_text = text

        is_info = self._is_info_query(text)
        is_forecast = self._is_forecast_query(text)
        is_competitor_pricing = self._is_competitor_pricing_query(text)
        is_recommendation = self._is_recommendation_query(text)
        is_seasonal = self._is_seasonal_query(text)
        is_listing = self._is_listing_query(text)

        month = None
        if is_seasonal:
            month = self._extract_month(text)
            logger.info(f"Seasonal query detected with month: {month}")

        is_best_price = any(phrase in text_lower for phrase in [
            "best price", "cheapest", "lowest price", "who sells",
            "where to buy", "best deal", "who has the best"
        ])
        is_compare = any(phrase in text_lower for phrase in [
            "compare", "comparison", "vs", "versus", "verses"
        ])
        is_price_alert = any(phrase in text_lower for phrase in [
            "price alert", "notify when", "alert me when", "track price"
        ])

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

        listing_limit = None
        if is_listing:
            listing_limit = self._extract_limit_from_query(text)
            if listing_limit:
                logger.info(f"📋 Listing query with limit: {listing_limit} customers")
                if not quantity:
                    quantity = listing_limit

        cleaned_text = re.sub(r"\b\d+\b", "", text_lower)
        for word in NUMBER_WORDS.keys():
            cleaned_text = re.sub(rf"\b{word}\b", "", cleaned_text)
        COMMAND_VERBS = r"\b(show|list|get|find|search|display|tell|give|look|create|make|generate)\b"
        cleaned_text = re.sub(COMMAND_VERBS, "", cleaned_text)
        cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

        date_match = re.search(
            r"\b(today|tomorrow|yesterday|\d{4}-\d{2}-\d{2})\b", text_lower,
        )

        if is_seasonal and month and not date_match:
            class SimpleMatch:
                def group(self, idx=0):
                    return month
                def __getitem__(self, idx):
                    return month
            date_match = SimpleMatch()

        detail_mode = bool(
            re.search(r"\b(detail|details|spec|specs|information|info|about)\b", text_lower)
        )

        warehouse = self._extract_warehouse(text)

        # =========================================================
        # CUSTOMER NAME EXTRACTION
        # =========================================================
        customer_name = None
        items_list = []

        # ── Step A: Quotation pattern (highest priority) ──────────────────────
        if 'quotation' in text_lower or 'quote' in text_lower:
            text_cleaned = original_text.strip()

            prefixes_to_remove = [
                r'^create\s+(?:a\s+)?quotation\s+for\s+',
                r'^make\s+(?:a\s+)?quotation\s+for\s+',
                r'^new\s+quotation\s+for\s+',
                r'^quotation\s+for\s+',
                r'^quote\s+for\s+',
                r'^create\s+(?:a\s+)?quotation\s+',
                r'^make\s+(?:a\s+)?quotation\s+',
                r'^new\s+quotation\s+',
                r'^quotation\s+',
                r'^quote\s+',
            ]

            for prefix in prefixes_to_remove:
                text_cleaned = re.sub(prefix, '', text_cleaned, flags=re.IGNORECASE)

            with_match = re.search(r'^(.+?)(?:\s+with\s+|\s*$)', text_cleaned, re.IGNORECASE)
            if with_match:
                customer = with_match.group(1).strip()
                customer = re.sub(r'\s+with\s*$', '', customer, flags=re.IGNORECASE)
                customer = re.sub(r'^for\s+', '', customer, flags=re.IGNORECASE)
                customer = re.sub(r'\s+\d+\s+[a-zA-Z0-9\-]+$', '', customer, flags=re.IGNORECASE)

                if customer and len(customer) > 1 and not customer[0].isdigit():
                    customer_name = customer
                    logger.info(f"📝 Extracted customer name for quotation: '{customer_name}'")

        # Extract items from quotation message
        if customer_name:
            after_customer = original_text.split(customer_name, 1)[-1] if customer_name in original_text else original_text
            item_pattern = r'(\d+)\s+([a-zA-Z0-9\-]+)\s+(\d+(?:ml|ML|mL|kg|KG|g|G|l|L))'
            matches = re.findall(item_pattern, after_customer, re.IGNORECASE)

            for qty, name, size in matches:
                items_list.append({
                    "name": f"{name} {size}",
                    "quantity": int(qty),
                    "size": size
                })
                logger.info(f"📦 Extracted item for quotation: qty={qty}, name={name} {size}")

            if not matches:
                simple_item_pattern = r'(\d+)\s+([a-zA-Z0-9\-]+)'
                matches = re.findall(simple_item_pattern, after_customer, re.IGNORECASE)
                for qty, name in matches:
                    if name.lower() not in ['with', 'and', 'for', 'quotation', 'create', 'make']:
                        items_list.append({
                            "name": name,
                            "quantity": int(qty),
                            "size": None
                        })
                        logger.info(f"📦 Extracted item (no size): qty={qty}, name={name}")

        # ── Step B: Non-quotation customer extraction ─────────────────────────
        if not customer_name and not is_competitor_pricing:
            pronoun_patterns = [
                r'\b(?:their|them|they|his|her|its)\s+(?:orders?|details?|info|quotation|delivery|invoices?)\b',
                r'(?:show|get|find|check)\s+(?:their|his|her|its)\s+(?:orders?|details?)\b',
                r'\b(?:their|them|they)\b',
            ]
            is_pronoun_query = any(re.search(pattern, text_lower) for pattern in pronoun_patterns)

            if is_pronoun_query:
                logger.info(f"🔁 Pronoun query detected: '{text}'")
                customer_name = None
            elif not is_listing:
                # ── Step B1: Customer code (e.g. CL01243) ────────────────────
                customer_code_patterns = [
                    r'\b([A-Z]{2,3}\d{4,8})\b',
                    r'\b(customer\s+code\s+([A-Z0-9]+))\b',
                    r'\b(code\s+([A-Z0-9]+))\b',
                ]

                for pattern in customer_code_patterns:
                    match = re.search(pattern, original_text, re.IGNORECASE)
                    if match:
                        code = match.group(1) if match.group(1) else (match.group(2) if len(match.groups()) > 1 else None)
                        if code and re.match(r'^[A-Z]{2,3}\d{4,8}$', code.upper()):
                            customer_name = code.upper()
                            logger.info(f"Extracted customer code: '{customer_name}'")
                            break

                if not customer_name:
                    # ── Step B2: "for <Name>" pattern (tried FIRST — most specific) ──
                    for_match = re.search(
                        r'\bfor\s+([A-Z][A-Za-z0-9\s\'\-&]{2,})',
                        original_text,
                        re.IGNORECASE,
                    )
                    if for_match:
                        candidate = for_match.group(1).strip()
                        # Strip any trailing noise that may have been captured
                        candidate = clean_customer_name(candidate)
                        if candidate.lower() not in {"all", "customers", "customer", "list", "show"}:
                            customer_name = candidate
                            logger.info(f"Extracted customer name (for-pattern): '{customer_name}'")

                if not customer_name:
                    # ── Step B3: "customer/client <Name>" pattern ─────────────
                    name_match = re.search(
                        r'(?:customer|client)\s+([A-Z][A-Za-z0-9\s\'\-&]{2,})',
                        original_text,
                        re.IGNORECASE,
                    )
                    if name_match:
                        candidate = name_match.group(1).strip()
                        # FIXED: strip leading noise words like "orders for"
                        candidate = clean_customer_name(candidate)
                        if candidate.lower() not in {"all", "customers", "customer", "list", "show"}:
                            customer_name = candidate
                            logger.info(f"Extracted customer name (customer-pattern): '{customer_name}'")
            else:
                logger.info("Listing query detected - not extracting customer name")

        # ── Step C: Safety net — strip noise from any customer name captured ──
        if customer_name:
            cleaned = clean_customer_name(customer_name)
            if cleaned != customer_name:
                logger.info(f"Customer name noise-stripped: '{customer_name}' → '{cleaned}'")
                customer_name = cleaned

        # =========================================================
        # ITEM EXTRACTION (with quotation items support)
        # =========================================================
        item_name = None
        detected_size = None
        exact_size_match_required = False

        if 'quotation' in text_lower and customer_name and not items_list:
            item_pattern = r'(\d+)\s+([a-zA-Z0-9\-]+)\s+(\d+(?:ml|ML|mL|kg|KG|g|G|l|L))'
            matches = re.findall(item_pattern, text, re.IGNORECASE)

            for qty, name, size in matches:
                items_list.append({
                    "name": f"{name} {size}",
                    "quantity": int(qty),
                    "size": size
                })
                if not item_name:
                    item_name = f"{name} {size}"
                    detected_size = normalize_size(size)
                    exact_size_match_required = True

            if items_list:
                logger.info(f"📦 Extracted {len(items_list)} items for quotation: {items_list}")

        if not detected_size:
            for pattern in SIZE_PATTERNS:
                match = re.search(pattern, text_lower)
                if match:
                    if len(match.groups()) == 2:
                        if match.group(1).isdigit() or (match.group(1) and match.group(1).replace('.', '').isdigit()):
                            size_num = match.group(1)
                            size_unit = match.group(2)
                            detected_size = f"{size_num}{size_unit}".lower()
                        elif match.group(2).isdigit() or (match.group(2) and match.group(2).replace('.', '').isdigit()):
                            size_num = match.group(2)
                            size_unit = match.group(1)
                            detected_size = f"{size_num}{size_unit}".lower()
                    else:
                        detected_size = match.group(0).lower()

                    detected_size = normalize_size(detected_size)
                    exact_size_match_required = True
                    logger.info(f"📏 Detected size: {detected_size} (exact match required: {exact_size_match_required})")
                    break

        if not item_name:
            sell_out_patterns = [
                r'sell\s+out\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'who\s+would\s+buy\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'which\s+customers?\s+buy\s+([a-zA-Z0-9\-\(\)\s]+)',
            ]

            for pattern in sell_out_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    item_name = match.group(1).strip()
                    break

        if is_recommendation and not item_name:
            cross_sell_patterns = [
                r'customers who bought\s+([a-zA-Z0-9\-\(\)\s]+?)\s+also',
                r'also bought with\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'what else do customers buy with\s+([a-zA-Z0-9\-\(\)\s]+)',
            ]
            for pattern in cross_sell_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    candidate = match.group(1).strip()
                    if candidate and len(candidate) > 1:
                        for prod in PRODUCT_INDICATORS:
                            if prod in candidate.lower():
                                item_name = prod
                                break
                        if not item_name and not self._looks_like_company(candidate):
                            item_name = candidate
                        break

        has_price_word = bool(re.search(
            r"\b(price|cost|how\s+much|what'?s?\s*(the)?\s*price|pricing|how\s+expensive|charge|rate)\b",
            text_lower, re.IGNORECASE
        ))

        if not item_name and has_price_word:
            price_patterns = [
                r'price\s+of\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'cost\s+of\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'how\s+much\s+is\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'what\s+is\s+the\s+price\s+of\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'what\s+does\s+([a-zA-Z0-9\-\(\)\s]+)\s+cost',
                r'price\s+for\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'best price for\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'cheapest\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'who sells\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'([a-zA-Z0-9\-]+)\s+(\d+(?:ml|ML|mL|kg|KG|g|G|l|L))\s+(?:price|cost)',
                r'([a-zA-Z0-9\-]+)\s+(?:price|cost)\s+(\d+(?:ml|ML|mL|kg|KG|g|G|l|L))',
            ]
            for pattern in price_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    candidate = match.group(1).strip()
                    if len(match.groups()) > 1 and match.group(2):
                        size_candidate = match.group(2).strip()
                        if detected_size is None:
                            detected_size = normalize_size(size_candidate)
                            exact_size_match_required = True
                    candidate = re.sub(r'\b(price|of|the|a|an|for|in|at|to|is|are|was|were)\b', '', candidate, flags=re.IGNORECASE)
                    candidate = candidate.strip()
                    if candidate and len(candidate) > 1:
                        if any(prod in candidate.lower() for prod in PRODUCT_INDICATORS) or not self._looks_like_company(candidate):
                            item_name = candidate
                            logger.info(f"Extracted item from price pattern: '{item_name}'")
                            break

            if not item_name:
                size_product_patterns = [
                    r'([a-zA-Z0-9\-]+)\s+(\d+(?:ml|ML|mL|kg|KG|g|G|l|L))',
                    r'(\d+(?:ml|ML|mL|kg|KG|g|G|l|L))\s+([a-zA-Z0-9\-]+)',
                ]
                for pattern in size_product_patterns:
                    match = re.search(pattern, text_lower)
                    if match:
                        if match.group(1).isdigit() or (match.group(1) and match.group(1).replace('.', '').isdigit()):
                            size_candidate = match.group(1)
                            product_candidate = match.group(2)
                        else:
                            product_candidate = match.group(1)
                            size_candidate = match.group(2)

                        if detected_size is None:
                            detected_size = normalize_size(size_candidate)
                            exact_size_match_required = True

                        if product_candidate and len(product_candidate) > 1:
                            if any(prod in product_candidate.lower() for prod in PRODUCT_INDICATORS) or not self._looks_like_company(product_candidate):
                                item_name = product_candidate
                                logger.info(f"Extracted item with size: '{item_name} {detected_size}'")
                                break

        base_item_name = item_name
        if item_name and detected_size:
            size_pattern = re.compile(r'\s+' + re.escape(detected_size) + r'\b', re.IGNORECASE)
            base_item_name = size_pattern.sub('', item_name).strip()
            base_item_name = re.sub(r'\s+\d+(?:ml|kg|g|l)\b', '', base_item_name, flags=re.IGNORECASE).strip()
            logger.info(f"Base item name (without size): '{base_item_name}'")

        if item_name and detected_size:
            if detected_size.lower() not in item_name.lower():
                item_name = f"{item_name} {detected_size}"
                logger.info(f"Enhanced item name with size: '{item_name}'")

        if item_name:
            item_name = re.sub(
                r"\b(item|product|details?|specs?|info|for|of|to|with|price|cost|the|a|an)\b",
                "", item_name, flags=re.IGNORECASE
            ).strip()

            if self._looks_like_company(item_name) and not self._is_product_name(item_name):
                logger.info(f"Item '{item_name}' looks like company — moving to customer_name")
                if not customer_name:
                    customer_name = item_name
                item_name = None

        # Extract from "for [company]" patterns (fallback)
        if not customer_name and not is_listing and not is_competitor_pricing:
            for_company_match = re.search(r'for\s+([A-Z][a-zA-Z0-9\s&\-.]+)$', original_text)
            if for_company_match:
                potential_customer = for_company_match.group(1).strip()
                if self._looks_like_company(potential_customer) or self._is_customer_code(potential_customer):
                    customer_name = potential_customer

        if is_forecast and not quantity:
            quantity = 30

        date_value = None
        if date_match:
            if hasattr(date_match, 'group'):
                try:
                    date_value = date_match.group(1)
                except (IndexError, TypeError):
                    try:
                        date_value = date_match.group(0)
                    except:
                        date_value = str(date_match)
            elif isinstance(date_match, str):
                date_value = date_match
            else:
                date_value = str(date_match)

        result = {
            "item_name": item_name if item_name else None,
            "base_item_name": base_item_name if base_item_name and base_item_name != item_name else None,
            "customer_name": customer_name if customer_name else None,
            "quantity": quantity,
            "warehouse": warehouse,
            "date": date_value,
            "detail_mode": detail_mode,
        }
        if items_list:
            result["items"] = items_list
        if detected_size:
            result["_detected_size"] = detected_size
            result["_exact_size_required"] = exact_size_match_required
            result["_normalized_size"] = normalize_size(detected_size)

        return result

    def _rule_based_entities(self, text: str) -> dict:
        """Wrapper for cached rule-based entity extraction."""
        return self._rule_based_entities_cached(text)

    # -------------------------------------------------
    # MAIN EXTRACTION FLOW (Async Optimized)
    # -------------------------------------------------
    def extract(self, user_message: str, initial_entities: dict = None) -> dict:
        """Sync extraction - for compatibility."""
        return asyncio.run(self.extract_async(user_message, initial_entities))

    async def extract_async(self, user_message: str, initial_entities: dict = None) -> dict:
        """
        Extract entities from user message with async support and caching.

        CRITICAL: Current message ALWAYS takes priority over session entities.
        """
        # ── Step 1: Check cache ──────────────────────────────────────────────
        cache_key = f"entities:{user_message}"
        cached = await cache_service.get_simple_async(cache_key)
        if cached and not initial_entities:
            logger.info(f"⚡ Entities cache hit: {user_message[:50]}...")
            return cached

        # ── Step 2: Extract fresh entities from current message ──────────────
        fresh_entities = self._rule_based_entities(user_message)
        logger.info(f"Fresh entities from current message: {fresh_entities}")

        # ── Step 3: Check if this is a pronoun query ─────────────────────────
        is_pronoun_query = self._is_pronoun_query(user_message)

        # ── Step 4: Merge with session entities if provided ──────────────────
        if initial_entities:
            logger.info(f"Session entities available: {initial_entities}")

            merged_entities = fresh_entities.copy()

            if is_pronoun_query and not fresh_entities.get("customer_name"):
                if initial_entities.get("customer_name"):
                    merged_entities["customer_name"] = initial_entities.get("customer_name")
                    logger.info(f"🔁 Resolved pronoun to session customer: {merged_entities['customer_name']}")
                elif initial_entities.get("item_name"):
                    merged_entities["item_name"] = initial_entities.get("item_name")
                    logger.info(f"🔁 Resolved pronoun to session item: {merged_entities['item_name']}")

            for key, value in initial_entities.items():
                if key.startswith('_'):
                    continue
                if key not in merged_entities or not merged_entities.get(key):
                    merged_entities[key] = value
                    logger.info(f"Filled gap from session: {key}={value}")

            for key, value in initial_entities.items():
                if key.startswith('_') and key not in merged_entities:
                    merged_entities[key] = value

            rule_entities = merged_entities
            logger.info(f"Merged entities: {rule_entities}")
        else:
            rule_entities = fresh_entities

        # ── Step 5: Fuzzy correction ─────────────────────────────────────────
        raw_item = rule_entities.get("item_name")
        if raw_item:
            corrected_item = self._correct_item_typo(raw_item)
            if corrected_item != raw_item:
                rule_entities["item_name"] = corrected_item
                rule_entities["_item_corrected_from"] = raw_item

        raw_customer = rule_entities.get("customer_name")
        if raw_customer:
            corrected_customer = self._correct_customer_typo(raw_customer)
            if corrected_customer != raw_customer:
                rule_entities["customer_name"] = corrected_customer
                rule_entities["_customer_corrected_from"] = raw_customer

        rule_entities["_original_query"] = user_message

        # ── Step 6: Return if we have entities ───────────────────────────────
        if any([
            rule_entities.get("item_name"),
            rule_entities.get("customer_name"),
            rule_entities.get("warehouse"),
            rule_entities.get("quantity"),
            rule_entities.get("detail_mode"),
        ]):
            logger.info(f"✅ Entities detected: {rule_entities}")
            await cache_service.set_simple_async(cache_key, rule_entities, ttl=300)
            return rule_entities

        # ── Step 7: Skip AI for generic queries ──────────────────────────────
        if self._should_skip_ai(user_message):
            logger.info("Skipping AI entity extraction — generic query")
            await cache_service.set_simple_async(cache_key, rule_entities, ttl=60)
            return rule_entities

        # ── Step 8: AI fallback for complex queries ──────────────────────────
        try:
            prompt = self.prompt_manager.get_entity_prompt(user_message)
            response = await self.llm.generate_async(prompt, max_tokens=150)

            json_text = self._extract_json(response)
            if not json_text:
                raise ValueError("No JSON found in AI response")

            entities = json.loads(json_text)

            structured = {
                "item_name": entities.get("item_name"),
                "customer_name": entities.get("customer_name"),
                "quantity": entities.get("quantity"),
                "warehouse": entities.get("warehouse"),
                "date": entities.get("date"),
                "detail_mode": entities.get("detail_mode", False),
            }

            if structured.get("item_name"):
                corrected = self._correct_item_typo(structured["item_name"])
                if corrected != structured["item_name"]:
                    rule_entities["_item_corrected_from"] = structured["item_name"]
                structured["item_name"] = corrected

            if structured.get("customer_name"):
                # Apply noise stripping to AI-extracted customer names too
                structured["customer_name"] = clean_customer_name(structured["customer_name"])
                corrected = self._correct_customer_typo(structured["customer_name"])
                if corrected != structured["customer_name"]:
                    rule_entities["_customer_corrected_from"] = structured["customer_name"]
                structured["customer_name"] = corrected

            for key, value in structured.items():
                if value is not None:
                    rule_entities[key] = value

            logger.info(f"Entities detected by AI: {structured}")
            logger.info(f"Final merged entities: {rule_entities}")

            await cache_service.set_simple_async(cache_key, rule_entities, ttl=300)
            return rule_entities

        except Exception as e:
            logger.warning(f"AI entity extraction failed, using rules. Error: {e}")
            await cache_service.set_simple_async(cache_key, rule_entities, ttl=60)
            return rule_entities

    # -------------------------------------------------
    # SAFE JSON EXTRACTION
    # -------------------------------------------------
    @staticmethod
    def _extract_json(text: str) -> str | None:
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        return match.group() if match else None

    # -------------------------------------------------
    # BATCH EXTRACTION
    # -------------------------------------------------
    async def extract_batch(self, messages: list[str]) -> list[dict]:
        """Extract entities from multiple messages in parallel."""
        tasks = [self.extract_async(msg) for msg in messages]
        return await asyncio.gather(*tasks)


# Singleton instance
entity_extractor = EntityExtractor()