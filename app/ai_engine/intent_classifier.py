"""
intent_classifier.py - Optimized with async support, caching, and fast-path
Enhanced with natural language understanding for conversational queries
"""

import json
import logging
import re
import asyncio
from typing import Optional, Dict, Any, Tuple
from functools import lru_cache
from app.services.llm_service import LLMService
from app.ai_engine.prompt_manager import PromptManager, VALID_INTENTS
from app.ai_engine.swahili_support import SwahiliSupport
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)

_VALID_INTENTS_SET = set(VALID_INTENTS)

# ---------------------------------------------------------------------------
# CONFIDENCE SCORING CONFIG
# ---------------------------------------------------------------------------

_CONF = {
    "fast_path":      0.95,
    "swahili":        0.90,
    "ai_clean":       0.80,
    "ai_override":    0.70,
    "rule_fallback":  0.65,
    "unknown":        0.30,
}

CLARIFY_THRESHOLD = 0.50

# ---------------------------------------------------------------------------
# SHARED WORD SETS
# ---------------------------------------------------------------------------

_ACKNOWLEDGEMENT_WORDS = {
    "okay", "ok", "alright", "sure", "got it", "i see", "understood",
    "noted", "cool", "great", "nice", "sounds good", "makes sense",
    "no problem", "no worries", "fine", "yep", "yup", "yeah", "yes",
    "nope", "no", "k", "kk", "hmm", "hm", "interesting", "wow",
    "oh", "ah", "lol", "haha", "good", "nice one", "perfect",
}

_FAREWELL_WORDS = {
    "bye", "goodbye", "see you", "see ya", "later", "talk later",
    "good night", "take care", "ttyl", "cya",
}

_CROSS_SELL_PHRASES = {
    "customers who bought", "also bought", "frequently bought",
    "people also buy", "others bought", "similar customers bought",
    "what else do customers buy with", "commonly bought with",
    "bundle with", "frequently purchased together", "who bougth",
    "who bought", "customers who buy", "people who buy",
    "customers who buys", "people who buys", "who buys"
}

_SELL_OUT_PHRASES = {
    "sell out", "sell to", "who to sell", "target customers",
    "who would buy", "who buys", "potential customers",
    "sell this to", "market to", "pitch to", "offer to",
    "recommend to customers", "suggest to customers",
    "which customer", "which customers", "customers that buy",
    "customer that buys", "customer segment for", "who purchases",
}

# Top selling phrases
TOP_SELLING_PHRASES = {
    "top selling", "best selling", "most popular", "top items", 
    "bestsellers", "best sellers", "most sold", "highest selling",
    "top 5", "top 10", "top 15", "top 20", "top products",
    "what sells most", "popular items", "fast moving", "fastest selling",
    "top performing", "best performers", "hot items", "trending products",
    "most purchased", "frequently bought", "high volume", "best movers",
    "what's popular", "what are people buying", "customers are buying",
    "selling like hotcakes", "flying off the shelves"
}

# Slow moving phrases
SLOW_MOVING_PHRASES = {
    "slow moving", "slow selling", "least popular", "worst selling",
    "lowest selling", "slowest selling", "dead stock", "obsolete",
    "not selling", "poorly selling", "slow items", "slow products",
    "dormant stock", "stagnant", "low turnover", "inactive items",
    "non moving", "non-moving", "excess stock", "surplus",
    "gathering dust", "not moving", "sitting on shelves", "hard to sell"
}

# Sales analytics phrases
SALES_ANALYTICS_PHRASES = {
    "sales analytics", "sales analysis", "sales report", "sales data",
    "sales overview", "sales summary", "sales performance", "sales metrics",
    "sales statistics", "sales insights", "sales trends", "sales dashboard",
    "show sales", "view sales", "sales figures", "revenue report",
    "revenue analytics", "sales breakdown", "sales by period", "sales summary",
    "sales performance report", "monthly sales", "weekly sales", "daily sales",
    "yearly sales", "quarterly sales", "sales by category", "sales by product",
    "sales history", "sales record", "transaction report", "sales totals",
    "total sales", "gross sales", "net sales", "sales volume"
}

# Natural language variations for price queries
PRICE_VARIATIONS = [
    r"\bhow much\b", 
    r"\bwhat'?s?\s*the\s*price\b", 
    r"\bwhat is\s*the\s*price\b",
    r"\bcost\b",
    r"\bpricing\b", 
    r"\bwhat'?s?\s*the\s*cost\b",
    r"\bwhat does.*cost\b",
    r"\bhow expensive\b", 
    r"\bhow\s*much\s*shillings\b",
    r"\bhow\s*much\s*money\b",
    r"\bbiashara\b", 
    r"\bthamani\b", 
    r"\bugharama\b", 
    r"\bpesa ngapi\b",
    r"\bni bei gani\b", 
    r"\bbei yake\b", 
    r"\bgharama yake\b",
    r"\bhow much is\b", 
    r"\bwhat'?s?\s*the\s*cost of\b",
    r"\bcan you tell me.*price\b", 
    r"\bi'?d like\s*the\s*price\b",
    r"\bi want\s*the\s*price\b"
]

# Natural language variations for stock queries
STOCK_VARIATIONS = [
    r"\b(?:stock|inventory|supply|availability|hisa)\b",
    r"\bhow many\b.*\bin stock\b", 
    r"\bdo you have\b",
    r"\bis there\b", 
    r"\bare there\b", 
    r"\bwhat'?s?\s*available\b",
    r"\bquantity on hand\b", 
    r"\blevels?\b", 
    r"\bupatikanaji\b",
    r"\bhow many left\b", 
    r"\bwhat'?s?\s*in stock\b"
]

# Natural language variations for customer queries
CUSTOMER_VARIATIONS = [
    r"\bcustomer\s*(?:details|info|information|profile)\b",
    r"\bwho is\b", 
    r"\btell me about\b.*\bcustomer\b",
    r"\bwhat do we know about\b", 
    r"\bmteja\b.*\bmaelezo\b",
    r"\btaarifa za mteja\b", 
    r"\bprofile ya mteja\b",
    r"\bshow me.*customer\b", 
    r"\bget.*customer\s*(?:details|info)\b"
]

# Natural language variations for order queries
ORDER_VARIATIONS = [
    r"\border(?:s)?\b", 
    r"\bpurchase(?:s)?\b", 
    r"\btransaction(?:s)?\b",
    r"\bwhat did (?:they|the customer) buy\b", 
    r"\bwhat has (?:been|been) ordered\b",
    r"\boda\b", 
    r"\bununuzi\b", 
    r"\bhistoria ya ununuzi\b",
    r"\bwhat (?:has|did).*buy\b", 
    r"\b(?:show|list|view).*orders\b"
]

_COMMON_PRODUCTS = [
    "cabbage", "tomato", "maize", "pepper", "cauliflower", "onion",
    "vegimax", "easeed", "tosheka", "kh500", "mh401", "snowball",
    "yolo wonder", "seed", "seeds", "fertilizer", "pesticide"
]

# Enhanced Fast-path patterns for natural language understanding
FAST_PATH_PATTERNS = [
    # =========================================================
    # CRITICAL: Quotation creation patterns (HIGHEST PRIORITY)
    # =========================================================
    (r'^create\s+(?:a\s+)?quotation\s+(?:for\s+)?([A-Za-z0-9\s]+)(?:\s+with\s+|\s+containing\s+|\s+including\s+)(.+)', "CREATE_QUOTATION"),
    (r'^make\s+(?:a\s+)?quotation\s+(?:for\s+)?([A-Za-z0-9\s]+)(?:\s+with\s+|\s+containing\s+)(.+)', "CREATE_QUOTATION"),
    (r'^new\s+quotation\s+(?:for\s+)?([A-Za-z0-9\s]+)(?:\s+with\s+)(.+)', "CREATE_QUOTATION"),
    (r'^quotation\s+(?:for\s+)?([A-Za-z0-9\s]+)(?:\s+with\s+|\s+for\s+)(.+)', "CREATE_QUOTATION"),
    (r'^(?:cash sale|cash sale -)\s+([A-Za-z0-9\s]+)(?:\s+with\s+)(.+)', "CREATE_QUOTATION"),
    (r'^create\s+quotation$', "CREATE_QUOTATION"),
    (r'^make\s+quotation$', "CREATE_QUOTATION"),
    
    # =========================================================
    # Company Info (HIGH PRIORITY - BEFORE customer patterns)
    # =========================================================
    (r'^(?:tell me about|what is|about)\s+leysco\s*$', "COMPANY_INFO"),
    (r'^(?:tell me about|what is|about)\s+the\s+company\s*$', "COMPANY_INFO"),
    (r'^company\s+(?:info|information|details|profile)\s*$', "COMPANY_INFO"),
    (r'^what\s+is\s+leysco\s*$', "COMPANY_INFO"),
    (r'^who\s+is\s+leysco\s*$', "COMPANY_INFO"),
    (r'^about\s+leysco\s*$', "COMPANY_INFO"),
    
    # =========================================================
    # Top Selling & Analytics (HIGH PRIORITY)
    # =========================================================
    (r'^(?:show|get|list)\s+(?:top|best)\s+(?:selling|sellers)\s+(?:items|products)$', "GET_TOP_SELLING_ITEMS"),
    (r'^(?:top|best)\s+(\d+)\s+(?:selling|sellers)\s+(?:items|products)$', "GET_TOP_SELLING_ITEMS"),
    (r'^(?:show|get|list)\s+(?:slow|least)\s+(?:moving|selling)\s+(?:items|products)$', "GET_SLOW_MOVING_ITEMS"),
    
    # =========================================================
    # Sales Analytics & Reporting (HIGH PRIORITY)
    # =========================================================
    (r'^(?:show|get|view|display)\s+(?:sales|revenue)\s+(?:analytics|analysis|report|data|overview|summary)$', "GET_SALES_ANALYTICS"),
    (r'^(?:sales|revenue)\s+(?:analytics|analysis|report|data|overview|summary)$', "GET_SALES_ANALYTICS"),
    (r'^show\s+sales$', "GET_SALES_ANALYTICS"),
    (r'^sales\s+(?:performance|metrics|statistics|insights|trends)$', "GET_SALES_ANALYTICS"),
    (r'^(?:monthly|weekly|daily|yearly|quarterly)\s+sales$', "GET_SALES_ANALYTICS"),
    (r'^(?:what|show me)\s+(?:are\s+)?(?:my\s+)?(?:total|gross|net)\s+sales$', "GET_SALES_ANALYTICS"),
    
    # Original patterns
    (r'^(price|bei)\s+(of|ya)?\s*([a-zA-Z0-9\-\(\)\s]+)$', "GET_ITEM_PRICE"),
    (r'^(stock|hisa)\s+(level|kiwango)?\s*(for|ya)?\s*([a-zA-Z0-9\-\(\)\s]+)$', "GET_STOCK_LEVELS"),
    (r'^(show|list|onyesha|orodhesha)\s+(me)?\s*(customers|wateja)$', "GET_CUSTOMERS"),
    (r'^(show|list|onyesha|orodhesha)\s+(me)?\s*(items|bidhaa)$', "GET_ITEMS"),
    (r'^low\s+stock\s+(alert|arifa)$', "GET_LOW_STOCK_ALERTS"),
    
    # Price query patterns
    (r'^(what|whats|what\'s)\s+is\s+the\s+price\s+of\s+([a-zA-Z0-9\-\(\)\s]+)$', "GET_ITEM_PRICE"),
    (r'^(what|whats|what\'s)\s+is\s+the\s+cost\s+of\s+([a-zA-Z0-9\-\(\)\s]+)$', "GET_ITEM_PRICE"),
    (r'^how\s+much\s+is\s+([a-zA-Z0-9\-\(\)\s]+)$', "GET_ITEM_PRICE"),
    (r'^how\s+much\s+does\s+([a-zA-Z0-9\-\(\)\s]+)\s+cost$', "GET_ITEM_PRICE"),
    (r'^can\s+you\s+tell\s+me\s+the\s+price\s+of\s+([a-zA-Z0-9\-\(\)\s]+)$', "GET_ITEM_PRICE"),
    (r'^may\s+i\s+know\s+the\s+price\s+of\s+([a-zA-Z0-9\-\(\)\s]+)$', "GET_ITEM_PRICE"),
    (r'^i\'?d\s+like\s+to\s+know\s+the\s+price\s+of\s+([a-zA-Z0-9\-\(\)\s]+)$', "GET_ITEM_PRICE"),
    (r'^price\s+of\s+([a-zA-Z0-9\-\(\)\s]+)\??$', "GET_ITEM_PRICE"),
    (r'^bei\s+ya\s+([a-zA-Z0-9\-\(\)\s]+)\??$', "GET_ITEM_PRICE"),
    
    # Natural language price queries
    (r'(?:how much|what(?:\'s| is)? the (?:price|cost)|can you tell me (?:the )?price|i(?:\'d like| want) (?:the )?price|show me (?:the )?price|give me (?:the )?price).*(?:of|for|on)\s+([a-zA-Z0-9\-\(\)\s]+)$', "GET_ITEM_PRICE"),
    (r'(?:what(?:\'s| is)?|how much is)\s+([a-zA-Z0-9\-\(\)\s]+?)\s*(?:price|cost|worth|selling for|going for)$', "GET_ITEM_PRICE"),
    (r'([a-zA-Z0-9\-\(\)\s]+?)\s+(?:price|cost|bei|gharama)$', "GET_ITEM_PRICE"),
    
    # Natural language stock queries
    (r'(?:how many|what(?:\'s| is)? the (?:stock|quantity|inventory)|do you have|is there|are there).*(?:of|for|on)\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\s+in stock|\s+available)?$', "GET_STOCK_LEVELS"),
    (r'(?:stock|hisa|available).*(?:of|for|ya)\s+([a-zA-Z0-9\-\(\)\s]+)$', "GET_STOCK_LEVELS"),
    
    # Natural language customer queries (MUST include "customer" keyword - won't match "Leysco")
    (r'(?:show|get|view|tell me about).*(?:customer|client|mteja)\s+(?:details|info|information|maelezo).*(?:for|of|about|ya)\s+([A-Za-z][A-Za-z\s]+)$', "GET_CUSTOMER_DETAILS"),
    (r'(?:who is|customer info for)\s+([A-Za-z][A-Za-z\s]+)$', "GET_CUSTOMER_DETAILS"),
    
    # Natural language order queries
    (r'(?:show|list|view|what are).*(?:orders|purchases|oda).*(?:for|of|from|ya)\s+([A-Za-z][A-Za-z\s]+)$', "GET_CUSTOMER_ORDERS"),
    (r'(?:what has|what did)\s+([A-Za-z][A-Za-z\s]+?)\s+(?:bought|ordered|purchased)$', "GET_CUSTOMER_ORDERS"),
    
    # Conversational greetings
    (r'^(?:hi|hello|hey|good morning|good afternoon|good evening|howdy|sup|yo|jambo|habari|mambo|sasa)(?:\s|$)', "GREETING"),
    (r'^(?:thanks|thank you|appreciate it|nice one|good one|asante|shukran)(?:\s|$)', "THANKS"),
    
    # Help queries
    (r'^(?:help|what can you do|how do i use this|capabilities|what do you do|msaada|unaweza kufanya nini)(?:\s|\?)?$', "FAQ"),
    
    # Warehouse queries
    (r'^(?:show|list|where are).*(?:warehouses?|maghala|storage|depots?)$', "GET_WAREHOUSES"),
    (r'^(?:what|which).*(?:warehouses?|maghala).*(?:have|has|stock|hisa).*(?:for|of|ya)\s+([a-zA-Z0-9\-\(\)\s]+)$', "GET_WAREHOUSE_STOCK"),
    
    # Low stock alerts
    (r'^(?:what|which).*(?:low|critical|danger).*(?:stock|inventory|hisa|items|bidhaa).*(?:alert|alerts?|warning|arifa)$', "GET_LOW_STOCK_ALERTS"),
    (r'^(?:what\'?s|what is).*(?:low|running low|almost out)$', "GET_LOW_STOCK_ALERTS"),
]


def _result(
    intent: str,
    language: str = "en",
    confidence: float = 0.80,
    alternatives: list | None = None,
    **extra,
) -> dict:
    """Construct a classifier result dict."""
    return {
        "intent":       intent,
        "language":     language,
        "confidence":   round(confidence, 2),
        "alternatives": alternatives or [],
        **extra,
    }


class IntentClassifier:
    def __init__(self):
        self.llm = LLMService()
        self.prompt_manager = PromptManager()
        self.swahili = SwahiliSupport()
        self._fast_path_cache = {}  # Simple in-memory cache for fast-path results

    # -------------------------------------------------------------------------
    # FAST-PATH DETECTION (No LLM)
    # -------------------------------------------------------------------------
    def _try_fast_path(self, message: str) -> Optional[Tuple[str, dict]]:
        """Try to classify using fast-path patterns (no LLM call)."""
        message_lower = message.lower().strip()
        
        # Check cache first
        cache_key = f"fast_path:{message_lower}"
        if cache_key in self._fast_path_cache:
            logger.info(f"⚡ Fast-path cache hit: {message_lower}")
            return self._fast_path_cache[cache_key]
        
        # Check patterns
        for pattern, intent in FAST_PATH_PATTERNS:
            match = re.match(pattern, message_lower, re.IGNORECASE)
            if match:
                # Extract entities if present
                entities = {}
                groups = match.groups()
                
                # For quotation creation, extract customer name and items
                if intent == "CREATE_QUOTATION" and len(groups) >= 2:
                    entities["customer_name"] = groups[0].strip()
                    # Extract items from the items string
                    items_str = groups[1] if len(groups) > 1 else ""
                    # Parse items like "3 vegimax 30ml and 2 vegimax 250ml"
                    item_pattern = r'(\d+)\s+([a-zA-Z0-9\-]+)\s+(\d+(?:ml|ML|mL|kg|KG|g|G))'
                    item_matches = re.findall(item_pattern, items_str, re.IGNORECASE)
                    if item_matches:
                        entities["items"] = []
                        for qty, name, size in item_matches:
                            entities["items"].append({
                                "name": f"{name} {size}",
                                "quantity": int(qty)
                            })
                    else:
                        # Try simpler pattern
                        simple_pattern = r'(\d+)\s+([a-zA-Z0-9\-]+)'
                        simple_matches = re.findall(simple_pattern, items_str, re.IGNORECASE)
                        for qty, name in simple_matches:
                            entities["items"] = entities.get("items", [])
                            entities["items"].append({
                                "name": name,
                                "quantity": int(qty)
                            })
                
                # Extract item name (usually the last capture group)
                elif groups and not entities:
                    for i, group in enumerate(groups):
                        if group and i == len(groups) - 1 and len(group) > 1:
                            if "customer" not in pattern.lower() and "order" not in pattern.lower():
                                entities["item_name"] = group.strip()
                            else:
                                entities["customer_name"] = group.strip()
                            break
                        elif group and len(group) > 2 and group.isdigit():
                            entities["quantity"] = int(group)
                
                # Extract limit for top selling queries
                if intent == "GET_TOP_SELLING_ITEMS":
                    num_match = re.search(r'top\s+(\d+)', message_lower)
                    if num_match:
                        entities["quantity"] = int(num_match.group(1))
                
                result = (intent, entities)
                self._fast_path_cache[cache_key] = result
                logger.info(f"⚡ Fast-path matched: '{message}' → {intent}")
                return result
        
        return None

    # -------------------------------------------------------------------------
    # RULE-BASED INTENT ENGINE (Cached)
    # -------------------------------------------------------------------------
    @lru_cache(maxsize=512)
    def _rule_based_intent(self, text: str) -> str:
        """Cached rule-based intent detection with natural language understanding."""
        text = text.lower().strip()
        
        # =========================================================
        # CRITICAL: Check for QUOTATION CREATION FIRST
        # This must come before any other detection
        # =========================================================
        if 'quotation' in text or 'quote' in text:
            if any(w in text for w in ['create', 'make', 'generate', 'prepare', 'new', 'cash sale']):
                logger.info(f"📝 Quotation creation detected: {text}")
                return "CREATE_QUOTATION"
        
        # =========================================================
        # Company Info (HIGH PRIORITY - before customer)
        # =========================================================
        if 'leysco' in text and any(w in text for w in ['tell me about', 'what is', 'who is', 'about']):
            logger.info(f"🏢 Company info detected: {text}")
            return "COMPANY_INFO"
        
        if any(w in text for w in ['company info', 'company information', 'about the company', 'tell me about leysco']):
            logger.info(f"🏢 Company info detected: {text}")
            return "COMPANY_INFO"
        
        # =========================================================
        # CRITICAL: Check for TOP SELLING ITEMS (high priority)
        # =========================================================
        if any(p in text for p in TOP_SELLING_PHRASES):
            logger.info(f"📊 Rule-based top selling detected: {text}")
            return "GET_TOP_SELLING_ITEMS"
        
        # =========================================================
        # CRITICAL: Check for SALES ANALYTICS (high priority)
        # =========================================================
        if any(p in text for p in SALES_ANALYTICS_PHRASES):
            logger.info(f"📈 Rule-based sales analytics detected: {text}")
            return "GET_SALES_ANALYTICS"
        
        # =========================================================
        # Check for SLOW MOVING ITEMS
        # =========================================================
        if any(p in text for p in SLOW_MOVING_PHRASES):
            logger.info(f"📊 Rule-based slow moving detected: {text}")
            return "GET_SLOW_MOVING_ITEMS"
        
        # =========================================================
        # Check for PRICE queries
        # =========================================================
        price_patterns = [
            r'\bprice\s+of\b',
            r'\bcost\s+of\b', 
            r'\bhow\s+much\b',
            r'\bwhat\s+is\s+the\s+price\b',
            r'\bwhat\s+is\s+the\s+cost\b',
            r'\bwhat\'?s\s+the\s+price\b',
            r'\bwhat\'?s\s+the\s+cost\b',
            r'\bcan\s+you\s+tell\s+me\s+the\s+price\b',
            r'\bmay\s+i\s+know\s+the\s+price\b',
            r'\bi\'?d\s+like\s+to\s+know\s+the\s+price\b',
            r'\bbei\s+ya\b',
            r'\bgharama\s+ya\b',
            r'\bpesa\s+ngapi\b',
        ]
        
        for pattern in price_patterns:
            if re.search(pattern, text):
                if re.search(r'(?:for|kwa|ya)\s+([A-Za-z][A-Za-z\s]+)$', text):
                    return "GET_CUSTOMER_PRICE"
                return "GET_ITEM_PRICE"
        
        # Sell-out / customer segmentation queries
        if any(p in text for p in _SELL_OUT_PHRASES):
            logger.info(f"🎯 Rule-based sell-out detected: {text}")
            return "FIND_CUSTOMERS_BY_ITEM"
        
        sell_out_patterns = [
            r'^sell\s+out\s+', r'^who\s+to\s+sell\s+', r'who\s+would\s+buy\s+',
            r'who\s+buys\s+', r'which\s+customer\s+', r'which\s+customers\s+',
            r'customers\s+that\s+buy\s+', r'customers\s+who\s+buy\s+',
            r'target\s+customers\s+for\s+', r'potential\s+customers\s+for\s+',
            r'sell\s+this\s+to\s+', r'market\s+to\s+',
        ]
        for pattern in sell_out_patterns:
            if re.search(pattern, text):
                return "FIND_CUSTOMERS_BY_ITEM"

        # Greeting
        if any(w in text for w in ["hi", "hello", "hey", "greetings",
                                    "good morning", "good afternoon", "good evening",
                                    "howdy", "sup", "yo", "jambo", "habari", "mambo", "sasa"]):
            return "GREETING"

        # Thanks
        if any(w in text for w in ["thanks", "thank you", "appreciate", "cheers", "asante", "shukran"]):
            return "THANKS"

        # Small talk / acknowledgements
        stripped = text.rstrip("!?.,")
        if stripped in _ACKNOWLEDGEMENT_WORDS or stripped in _FAREWELL_WORDS:
            return "SMALL_TALK"
        for phrase in _ACKNOWLEDGEMENT_WORDS | _FAREWELL_WORDS:
            if stripped.startswith(phrase + " "):
                return "SMALL_TALK"

        # Training modules - MOVED LOWER and made more specific
        # Only trigger if there are explicit training keywords AND not a top selling/slow moving query
        training_keywords = ["how to", "learn", "training", "tutorial", "guide", "teach me", 
                            "walk me through", "show me how", "getting started", "beginner", 
                            "new user", "onboarding", "help me understand", "how do i", "how can i"]
        
        if any(p in text for p in training_keywords):
            # Skip if it's already a top selling or slow moving query
            if not any(p in text for p in TOP_SELLING_PHRASES) and not any(p in text for p in SLOW_MOVING_PHRASES):
                if any(w in text for w in ["video", "watch", "screencast", "demo"]):
                    return "TRAINING_VIDEO"
                elif any(w in text for w in ["pdf", "document", "manual", "handbook"]):
                    return "TRAINING_GUIDE"
                elif any(w in text for w in ["faq", "questions", "answers", "common issues"]):
                    return "TRAINING_FAQ"
                elif any(w in text for w in ["webinar", "live", "session", "class", "workshop"]):
                    return "TRAINING_WEBINAR"
                elif any(w in text for w in ["glossary", "term", "definition", "meaning",
                                              "what does", "what is", "sku", "moq", "uom",
                                              "eta", "grn", "dn"]):
                    return "TRAINING_GLOSSARY"
                else:
                    return "TRAINING_MODULE"

        # Cross-sell
        if any(p in text for p in _CROSS_SELL_PHRASES):
            return "GET_CROSS_SELL"

        # Upsell
        if any(p in text for p in [
            "better version", "upgrade", "premium alternative",
            "higher quality", "better value", "more expensive",
            "what's better than", "superior to", "upgrade to",
            "deluxe version", "professional grade", "commercial grade",
            "premium version", "enhanced version"
        ]):
            return "GET_UPSELL"

        # Seasonal recommendations
        if any(p in text for p in [
            "seasonal", "what to plant in", "best for this season",
            "recommend for", "good for planting", "seasonal crops",
            "what grows in", "planting guide for", "seasonal recommendations",
            "what should i plant in", "what to grow in"
        ]):
            return "GET_SEASONAL_RECOMMENDATIONS"

        # Trending products
        if any(p in text for p in [
            "trending", "popular now", "hot items", "best sellers",
            "most popular", "top selling", "what's trending",
            "customers are buying", "in demand", "high demand",
            "what is trending", "what's popular"
        ]):
            return "GET_TRENDING_PRODUCTS"

        # Follow-up quotations
        if any(p in text for p in [
            "stale quote", "follow up", "unconverted", "pending quote",
            "quote no response", "who hasn't responded", "open quotations",
            "quote conversion", "quotation follow", "follow up on quote",
            "customers with pending quotes",
        ]):
            return "FOLLOW_UP_QUOTATIONS"

        # Price alert
        if any(p in text for p in [
            "price alert", "notify when price drops", "alert me when price",
            "track price", "price monitoring", "price change alert",
        ]):
            return "PRICE_ALERT"

        # Market intelligence
        if any(p in text for p in [
            "market intelligence", "market analysis", "price trends",
            "market insights", "market overview", "industry prices",
        ]):
            return "MARKET_INTELLIGENCE"

        # Competitor price check
        if any(p in text for p in [
            "competitor price", "competitor prices", "price at", "prices at",
            "market price", "market prices", "other sellers", "compare price",
            "price comparison", "compare with", "compare prices for", "vs", "versus"
        ]):
            return "COMPETITOR_PRICE_CHECK"

        # Find best price
        if any(p in text for p in [
            "best price", "cheapest", "lowest price", "where to buy",
            "who sells cheapest", "best deal", "most affordable",
            "who has the best price", "where can i find.*cheap",
        ]):
            return "FIND_BEST_PRICE"

        # Inventory health
        if any(p in text for p in [
            "inventory health", "stock health", "inventory analysis", "health check",
        ]):
            return "ANALYZE_INVENTORY_HEALTH"

        # Reorder decisions
        if any(p in text for p in [
            "reorder", "what to order", "order decisions", "what should i order",
            "reorder recommendations", "reorder decisions",
        ]):
            return "GET_REORDER_DECISIONS"

        # Pricing opportunities
        if any(p in text for p in [
            "pricing opportunities", "price opportunities", "price analysis",
            "price drops", "price hikes",
        ]):
            return "ANALYZE_PRICING_OPPORTUNITIES"

        # Customer behavior analysis
        if any(p in text for p in [
            "customer behavior", "customer analysis", "customer insights",
            "analyze customer", "customer patterns", "purchase patterns",
        ]):
            return "ANALYZE_CUSTOMER_BEHAVIOR"

        # Forecast demand
        if any(p in text for p in [
            "forecast", "demand forecast", "sales forecast", "predict demand",
            "future demand",
        ]):
            return "FORECAST_DEMAND"

        # List customers
        if any(p in text for p in [
            "customers", "clients", "buyers",
            "show me customers", "list customers", "all customers", "wateja wote"
        ]):
            if not any(phrase in text for phrase in _CROSS_SELL_PHRASES):
                return "GET_CUSTOMERS"

        # Contact info
        if any(p in text for p in ["phone", "phone number", "contact", "email",
                                    "support", "reach you", "call", "whatsapp"]):
            return "CONTACT_INFO"

        # Company info (fallback - already checked above but keeping for safety)
        if any(p in text for p in ["about leysco", "tell me about", "what is leysco",
                                    "who is leysco", "leysco information"]):
            return "COMPANY_INFO"

        # Product info
        if any(p in text for p in ["easeed", "agriscope", "product line", "brands"]):
            if "price" not in text and "stock" not in text:
                return "PRODUCT_INFO"

        # Payment methods
        if any(p in text for p in [
            "payment method", "payment methods", "payment option",
            "how to pay", "accepted payment", "do you accept", "pay with",
            "mpesa", "bank transfer", "cash", "card", "paybill",
        ]):
            return "PAYMENT_METHODS"

        # How to order
        if any(p in text for p in [
            "how to order", "place an order", "how do i order", "ordering process",
        ]):
            return "HOW_TO_ORDER"

        # Get quotations
        if any(p in text for p in [
            "show quotes", "show quotations", "list quotes", "view quotes",
            "my quotes", "my quotations"
        ]):
            return "GET_QUOTATIONS"

        # Recommendations
        if any(w in text for w in ["recommend", "suggest", "best selling",
                                    "top selling", "popular", "good for"]):
            return "RECOMMEND_ITEMS"

        # Stock levels
        if any(p in text for p in [
            "stock level", "stock levels", "current stock", "stock status",
            "how much stock", "stock report",
        ]):
            return "GET_STOCK_LEVELS"

        # Low stock alerts
        if any(p in text for p in ["low stock", "low inventory", "stock alert",
                                    "running low", "alert"]):
            return "GET_LOW_STOCK_ALERTS"

        # Warehouse stock
        if any(p in text for p in ["stock in", "stock at", "inventory in",
                                    "inventory at", "which warehouse has"]):
            return "GET_WAREHOUSE_STOCK"

        # Product detection
        has_product = any(prod in text for prod in _COMMON_PRODUCTS)
        if has_product:
            if len(text.split()) <= 3:
                return "GET_ITEMS"
            if "stock" in text or "available" in text:
                return "GET_STOCK_LEVELS"
            if any(w in text for w in ["low", "alert", "running low"]):
                return "GET_LOW_STOCK_ALERTS"
            if "warehouse" in text:
                return "GET_WAREHOUSE_STOCK"
            return "GET_ITEMS"

        # Delivery tracking
        if any(p in text for p in ["track delivery", "delivery status",
                                    "where is delivery", "track order"]):
            return "TRACK_DELIVERY"

        # Delivery history
        if any(p in text for p in ["delivery history", "past deliveries",
                                    "previous deliveries"]):
            return "GET_DELIVERY_HISTORY"

        # Outstanding deliveries
        if any(p in text for p in ["outstanding deliver", "pending deliver", "undelivered"]):
            return "GET_OUTSTANDING_DELIVERIES"

        # Warehouses
        if any(w in text for w in ["warehouse", "warehouses", "storage location", "ghala", "maghala"]):
            if "stock" in text or "item" in text or "has" in text:
                return "GET_WAREHOUSE_STOCK"
            return "GET_WAREHOUSES"

        # Sellable items
        if any(w in text for w in ["sellable", "for sale", "saleable"]):
            return "GET_SELLABLE_ITEMS"
        
        # Purchasable items
        if any(w in text for w in ["purchasable", "to purchase"]):
            return "GET_PURCHASABLE_ITEMS"
        
        # Inventory items
        if any(w in text for w in ["inventory items", "in inventory"]):
            return "GET_INVENTORY_ITEMS"

        # List items
        if any(w in text for w in ["show me items", "list items", "items", "products",
                                    "what items", "bidhaa"]):
            return "GET_ITEMS"

        if has_product:
            return "GET_ITEMS"

        return "UNKNOWN"

    # -------------------------------------------------------------------------
    # SAFE JSON PARSER
    # -------------------------------------------------------------------------
    def _extract_json(self, text: str) -> dict | None:
        try:
            match = re.search(r"\{.*?\}", text, re.DOTALL | re.MULTILINE)
            if not match:
                return None
            return json.loads(match.group(0))
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # CLARIFICATION SUGGESTIONS
    # -------------------------------------------------------------------------
    def _clarify_suggestions(self, text: str, language: str = "en") -> list[str]:
        text_lower = text.lower()
        sw = language in ("sw", "mixed")

        if any(w in text_lower for w in ["price", "cost", "bei", "how much"]):
            if sw:
                return ["Bei ya bidhaa gani?", "Angalia bei ya vegimax", "Bei ya mteja"]
            return ["Price of which item?", "Check price of vegimax", "Customer pricing"]

        if any(w in text_lower for w in ["stock", "hisa", "available", "how many"]):
            if sw:
                return ["Hisa ya bidhaa gani?", "Angalia hisa ya maghala yote", "Arifa za hisa chini"]
            return ["Stock of which item?", "Check all warehouse stock", "Low stock alerts"]

        if any(w in text_lower for w in ["customer", "mteja", "client", "who is"]):
            if sw:
                return ["Maelezo ya mteja gani?", "Onyesha wateja wote", "Oda za mteja"]
            return ["Details for which customer?", "Show all customers", "Customer orders"]

        if any(w in text_lower for w in ["quote", "quotation", "nukuu", "create", "make"]):
            if sw:
                return ["Unda nukuu mpya", "Onyesha nukuu zilizopo", "Fuatilia nukuu"]
            return ["Create a new quotation", "Show existing quotations", "Follow up on quotes"]
        
        if any(w in text_lower for w in ["sell", "out", "who", "target", "buy"]):
            if sw:
                return ["Nani atanunua bidhaa hii?", "Wateja wanaonunua nini?", "Unda nukuu kwa wateja"]
            return ["Who would buy this product?", "Find customers for a product", "Create quotes for potential buyers"]

        if any(w in text_lower for w in ["top", "best", "popular", "selling", "trending"]):
            if sw:
                return ["Onyesha bidhaa 10 zinazouzwa zaidi", "Bidhaa gani zinauzwa sana?", "Top 5 bidhaa kwa mwezi huu"]
            return ["Show top 10 selling items", "Which products sell the most?", "Top 5 items this month"]
        
        # Sales analytics suggestions
        if any(w in text_lower for w in ["sales", "analytics", "revenue", "report"]):
            if sw:
                return ["Onyesha uchambuzi wa mauzo", "Ripoti ya mauzo kwa mwezi", "Muhtasari wa mauzo"]
            return ["Show sales analytics", "Sales report for last month", "Sales performance overview"]

        if any(w in text_lower for w in ["slow", "least", "worst", "dead stock", "not selling"]):
            if sw:
                return ["Onyesha bidhaa zinazosonga polepole", "Bidhaa gani hazijauzwa?", "Bidhaa za dead stock"]
            return ["Show slow moving items", "Which products are not selling?", "Dead stock items"]

        if any(w in text_lower for w in ["order", "purchase", "oda", "what did"]):
            if sw:
                return ["Oda za mteja gani?", "Mteja alinunua nini?", "Historia ya ununuzi"]
            return ["Orders for which customer?", "What did the customer buy?", "Purchase history"]

        if sw:
            return ["Angalia bei ya bidhaa", "Angalia hisa", "Unda nukuu", "Onyesha wateja", "Bidhaa zinazouzwa sana"]
        return ["Check item price", "Check stock levels", "Create a quotation", "Show customers", "Top selling items"]

    # -------------------------------------------------------------------------
    # MAIN CLASSIFIER (Sync)
    # -------------------------------------------------------------------------
    def classify(self, user_message: str) -> dict:
        """Sync classification - used for compatibility."""
        return asyncio.run(self.classify_async(user_message))

    # -------------------------------------------------------------------------
    # MAIN CLASSIFIER (Async - Optimized)
    # -------------------------------------------------------------------------
    async def classify_async(self, user_message: str) -> dict:
        """
        Async intent classification with fast-path, caching, and parallel execution.
        """
        text_lower = user_message.lower().strip()
        language = "en"

        # ── STEP 1: Check cache first (fastest) ──────────────────────────────
        cache_key = f"intent:{user_message}"
        cached = await cache_service.get_simple_async(cache_key)
        if cached:
            logger.info(f"⚡ Intent cache hit: {user_message[:50]}...")
            return cached

        # ── STEP 2: Try fast-path patterns (no LLM) ──────────────────────────
        fast_path_result = self._try_fast_path(user_message)
        if fast_path_result:
            intent, entities = fast_path_result
            result = _result(
                intent=intent,
                language=language,
                confidence=_CONF["fast_path"],
                entities=entities,
                original_text=user_message
            )
            await cache_service.set_simple_async(cache_key, result, ttl=300)
            return result

        # ── STEP 3: Swahili detection ────────────────────────────────────────
        swahili_result = self.swahili.process_swahili_query(user_message)

        if swahili_result["detected_language"] != "en":
            language = swahili_result["detected_language"]
            logger.info(f"🇰🇪 Swahili detected: lang={language}")

            if swahili_result["intent"] != "UNKNOWN":
                intent = swahili_result["intent"]
                result = _result(
                    intent=intent,
                    language=language,
                    confidence=_CONF["swahili"],
                    entities=swahili_result.get("entities", {}),
                    original_text=user_message,
                    normalized_text=swahili_result.get("normalized_text", ""),
                )
                await cache_service.set_simple_async(cache_key, result, ttl=300)
                return result

            if swahili_result.get("normalized_text"):
                text_lower = swahili_result["normalized_text"].lower()

        # ── STEP 4: Customer Segmentation / "Sell Out" queries ───────────────
        is_sell_out_query = False
        
        for phrase in _SELL_OUT_PHRASES:
            if phrase in text_lower:
                is_sell_out_query = True
                logger.info(f"🎯 Sell-out query detected: '{phrase}'")
                break
        
        sell_out_patterns = [
            r'^sell\s+out\s+', r'^who\s+to\s+sell\s+', r'who\s+would\s+buy\s+',
            r'who\s+buys\s+', r'which\s+customer\s+', r'which\s+customers\s+',
            r'customers\s+that\s+buy\s+', r'customers\s+who\s+buy\s+',
            r'target\s+customers\s+for\s+', r'potential\s+customers\s+for\s+',
        ]
        for pattern in sell_out_patterns:
            if re.search(pattern, text_lower):
                is_sell_out_query = True
                break
        
        if is_sell_out_query:
            product = None
            extract_patterns = [
                r'sell\s+out\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\?|$)',
                r'who\s+would\s+buy\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\?|$)',
                r'which\s+customers?\s+buy\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\?|$)',
                r'customers\s+who\s+buy\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\?|$)',
                r'target\s+customers\s+for\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\?|$)',
            ]
            
            for pattern in extract_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    candidate = match.group(1).strip()
                    candidate = re.sub(r'\b(sell|out|to|for|who|would|buy|buys|target|customers)\b', '', candidate, flags=re.IGNORECASE)
                    candidate = candidate.strip()
                    if candidate and len(candidate) > 1:
                        product = candidate
                        break
            
            if product:
                for known in _COMMON_PRODUCTS:
                    if known in product.lower() or product.lower() in known:
                        product = known
                        break
                
                result = _result(
                    intent="FIND_CUSTOMERS_BY_ITEM",
                    language=language,
                    confidence=0.95,
                    entities={"item_name": product, "action": "sell_out"}
                )
                await cache_service.set_simple_async(cache_key, result, ttl=300)
                return result
            else:
                result = _result(
                    intent="CLARIFY",
                    language=language,
                    confidence=0.85,
                    alternatives=["Sell out which product?", "Find customers for which item?"]
                )
                await cache_service.set_simple_async(cache_key, result, ttl=300)
                return result

        # ── STEP 5: Short query fast-path (no AI) ───────────────────────────
        if len(text_lower) < 35:
            if any(w in text_lower for w in ["hi", "hello", "hey", "jambo", "habari"]):
                result = _result("GREETING", language, _CONF["fast_path"])
                await cache_service.set_simple_async(cache_key, result, ttl=300)
                return result

            if any(w in text_lower for w in ["thanks", "thank you", "asante"]):
                result = _result("THANKS", language, _CONF["fast_path"])
                await cache_service.set_simple_async(cache_key, result, ttl=300)
                return result

            # Add sales check for short queries
            if any(w in text_lower for w in ["sales", "revenue", "analytics"]):
                result = _result("GET_SALES_ANALYTICS", language, _CONF["fast_path"])
                await cache_service.set_simple_async(cache_key, result, ttl=300)
                return result

            stripped = text_lower.rstrip("!?.,")
            if stripped in _ACKNOWLEDGEMENT_WORDS or stripped in _FAREWELL_WORDS:
                result = _result("SMALL_TALK", language, _CONF["fast_path"])
                await cache_service.set_simple_async(cache_key, result, ttl=300)
                return result

        # ── STEP 6: Rule-based fallback (cached) ─────────────────────────────
        rule_intent = self._rule_based_intent(user_message)
        
        if rule_intent != "UNKNOWN":
            confidence = _CONF["rule_fallback"]
            result = _result(
                intent=rule_intent,
                language=language,
                confidence=confidence,
            )
            await cache_service.set_simple_async(cache_key, result, ttl=300)
            return result

        # ── STEP 7: AI classification (only if needed) ───────────────────────
        try:
            prompt = self.prompt_manager.get_intent_prompt(user_message)
            response = await self.llm.generate_async(prompt)

            if response and response.strip():
                data = self._extract_json(response)
                if data:
                    ai_intent = data.get("intent", "").strip().upper()

                    if ai_intent in _VALID_INTENTS_SET:
                        logger.info(f"AI raw intent: {ai_intent}")
                        
                        # Post-AI overrides
                        original_ai = ai_intent
                        
                        # Check for quotation creation again
                        if 'quotation' in text_lower or 'quote' in text_lower:
                            if any(w in text_lower for w in ['create', 'make', 'generate', 'prepare', 'new', 'cash sale']):
                                ai_intent = "CREATE_QUOTATION"
                        # Check for company info
                        elif 'leysco' in text_lower and any(w in text_lower for w in ['tell me about', 'what is', 'who is', 'about']):
                            ai_intent = "COMPANY_INFO"
                            logger.info(f"🏢 AI override: company info detected")
                        # Add sales analytics check
                        elif any(p in text_lower for p in SALES_ANALYTICS_PHRASES):
                            ai_intent = "GET_SALES_ANALYTICS"
                            logger.info(f"📈 AI override: sales analytics detected")
                        elif any(p in text_lower for p in _SELL_OUT_PHRASES):
                            ai_intent = "FIND_CUSTOMERS_BY_ITEM"
                        elif "customer" in text_lower and "price" in text_lower:
                            ai_intent = "GET_CUSTOMER_PRICE"
                        elif "low stock" in text_lower:
                            ai_intent = "GET_LOW_STOCK_ALERTS"
                        elif any(p in text_lower for p in TOP_SELLING_PHRASES):
                            ai_intent = "GET_TOP_SELLING_ITEMS"
                        elif any(p in text_lower for p in SLOW_MOVING_PHRASES):
                            ai_intent = "GET_SLOW_MOVING_ITEMS"
                        
                        confidence = _CONF["ai_override"] if ai_intent != original_ai else _CONF["ai_clean"]
                        
                        result = _result(
                            intent=ai_intent,
                            language=language,
                            confidence=confidence,
                        )
                        await cache_service.set_simple_async(cache_key, result, ttl=300)
                        return result

        except Exception as e:
            logger.warning(f"LLM intent failed: {e}")

        # ── STEP 8: Final fallback to CLARIFY ────────────────────────────────
        suggestions = self._clarify_suggestions(user_message, language)
        result = _result(
            intent="CLARIFY",
            language=language,
            confidence=0.30,
            alternatives=suggestions,
        )
        await cache_service.set_simple_async(cache_key, result, ttl=60)
        return result

    # -------------------------------------------------------------------------
    # BATCH CLASSIFICATION (for multiple messages)
    # -------------------------------------------------------------------------
    async def classify_batch(self, messages: list[str]) -> list[dict]:
        """Classify multiple messages in parallel."""
        tasks = [self.classify_async(msg) for msg in messages]
        return await asyncio.gather(*tasks)


# Singleton instance
intent_classifier = IntentClassifier()