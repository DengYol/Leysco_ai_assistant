"""Query rewriting and expansion for better intent detection"""

import re
import logging
from typing import Optional, Tuple, List, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)


class QueryRewriter:
    """
    Rewrites vague or poorly phrased queries into structured patterns
    that the intent classifier can better understand.
    """

    def __init__(self):
        # Price-related patterns
        self.price_patterns = [
            (r"(?:how much|what'?s the price|how much is|price of|cost of|bei ya|gharama ya)\s+(.+)", "price"),
            (r"(.+)\s+(?:price|cost|bei|gharama)", "price"),
            (r"(?:expensive|cheap|costly)\s+(.+)", "price"),
            (r"(?:tell me|show me|get me)\s+(?:the )?price\s+(?:of|for)?\s*(.+)", "price"),
            (r"(?:what does|how much does)\s+(.+)\s+(?:cost|sell for)", "price"),
        ]

        # Stock-related patterns
        self.stock_patterns = [
            (r"(?:stock|inventory|available|hisa|viwango|idadi)\s+(?:of|for|ya|za)?\s*(.+)", "stock"),
            (r"(?:how many|quantity of)\s+(.+)\s+(?:do we have|is available|zilizopo)", "stock"),
            (r"(?:is there|do we have)\s+(.+)\s+(?:in stock|available)", "stock"),
            (r"(?:check|look up)\s+(?:stock of|inventory for)?\s*(.+)", "stock"),
            (r"(.+)\s+(?:stock|inventory|hisa)", "stock"),
        ]

        # Critical: Churn risk / Customer health patterns (HIGH PRIORITY)
        self.churn_risk_patterns = [
            (r"(?:show|customer|list|get|find)\s+customers?\s+(?:at|with|having)?\s+(?:churn\s+risk|churn risk|risk)", "customer_health"),
            (r"(?:who|customers)\s+(?:is|are)\s+(?:likely|about)\s+to\s+(?:leave|churn)", "customer_health"),
            (r"(?:customer\s+health|health\s+score|health\s+check)", "customer_health"),
            (r"(?:churn\s+analysis|churn\s+prediction|churn\s+alert)", "customer_health"),
            (r"(?:high|medium|low)\s+risk\s+customers?", "customer_health"),
            (r"wateja\s+walio\s+katika\s+hatari", "customer_health"),
            (r"afya\s+ya\s+wateja", "customer_health"),
        ]

        # Warehouse-related patterns (FIXED: added before stock patterns so
        # "view warehouse stock" / "warehouse stock" routes to GET_WAREHOUSES
        # rather than being mangled into "stock of view warehouse?")
        self.warehouse_patterns = [
            (r"(?:view|show|list|get|display|see)\s+(?:all\s+)?warehouse(?:s)?\s*(?:stock|inventory|items)?", "warehouses"),
            (r"warehouse(?:s)?\s+(?:stock|inventory|list|summary|overview|report)", "warehouses"),
            (r"(?:all\s+)?warehouses?\s+(?:and\s+)?(?:stock|inventory|levels)", "warehouses"),
            (r"(?:stock|inventory)\s+(?:across|by|per|in\s+all)\s+warehouses?", "warehouses"),
            (r"(?:show|list|get)\s+warehouses?$", "warehouses"),
            (r"onyesha\s+maghala|orodha\s+ya\s+maghala", "warehouses"),
        ]

        # Delivery-related patterns
        self.delivery_patterns = [
            (r"(?:track|where is|status of|check on)\s+(?:my )?(?:delivery|order|shipment)(?:\s+#?(\d+))?", "delivery"),
            (r"(?:outstanding|pending|open)\s+(?:deliveries|orders|delivery)", "outstanding_deliveries"),
            (r"(?:when will|when is)\s+(?:my )?(?:delivery|order)\s+(?:arrive|come|get here)", "delivery_status"),
            (r"(?:delivery|order)\s+(?:status|update|progress)", "delivery_status"),
            (r"(?:show me|list|what are)\s+(?:the )?(?:outstanding|pending)\s+(?:deliveries|orders)", "outstanding_deliveries"),
        ]

        # Top selling patterns
        self.top_selling_patterns = [
            (r"(?:top|best|popular|trending|hottest)\s+(?:selling|performing|products|items)", "top_selling"),
            (r"(?:best sellers|bestsellers|top sellers)", "top_selling"),
            (r"(?:what do|customers love|people buy|popular right now)", "top_selling"),
            (r"(?:most sold|highest selling|frequently bought)", "top_selling"),
            (r"sales (?:leaders|hits|winners)", "top_selling"),
            (r"zinazouzwa sana|bidhaa bora|muu mkubwa", "top_selling"),
        ]

        # Slow moving patterns
        self.slow_moving_patterns = [
            (r"(?:slow(?:ly)?|poorly)\s+(?:moving|selling|performing)", "slow_moving"),
            (r"(?:not|isn't)\s+(?:selling|moving)\s+well", "slow_moving"),
            (r"(?:stuck|stagnant|dead)\s+(?:stock|inventory)", "slow_moving"),
            (r"(?:excess|overstock|too much)\s+(?:stock|inventory)", "slow_moving"),
            (r"(?:what's not|items not)\s+(?:selling|moving)", "slow_moving"),
            (r"zinazotembea polepole|bidhaa zilizokaa|hisa zaidi", "slow_moving"),
        ]

        # Customer-related patterns
        self.customer_patterns = [
            (r"(?:find|show|get|search for)\s+(?:customer|mteja|client)\s+(.+)", "customer"),
            (r"(?:who is|customer details|info on)\s+(.+)", "customer"),
            (r"(?:orders?|purchases|buying history)\s+(?:for|of|from)\s+(.+)", "customer_orders"),
            (r"(?:what has|what did)\s+(.+)\s+(?:ordered|bought|purchased)", "customer_orders"),
        ]

        # Quotation patterns
        self.quotation_patterns = [
            (r"(?:create|make|prepare|generate)\s+(?:a )?(?:quote|quotation|estimate)\s+(?:for)?\s*(.+)", "create_quotation"),
            (r"(?:new quote|quotation for)\s+(.+)", "create_quotation"),
            (r"(?:need a quote|quote me|give me a price)\s+(?:for)?\s*(.+)", "create_quotation"),
            (r"unda nukuu|tengeneza nukuu|nukuu kwa", "create_quotation"),
        ]

        # General inquiry patterns
        self.general_patterns = [
            (r"(?:tell me about|what is|what are|information on|info about)\s+(.+)", "info"),
            (r"(?:show me|list|get me|find me)\s+(.+)", "list"),
            (r"(?:help|assist|support)", "help"),
        ]

        # Item extraction patterns
        self.item_extraction = [
            r"(?:vegimax|vegimax-\d+ml|vegimax-\d+l)",
            r"(?:cabbage|cabage|cabiji|cabbage seeds)",
            r"(?:tomato|tomatoes|matunda|nyanya)",
            r"(?:maize|corn|mahindi|maize seed)",
            r"(?:carrot|carrots|karoti|carrot seed)",
            r"(?:onion|onions|kitunguu|onion seed)",
            r"(?:beans|bean|maharagwe|bean seed)",
            r"(?:easeed|easeed-\d+|easeed pouch)",
            r"(?:tosheka|tosheka mh401|tosheka seed)",
        ]

        # Common misspellings and Swahili mappings
        self.misspellings = {
            "vegimax": "vegimax",
            "vegimx": "vegimax",
            "vegmax": "vegimax",
            "vegimax 30": "vegimax 30ml",
            "vegimax 30ml": "vegimax 30ml",
            "cabage": "cabbage",
            "cabiji": "cabbage",
            "matunda": "tomato",
            "nyanya": "tomato",
            "mahindi": "maize",
            "karoti": "carrot",
            "kitunguu": "onion",
            "maharagwe": "beans",
        }

        # Intent to standard phrase mapping
        self.intent_phrases = {
            "GET_ITEM_PRICE": "price of",
            "GET_STOCK_LEVELS": "stock of",
            "GET_TOP_SELLING_ITEMS": "top selling items",
            "GET_SLOW_MOVING_ITEMS": "slow moving items",
            "GET_OUTSTANDING_DELIVERIES": "outstanding deliveries",
            "TRACK_DELIVERY": "track delivery",
            "CREATE_QUOTATION": "create quotation for",
            "GET_CUSTOMERS": "show customers",
            "GET_CUSTOMER_HEALTH": "show customers at churn risk",
            "GET_CUSTOMER_ORDERS": "customer orders for",
            "GET_WAREHOUSES": "show warehouses",
            "FIND_CUSTOMERS_BY_ITEM": "customers who buy",
        }

    def rewrite(self, message: str) -> Tuple[str, str, Optional[dict]]:
        """
        Rewrite query and extract structured information.

        Returns:
            Tuple of (rewritten_message, detected_intent, extracted_entities)
        """
        original = message
        rewritten = message
        detected_intent = None
        extracted_entities = {}

        # Step 0: Check for PROTECTED patterns FIRST (don't rewrite these)
        protected_patterns = [
            (self.churn_risk_patterns, "GET_CUSTOMER_HEALTH"),
        ]

        for patterns, intent_type in protected_patterns:
            for pattern, _ in patterns:
                if re.search(pattern, rewritten, re.IGNORECASE):
                    logger.info(f"Protected pattern detected: '{original}' → intent: {intent_type}")
                    return original, intent_type, {}

        # Step 0b: FIXED — check warehouse patterns before any rewriting so
        # queries like "View warehouse stock" or "warehouse stock" are not
        # first transformed into "stock of view warehouse?" by the stock
        # patterns, which then confuses the warehouse entity extractor.
        for pattern, _ in self.warehouse_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                logger.info(f"Warehouse pattern detected: '{original}' → intent: GET_WAREHOUSES")
                return "show warehouses?", "GET_WAREHOUSES", {}

        # Step 1: Fix common misspellings
        rewritten = self._fix_misspellings(rewritten)

        # Step 2: Try to detect intent and extract entities
        detected_intent, extracted_entities = self._detect_intent_and_extract(rewritten)

        # Step 3: Rewrite based on detected intent
        if detected_intent:
            rewritten = self._rewrite_for_intent(rewritten, detected_intent, extracted_entities)

        # Step 4: If no intent detected, try pattern matching
        if not detected_intent:
            detected_intent, rewritten, extracted_entities = self._pattern_based_rewrite(rewritten)

        # Step 5: Clean up the rewritten query
        rewritten = self._clean_query(rewritten)

        if rewritten != original:
            logger.info(f"Query rewritten: '{original}' → '{rewritten}' (intent: {detected_intent})")

        return rewritten, detected_intent, extracted_entities

    def _fix_misspellings(self, text: str) -> str:
        """Fix common misspellings"""
        result = text.lower()
        for wrong, correct in self.misspellings.items():
            if wrong in result:
                result = result.replace(wrong, correct)
        return result

    def _detect_intent_and_extract(self, text: str) -> Tuple[Optional[str], dict]:
        """Detect intent and extract entities from text"""
        text_lower = text.lower()
        entities = {}

        # CRITICAL: Check for churn risk first (highest priority)
        for pattern, _ in self.churn_risk_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.info(f"Detected churn risk intent: '{text}'")
                return "GET_CUSTOMER_HEALTH", entities

        # Check for price queries
        for pattern, _ in self.price_patterns:
            match = re.search(pattern, text_lower)
            if match:
                entities["item_name"] = self._extract_item_name(match.group(1))
                if entities["item_name"]:
                    return "GET_ITEM_PRICE", entities

        # Check for stock queries
        for pattern, _ in self.stock_patterns:
            match = re.search(pattern, text_lower)
            if match:
                entities["item_name"] = self._extract_item_name(match.group(1) if match.groups() else text)
                if entities["item_name"]:
                    return "GET_STOCK_LEVELS", entities

        # Check for delivery queries
        for pattern, delivery_type in self.delivery_patterns:
            match = re.search(pattern, text_lower)
            if match:
                if delivery_type == "outstanding_deliveries":
                    return "GET_OUTSTANDING_DELIVERIES", entities
                elif delivery_type in ("delivery", "delivery_status"):
                    if match.groups() and match.group(1):
                        entities["delivery_number"] = match.group(1)
                    return "TRACK_DELIVERY", entities

        # Check for top selling
        for pattern, _ in self.top_selling_patterns:
            if re.search(pattern, text_lower):
                return "GET_TOP_SELLING_ITEMS", entities

        # Check for slow moving
        for pattern, _ in self.slow_moving_patterns:
            if re.search(pattern, text_lower):
                return "GET_SLOW_MOVING_ITEMS", entities

        # Check for quotation creation
        for pattern, _ in self.quotation_patterns:
            match = re.search(pattern, text_lower)
            if match:
                if match.groups():
                    customer_part = match.group(1)
                    entities["customer_name"] = self._extract_customer_name(customer_part)
                return "CREATE_QUOTATION", entities

        # Check for customer queries
        for pattern, intent_type in self.customer_patterns:
            match = re.search(pattern, text_lower)
            if match:
                if intent_type == "customer":
                    entities["customer_name"] = self._extract_customer_name(match.group(1))
                    return "GET_CUSTOMERS", entities
                elif intent_type == "customer_orders":
                    entities["customer_name"] = self._extract_customer_name(match.group(1))
                    return "GET_CUSTOMER_ORDERS", entities

        return None, entities

    def _extract_item_name(self, text: str) -> Optional[str]:
        """Extract item name from text"""
        if not text:
            return None

        text = text.strip()

        for pattern in self.item_extraction:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)

        filler_words = ["the", "a", "an", "of", "for", "to", "in", "at", "with", "about", "tell", "me", "show", "get"]
        words = text.split()
        cleaned = [w for w in words if w not in filler_words]

        if cleaned:
            return " ".join(cleaned[:3])

        return None

    def _extract_customer_name(self, text: str) -> Optional[str]:
        """Extract customer name from text"""
        if not text:
            return None

        remove_words = {"a", "quotation", "quote", "for", "with", "the", "and", "new"}
        words = text.split()
        cleaned = [w for w in words if w.lower() not in remove_words]

        if cleaned:
            return " ".join(cleaned[:2])

        return None

    def _rewrite_for_intent(self, text: str, intent: str, entities: dict) -> str:
        """Rewrite query into standard format for the detected intent.

        IMPORTANT — CREATE_QUOTATION must never be rewritten to a shorter
        form.  The full original text (including the 'with <items>' clause)
        is needed by multi_turn_quotation._extract_items_from_message().
        Truncating to just the customer name causes the item parser to find
        nothing and start an empty draft instead of creating the quotation.
        """
        standard_phrase = self.intent_phrases.get(intent, "")

        if intent == "GET_ITEM_PRICE" and entities.get("item_name"):
            return f"{standard_phrase} {entities['item_name']}"

        if intent == "GET_STOCK_LEVELS" and entities.get("item_name"):
            return f"{standard_phrase} {entities['item_name']}"

        if intent == "GET_CUSTOMER_ORDERS" and entities.get("customer_name"):
            return f"{standard_phrase} {entities['customer_name']}"

        # CREATE_QUOTATION: return original text unchanged so the items
        # clause ('with 3 vegimax 30ml') is preserved for the item parser.
        if intent == "CREATE_QUOTATION":
            return text

        # GET_CUSTOMER_HEALTH: preserve original text unchanged.
        if intent == "GET_CUSTOMER_HEALTH":
            return text

        return text

    def _pattern_based_rewrite(self, text: str) -> Tuple[Optional[str], str, dict]:
        """Pattern-based rewrite for ambiguous queries"""
        text_lower = text.lower()
        entities = {}

        # What is... patterns
        if text_lower.startswith("what is") or text_lower.startswith("what's"):
            if "price" in text_lower or "cost" in text_lower:
                item = self._extract_item_name(text_lower.replace("what is", "").replace("what's", ""))
                if item:
                    return "GET_ITEM_PRICE", f"price of {item}", {"item_name": item}

            if "stock" in text_lower or "available" in text_lower:
                item = self._extract_item_name(text_lower)
                if item:
                    return "GET_STOCK_LEVELS", f"stock of {item}", {"item_name": item}

        # How many/much patterns
        if text_lower.startswith("how many") or text_lower.startswith("how much"):
            if "stock" in text_lower or "available" in text_lower or "left" in text_lower:
                item = self._extract_item_name(text_lower)
                if item:
                    return "GET_STOCK_LEVELS", f"stock of {item}", {"item_name": item}

            if "price" in text_lower or "cost" in text_lower:
                item = self._extract_item_name(text_lower)
                if item:
                    return "GET_ITEM_PRICE", f"price of {item}", {"item_name": item}

        # Show / View / List patterns
        if re.match(r'^(?:show(?:\s+me)?|view|list|display|see)\b', text_lower):
            rest = re.sub(r'^(?:show(?:\s+me)?|view|list|display|see)\s*', '', text_lower).strip()

            if "churn risk" in rest or "customer health" in rest or "at risk" in rest:
                return "GET_CUSTOMER_HEALTH", text, {}

            # FIXED: warehouse check before stock so "view warehouse stock"
            # maps to GET_WAREHOUSES, not GET_STOCK_LEVELS
            if "warehouse" in rest or "warehouses" in rest:
                return "GET_WAREHOUSES", "show warehouses", {}

            if "price" in rest:
                item = self._extract_item_name(rest)
                if item:
                    return "GET_ITEM_PRICE", f"price of {item}", {"item_name": item}

            if "stock" in rest or "inventory" in rest:
                item = self._extract_item_name(rest)
                if item:
                    return "GET_STOCK_LEVELS", f"stock of {item}", {"item_name": item}

            if "customer" in rest or "customers" in rest:
                return "GET_CUSTOMERS", "show customers", {}

            if "order" in rest or "orders" in rest:
                customer = self._extract_customer_name(rest)
                if customer:
                    return "GET_CUSTOMER_ORDERS", f"customer orders for {customer}", {"customer_name": customer}

        # Tell me about patterns
        if text_lower.startswith("tell me about"):
            topic = text_lower.replace("tell me about", "").strip()
            item = self._extract_item_name(topic)
            if item:
                return "GET_ITEM_PRICE", f"price of {item}", {"item_name": item}

        return None, text, entities

    def _clean_query(self, text: str) -> str:
        """Clean and normalize the query"""
        text = re.sub(r'\s+', ' ', text).strip()
        if not text.endswith(('?', '.', '!')):
            text += '?'
        return text

    def expand_query(self, query: str) -> List[str]:
        """Generate query variations for better matching"""
        variations = [query]

        if "price of" in query:
            item = query.replace("price of", "").strip()
            variations.append(f"how much is {item}")
            variations.append(f"what does {item} cost")
            variations.append(f"{item} price")

        if "stock of" in query:
            item = query.replace("stock of", "").strip()
            variations.append(f"how many {item} in stock")
            variations.append(f"inventory of {item}")
            variations.append(f"{item} available")

        direct = re.sub(r'^(what|how|where|when|why|tell me|show me|can you)\s+', '', query.lower())
        if direct != query.lower():
            variations.append(direct)

        return list(set(variations))


# Singleton instance
_query_rewriter = None


def get_query_rewriter() -> QueryRewriter:
    """Get singleton query rewriter instance"""
    global _query_rewriter
    if _query_rewriter is None:
        _query_rewriter = QueryRewriter()
    return _query_rewriter