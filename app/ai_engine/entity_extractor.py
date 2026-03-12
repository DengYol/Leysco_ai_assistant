import logging
import json
import re
from app.services.llm_service import LLMService
from app.ai_engine.prompt_manager import PromptManager
import difflib

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
    "takii", "takii logo", "rmst0512",  # Added Takii products
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
}

# Words that indicate seasonal queries - NEW
SEASONAL_INDICATORS = {
    "seasonal", "what to plant", "best for this season", "what grows in",
    "planting guide", "seasonal picks", "this month", "current month",
    "in season", "spring", "summer", "fall", "autumn", "winter",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december"
}

# Month mapping
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]


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


class EntityExtractor:
    """
    Smart Hybrid Entity Extraction Engine.
    Rule-first for speed, AI fallback for intelligence.
    """

    def __init__(self):
        self.llm = LLMService()
        self.prompt_manager = PromptManager()

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
    # FUZZY CUSTOMER CORRECTION
    # -------------------------------------------------
    def _correct_customer_typo(self, name: str) -> str:
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
    # CUSTOMER NAME DETECTION HELPERS
    # -------------------------------------------------
    def _looks_like_company(self, text: str) -> bool:
        """Check if text looks like a company/customer name."""
        if not text or len(text) < 3:
            return False

        text_lower = text.lower()

        # Check for business suffixes
        for suffix in CUSTOMER_SUFFIX_WORDS:
            if suffix in text_lower:
                return True

        # Check for title case pattern (multiple capitalized words)
        original_words = text.split()
        capitalized_count = sum(1 for w in original_words if w and w[0].isupper())
        if len(original_words) >= 2 and capitalized_count >= len(original_words) - 1:
            # Exclude if it's clearly a product
            for product in PRODUCT_INDICATORS:
                if product in text_lower:
                    return False
            return True

        # Check for common company name patterns
        company_patterns = [
            r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$',
            r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Ltd|Limited|Inc|Corp|LLC|Co)$',
            r'^(?:The\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Company|Corporation)$',
            r'^[A-Z]{2,}(?:\s+[A-Z]{2,})*$',
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

        # Check for product indicators
        for product in PRODUCT_INDICATORS:
            if product in text_lower:
                return True

        # Single word, lowercase, common product pattern
        words = text_lower.split()
        if len(words) == 1 and not words[0][0].isupper():
            return True

        return False

    # -------------------------------------------------
    # Check if this is an informational query
    # -------------------------------------------------
    def _is_info_query(self, text: str) -> bool:
        """Check if this is an informational query (tell me about X)"""
        text_lower = text.lower()
        
        for indicator in INFO_QUERY_INDICATORS:
            if indicator in text_lower:
                return True
        
        # Check for product name alone with "about"
        if "about" in text_lower:
            words = text_lower.split()
            for i, word in enumerate(words):
                if word == "about" and i + 1 < len(words):
                    potential_product = words[i + 1]
                    if potential_product in PRODUCT_INDICATORS:
                        return True
        
        return False

    # -------------------------------------------------
    # Check if this is a forecast/demand query
    # -------------------------------------------------
    def _is_forecast_query(self, text: str) -> bool:
        """Check if this is a forecast/demand prediction query"""
        text_lower = text.lower()
        
        # Don't treat seasonal queries as forecast
        if self._is_seasonal_query(text_lower):
            return False
            
        for indicator in FORECAST_INDICATORS:
            if indicator in text_lower:
                return True
        
        # Check for product + forecast patterns
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

    # -------------------------------------------------
    # NEW: Check if this is a seasonal query
    # -------------------------------------------------
    def _is_seasonal_query(self, text: str) -> bool:
        """Check if this is a seasonal recommendation query"""
        text_lower = text.lower()
        
        for indicator in SEASONAL_INDICATORS:
            if indicator in text_lower:
                return True
        
        return False

    # -------------------------------------------------
    # NEW: Extract month from seasonal query
    # -------------------------------------------------
    def _extract_month(self, text: str) -> str | None:
        """Extract month from seasonal query"""
        text_lower = text.lower()
        
        for month in MONTHS:
            if month in text_lower:
                logger.info(f"Detected month: {month}")
                return month
        
        return None

    # -------------------------------------------------
    # Check if this is a competitor pricing query
    # -------------------------------------------------
    def _is_competitor_pricing_query(self, text: str) -> bool:
        """Check if this is a competitor pricing query"""
        text_lower = text.lower()
        
        for indicator in COMPETITOR_PRICING_INDICATORS:
            if indicator in text_lower:
                return True
        
        return False

    # -------------------------------------------------
    # Check if this is a recommendation/cross-sell query
    # -------------------------------------------------
    def _is_recommendation_query(self, text: str) -> bool:
        """Check if this is a recommendation/cross-sell query"""
        text_lower = text.lower()
        
        for indicator in RECOMMENDATION_INDICATORS:
            if indicator in text_lower:
                return True
        
        return False

    # -------------------------------------------------
    # FIXED WAREHOUSE DETECTION - Won't extract from "lowest"
    # -------------------------------------------------
    def _extract_warehouse(self, text: str) -> str | None:
        """Extract warehouse name with improved patterns."""
        text_lower = text.lower()
        
        # FIRST: Check if this is a competitor pricing query - if so, be very conservative
        if self._is_competitor_pricing_query(text_lower):
            # Only look for warehouse if there's explicit location mention with "in" or "at"
            location_match = re.search(r'(?:in|at)\s+([a-zA-Z]+(?:[\s-][a-zA-Z]+)?)\s*$', text_lower)
            if location_match:
                candidate = location_match.group(1).strip()
                # Check if it's a known warehouse location
                if candidate in ["nairobi", "mombasa", "kisumu", "eldoret"]:
                    logger.info(f"Warehouse from competitor query: '{candidate}'")
                    return candidate
            return None
        
        # For non-competitor queries, use the regular patterns
        cleaned_for_warehouse = re.sub(
            r'\b(show|list|get|find|tell|me|please|can|you|what|where|how|which)\b',
            '',
            text_lower
        )

        # Pattern 1: "in X warehouse", "at X warehouse", "from X warehouse"
        pattern1 = r'(?:in|at|from)\s+([a-zA-Z0-9]+(?:\s+[a-zA-Z0-9]+)?)\s+(?:warehouse|store|branch|depot)'
        match = re.search(pattern1, cleaned_for_warehouse)
        if match:
            candidate = match.group(1).strip()
            words = candidate.split()
            if all(w not in WAREHOUSE_STOP_WORDS for w in words):
                logger.info(f"Warehouse pattern1: '{candidate}'")
                return candidate

        # Pattern 2: "X warehouse"
        pattern2 = r'([a-zA-Z0-9]+)\s+(?:warehouse|store|branch|depot)(?:\s|$)'
        match = re.search(pattern2, cleaned_for_warehouse)
        if match:
            candidate = match.group(1).strip()
            if candidate not in WAREHOUSE_STOP_WORDS:
                logger.info(f"Warehouse pattern2: '{candidate}'")
                return candidate

        # Pattern 3: "warehouse X"
        pattern3 = r'(?:warehouse|store|branch|depot)\s+([a-zA-Z0-9]+)'
        match = re.search(pattern3, cleaned_for_warehouse)
        if match:
            candidate = match.group(1).strip()
            if candidate not in WAREHOUSE_STOP_WORDS:
                logger.info(f"Warehouse pattern3: '{candidate}'")
                return candidate

        # Pattern 4: Common warehouse names
        for warehouse in ["main", "nairobi", "mombasa", "kisumu", "eldoret",
                          "central", "north", "south", "east", "west",
                          "dispatch", "shipping", "receiving", "quarantine"]:
            if warehouse in cleaned_for_warehouse:
                # Don't extract "west" if it's part of "lowest"
                if warehouse == "west" and "lowest" in text_lower:
                    continue
                logger.info(f"Warehouse pattern4: '{warehouse}'")
                return warehouse

        return None

    # -------------------------------------------------
    # RULE-BASED EXTRACTION
    # -------------------------------------------------
    def _rule_based_entities(self, text: str) -> dict:
        text_lower = text.lower()
        original_text = text

        # Check query types
        is_info = self._is_info_query(text)
        is_forecast = self._is_forecast_query(text)
        is_competitor_pricing = self._is_competitor_pricing_query(text)
        is_recommendation = self._is_recommendation_query(text)
        is_seasonal = self._is_seasonal_query(text)
        
        # Extract month for seasonal queries
        month = None
        if is_seasonal:
            month = self._extract_month(text)
            logger.info(f"Seasonal query detected with month: {month}")
        
        # Specific flags for different competitor query types
        is_best_price = any(phrase in text_lower for phrase in [
            "best price", "cheapest", "lowest price", "who sells", 
            "where to buy", "best deal", "who has the best"
        ])
        
        is_compare = any(phrase in text_lower for phrase in [
            "compare", "comparison", "vs", "versus", "verses"
        ])
        
        is_market_intel = any(phrase in text_lower for phrase in [
            "market intelligence", "market analysis", "price trends",
            "market insights"
        ])
        
        is_price_alert = any(phrase in text_lower for phrase in [
            "price alert", "notify when", "alert me when", "track price"
        ])

        # Quantity - skip setting quantity for seasonal queries
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

        cleaned_text = re.sub(r"\b\d+\b", "", text_lower)
        for word in NUMBER_WORDS.keys():
            cleaned_text = re.sub(rf"\b{word}\b", "", cleaned_text)
        COMMAND_VERBS = r"\b(show|list|get|find|search|display|tell|give|look|create|make|generate)\b"
        cleaned_text = re.sub(COMMAND_VERBS, "", cleaned_text)
        cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

        # Date
        date_match = re.search(
            r"\b(today|tomorrow|yesterday|\d{4}-\d{2}-\d{2})\b",
            text_lower,
        )

        # For seasonal queries, use month as date if available
        if is_seasonal and month and not date_match:
            # Create a proper class with group method that accepts parameters
            class SimpleMatch:
                def group(self, idx=0):
                    return month
                def __getitem__(self, idx):
                    return month
            date_match = SimpleMatch()
            logger.info(f"Using month '{month}' as date for seasonal query")

        # Detail mode
        detail_mode = bool(
            re.search(r"\b(detail|details|spec|specs|information|info|about)\b", text_lower)
        )

        # Warehouse - use the fixed method
        warehouse = self._extract_warehouse(text)

        # ── Customer name detection ───────────────────────────────────────
        customer_name = None

        cleaned_for_customer = cleaned_text

        recommendation_patterns = [
            r'\bto buy\s+[a-zA-Z0-9\-\s]+$',
            r'\bfor buying\s+[a-zA-Z0-9\-\s]+$',
            r'\bwho buy\s+[a-zA-Z0-9\-\s]+$',
            r'\bwho would buy\s+[a-zA-Z0-9\-\s]+$',
            r'\bthat buy\s+[a-zA-Z0-9\-\s]+$',
            r'\bwho purchase\s+[a-zA-Z0-9\-\s]+$',
        ]

        for pattern in recommendation_patterns:
            cleaned_for_customer = re.sub(pattern, '', cleaned_for_customer)

        customer_patterns = [
            r"(?:customer|client|company)\s+details\s+for\s+([a-zA-Z0-9\s&\-.]+?)(?:\s+please|\?|$)",
            r"details?\s+(?:for|about|of|on)\s+([a-zA-Z0-9\s&\-.]+?)(?:\s+please|\?|$)",
            r"(?:tell|show|get|find|give)\s+me\s+(?:details?|info)\s+(?:for|about|on)\s+([a-zA-Z0-9\s&\-.]+?)(?:\s+please|\?|$)",
            r"(?:quotation|quote)\s+for\s+([a-zA-Z0-9\s&\-.]+?)\s+with",
            r"(?:outstanding|pending|open|undelivered)?\s*deliver(?:y|ies)\s+(?:for|to|from)\s+([a-zA-Z0-9\s&\-.]+)",
            r"(?:orders?|invoices?|quotations?|sales)\s+(?:for|to|from)\s+([a-zA-Z0-9\s&\-.]+)",
            r"(?:customer|client|buyer)\s+([a-zA-Z0-9\s&\-.]+)",
            r"(?:price|cost|stock|availability)\s+(?:of|for)\s+[a-zA-Z0-9\s&\-.]+?\s+for\s+([a-zA-Z0-9\s&\-.]+)",
        ]

        for pattern in customer_patterns:
            match = re.search(pattern, cleaned_for_customer, re.IGNORECASE)
            if match:
                customer_name = match.group(1).strip()
                break

        if customer_name:
            customer_name = re.sub(
                r"\b(today|tomorrow|yesterday|warehouse|store|branch|details?|info|information|please|thanks)\b.*$",
                "",
                customer_name,
                flags=re.IGNORECASE
            ).strip()
            logger.info(f"Extracted customer name: '{customer_name}'")

        # ── Item name detection ───────────────────────────────
        item_name = None
        items_list = []  # For multi-item queries like "compare X and Y"

        # SPECIAL HANDLING FOR SEASONAL QUERIES - NEW
        if is_seasonal:
            logger.info(f"Seasonal query detected, not extracting item name")
            # Don't set item_name for seasonal queries
            item_name = None

        # SPECIAL HANDLING FOR CROSS-SELL / RECOMMENDATION QUERIES
        elif is_recommendation and not item_name:
            logger.info(f"Cross-sell/recommendation query detected, extracting item name")
            
            # Pattern for "customers who bought X also bought Y"
            patterns = [
                r'(?:customers who bought|customers who buy|people who bought|who bougth|who bought)\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\s+also|\s+and|\s+buy|\?|$)',
                r'also bought with\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'frequently bought with\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'what else do customers buy with\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'commonly bought with\s+([a-zA-Z0-9\-\(\)\s]+)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip()
                    # Clean up
                    candidate = re.sub(r'\s+(also|and|with|buys|buy|what|\?|by)$', '', candidate).strip()
                    
                    if candidate and len(candidate) > 1:
                        # Check if this looks like a product (use PRODUCT_INDICATORS)
                        # First check exact match in product indicators
                        found_product = None
                        for prod in PRODUCT_INDICATORS:
                            if prod in candidate.lower():
                                found_product = prod
                                break
                        
                        if found_product:
                            item_name = found_product
                            logger.info(f"Extracted product from cross-sell: '{item_name}'")
                        else:
                            # Use the candidate as is
                            item_name = candidate
                            logger.info(f"Extracted potential product from cross-sell: '{item_name}'")
                        break

        # Handle multi-item comparison queries
        if is_compare and "and" in text_lower and not item_name:
            # Try to extract multiple items
            items_pattern = r'(?:compare|comparison).*?([a-zA-Z0-9\-\(\)\s]+?)\s+and\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\?|$)'
            match = re.search(items_pattern, text_lower, re.IGNORECASE)
            if match:
                item1 = match.group(1).strip()
                item2 = match.group(2).strip()
                # Clean each item
                for itm in [item1, item2]:
                    cleaned = re.sub(r'\b(price|cost|for|of|the)\b', '', itm).strip()
                    if cleaned and len(cleaned) > 1:
                        items_list.append(cleaned)
                if items_list:
                    item_name = items_list[0]  # Use first as primary
                    logger.info(f"Extracted multiple items for comparison: {items_list}")

        # Special handling for best price / who sells queries
        if is_best_price and not item_name:
            logger.info(f"Best price query detected, extracting item name")
            
            # Pattern for "who sells X at the lowest price"
            who_sells_patterns = [
                r'who sells\s+([a-zA-Z0-9\-\(\)\s]+?)\s+(?:at|for|with)',
                r'who sells\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\?|$)',
                r'best price for\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'cheapest\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'lowest price (?:for|of)\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'where to buy\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'where can i buy\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'who has the best price on\s+([a-zA-Z0-9\-\(\)\s]+)',
                r'who sells.*cheapest\s+([a-zA-Z0-9\-\(\)\s]+)',
            ]
            
            for pattern in who_sells_patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip()
                    # Clean up common words
                    candidate = re.sub(
                        r'\b(at|the|and|or|for|with|price|cost|cheap|best|lowest|who|sells|where|can|i|buy|get|find)\b',
                        '',
                        candidate,
                        flags=re.IGNORECASE
                    ).strip()
                    
                    if candidate and len(candidate) > 1:
                        item_name = candidate
                        logger.info(f"Extracted item from who-sells query: '{item_name}'")
                        break

        # Special handling for price alert queries
        if is_price_alert and not item_name:
            logger.info(f"Price alert query detected, extracting item name")
            alert_patterns = [
                r'alert me when\s+([a-zA-Z0-9\-\(\)\s]+?)\s+price',
                r'notify when\s+([a-zA-Z0-9\-\(\)\s]+?)\s+price',
                r'track\s+([a-zA-Z0-9\-\(\)\s]+?)\s+price',
            ]
            for pattern in alert_patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip()
                    if candidate and len(candidate) > 1:
                        item_name = candidate
                        logger.info(f"Extracted item from price alert: '{item_name}'")
                        break

        # For forecast queries, ALWAYS try to extract the item name
        if is_forecast and not item_name:
            logger.info(f"Forecast query detected, extracting item name")
            
            # Pattern for forecast queries: "forecast demand for X"
            forecast_item_patterns = [
                r'(?:forecast|predict|demand)\s+(?:for|of)\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\?|$|for)',
                r'how many\s+([a-zA-Z0-9\-\(\)\s]+?)\s+will',
                r'how much\s+([a-zA-Z0-9\-\(\)\s]+?)\s+will',
                r'demand\s+(?:for|of)\s+([a-zA-Z0-9\-\(\)\s]+)',
            ]
            
            for pattern in forecast_item_patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip()
                    # Clean up common words
                    candidate = re.sub(
                        r'\b(we|will|sell|be|in|the|next|month|year|days)\b',
                        '',
                        candidate,
                        flags=re.IGNORECASE
                    ).strip()
                    
                    if candidate and len(candidate) > 1:
                        item_name = candidate
                        logger.info(f"Extracted forecast item: '{item_name}'")
                        break
        
        # If this is an informational query, don't extract item name (handled by knowledge base)
        elif is_info:
            logger.info(f"Info query detected, skipping item extraction")
            item_name = None
        
        # Normal item extraction for non-forecast, non-info, non-competitor, non-recommendation, non-seasonal queries
        if not item_name and not is_forecast and not is_info and not is_competitor_pricing and not is_recommendation and not is_seasonal:
            pure_customer_query = bool(re.search(
                r"(?:customer|client|company).*?(?:details|info|about).*?([A-Z][a-zA-Z0-9\s&\-.]+)",
                original_text, re.IGNORECASE
            ))

            if not pure_customer_query:
                item_patterns = [
                    r"(?:which|what)\s+warehouse.*?(?:has|have|stock|find)\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\?|$)",
                    r"where\s+(?:can\s+i\s+)?(?:find|get|buy)\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\?|$)",
                    r"(?:details|specs|info|information)\s+(?:for|about)\s+([a-zA-Z0-9\-\(\)\s]+)",
                    r"(?:price|cost|stock|availability)\s+(?:of|for)\s+([a-zA-Z0-9\-\(\)]+(?:\s+[a-zA-Z0-9\-\(\)]+)*)\s+for\s+[a-zA-Z]",
                    r"(?:price|cost)\s+(?:of|for)\s+([a-zA-Z0-9\-\(\)\s]+)",
                    r"(?:check|buy|sell)\s+([a-zA-Z0-9\-\(\)\s]+)",
                    r"([a-zA-Z0-9\-\(\)]{2}[a-zA-Z0-9\-\(\)\s]+?)\s+(?:price|cost|availability|stock)",
                ]

                for pattern in item_patterns:
                    match = re.search(pattern, cleaned_text, re.IGNORECASE)
                    if match:
                        candidate = match.group(1).strip()

                        candidate_words = set(candidate.lower().split())
                        if candidate_words & CUSTOMER_SUFFIX_WORDS or self._looks_like_company(candidate):
                            logger.info(f"Candidate '{candidate}' looks like company — treating as customer")
                            if not customer_name:
                                customer_name = candidate
                            continue

                        if self._is_product_name(candidate):
                            item_name = candidate
                            break

                        if not item_name:
                            item_name = candidate
                            break

        # Clean generic words from item name
        if item_name:
            item_name = re.sub(
                r"\b(item|product|details?|specs?|info|information|of|for|to|from|me|will|sell|demand|forecast|price|cost|cheap|best|lowest|who|sells|where|buy|also|bought|with)\b",
                "",
                item_name,
                flags=re.IGNORECASE
            ).strip()

            if self._looks_like_company(item_name) and not self._is_product_name(item_name):
                logger.info(f"Item '{item_name}' looks like company — moving to customer_name")
                if not customer_name:
                    customer_name = item_name
                item_name = None

        # Strip customer name out of item when both came from same phrase
        if item_name and customer_name:
            cust_in_item = customer_name.lower().strip()
            item_lower   = item_name.lower().strip()
            if cust_in_item in item_lower:
                item_name = item_lower.replace(cust_in_item, "").strip()
                logger.info(f"Stripped customer from item: result='{item_name}'")

        # Fallback: detail mode active but nothing matched
        if detail_mode and not item_name and not customer_name and not is_info:
            words = cleaned_text.split()
            if len(words) >= 2:
                potential_name = " ".join(words[-2:])
                if self._looks_like_company(potential_name):
                    customer_name = potential_name
                else:
                    item_name = potential_name

        # Smart conflict resolution
        if detail_mode and customer_name:
            logger.info(f"Detail mode + customer_name='{customer_name}' — clearing item_name")
            item_name = None

        # Special handling for "for [Company]" pattern
        for_company_match = re.search(r'for\s+([A-Z][a-zA-Z0-9\s&\-.]+)$', original_text)
        if for_company_match and not customer_name:
            potential_customer = for_company_match.group(1).strip()
            if self._looks_like_company(potential_customer):
                customer_name = potential_customer
                logger.info(f"Extracted customer from trailing 'for': '{customer_name}'")

        # For forecast queries, ensure quantity is set to default if not provided
        if is_forecast and not quantity:
            quantity = 30  # Default forecast period in days
            logger.info(f"Forecast query: setting default quantity=30")

        # Safely extract date value
        date_value = None
        if date_match:
            if hasattr(date_match, 'group'):
                try:
                    date_value = date_match.group(1)
                except (IndexError, TypeError):
                    # If group(1) fails, try group(0) or convert to string
                    try:
                        date_value = date_match.group(0)
                    except:
                        date_value = str(date_match)
            elif isinstance(date_match, str):
                date_value = date_match
            else:
                date_value = str(date_match)

        # Store items_list in a special field for multi-item queries
        result = {
            "item_name":     item_name,
            "customer_name": customer_name,
            "quantity":      quantity,
            "warehouse":     warehouse,
            "date":          date_value,
            "detail_mode":   detail_mode,
        }
        
        # Add items_list for multi-item queries
        if items_list:
            result["items_list"] = items_list
            
        return result

    # -------------------------------------------------
    # MAIN EXTRACTION FLOW
    # -------------------------------------------------
    def extract(self, user_message: str, initial_entities: dict = None) -> dict:
        """
        Extract entities from user message.
        
        Args:
            user_message: The user's input text
            initial_entities: Optional entities already extracted (e.g., from Swahili support)
        
        Returns:
            dict: Extracted entities
        """
        # Start with initial entities if provided (from Swahili support)
        if initial_entities:
            logger.info(f"Starting with initial entities: {initial_entities}")
            rule_entities = initial_entities.copy()
        else:
            rule_entities = self._rule_based_entities(user_message)
        
        # Add original query to entities for override logic
        rule_entities["_original_query"] = user_message

        # If rules found something useful, return immediately — no LLM call
        if any([
            rule_entities.get("item_name"),
            rule_entities.get("customer_name"),
            rule_entities.get("warehouse"),
            rule_entities.get("quantity"),
            rule_entities.get("detail_mode"),
        ]):
            logger.info(f"Entities detected by rules: {rule_entities}")
            return rule_entities

        # Skip AI for short/generic queries — saves Groq tokens
        if self._should_skip_ai(user_message):
            logger.info("Skipping AI entity extraction — generic query")
            return rule_entities

        # AI fallback for complex/ambiguous queries
        try:
            # FIXED: Removed the context argument - only pass user_message
            prompt = self.prompt_manager.get_entity_prompt(user_message)
            response = self.llm.generate(prompt, max_tokens=150)

            json_text = self._extract_json(response)
            if not json_text:
                raise ValueError("No JSON found in AI response")

            entities = json.loads(json_text)

            structured = {
                "item_name":     entities.get("item_name"),
                "customer_name": entities.get("customer_name"),
                "quantity":      entities.get("quantity"),
                "warehouse":     entities.get("warehouse"),
                "date":          entities.get("date"),
                "detail_mode":   entities.get("detail_mode", False),
            }

            # Merge with rule entities (preserve any rule-extracted values)
            for key, value in structured.items():
                if value is not None:
                    rule_entities[key] = value

            logger.info(f"Entities detected by AI: {structured}")
            logger.info(f"Final merged entities: {rule_entities}")
            return rule_entities

        except Exception as e:
            logger.warning(f"AI entity extraction failed, using rules. Error: {e}")
            return rule_entities

    # -------------------------------------------------
    # SAFE JSON EXTRACTION
    # -------------------------------------------------
    @staticmethod
    def _extract_json(text: str) -> str | None:
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        return match.group() if match else None

    # -------------------------------------------------
    # LOAD CUSTOMERS FOR FUZZY MATCHING
    # -------------------------------------------------
    def _load_customers(self) -> list:
        """
        Load customer names for fuzzy matching.
        This would typically come from the API.
        """
        # This is a placeholder - implement actual customer loading
        return []