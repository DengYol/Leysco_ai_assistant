"""Query rewriting and expansion for better intent detection"""

import re
import logging
from typing import Optional, Tuple, List, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# NON-ITEM WORDS
# Words that look like item names when captured by "stock of X" patterns
# but are actually generic qualifiers. Expanded to include adjectives like
# "low"/"high" that appear in alert-style queries.
# ---------------------------------------------------------------------------
_NON_ITEM_WORDS = {
    # Generic stock/inventory words
    "levels", "level", "all", "everything", "items", "products",
    "alerts", "alert", "report", "summary", "overview", "list",
    "current", "now", "today", "hisa", "viwango", "me", "us",
    # Adjectives used in alert-style queries ("low stock", "high stock")
    "low", "high", "minimum", "min", "critical", "zero", "empty",
    "running", "out", "near", "reorder", "insufficient", "short",
    "excess", "surplus", "maximum", "max",
}

# ---------------------------------------------------------------------------
# LOW-STOCK PATTERNS
# Must be checked at Step 0 — before ANY stock or price pattern — so
# adjectives like "low" are never extracted as item names.
# ---------------------------------------------------------------------------
_LOW_STOCK_PATTERNS = [
    r"\blow[\s\-]?stock\b",
    r"\bstock[\s\-]?alert[s]?\b",
    r"\bstock[\s\-]?level[s]?\s*(are\s*)?(low|critical|minimum)\b",
    r"\breorder[\s\-]?(alert[s]?|list|report|point)?\b",
    r"\bitems?\s+(running|near(ing)?)\s+(low|out)\b",
    r"\bwhat\s+(needs?|require[s]?)\s+reorder(ing)?\b",
    r"\bminimum\s+stock\b",
    r"\bcritical\s+stock\b",
    r"\bstock\s+(running\s+)?out\b",
    r"\bout[\s\-]of[\s\-]stock\b",
    r"\bstock\s+shortage[s]?\b",
    r"\bbelow\s+(minimum|reorder|safety)\b",
]

# ---------------------------------------------------------------------------
# CONVERSATIONAL / GREETING PATTERNS
# Must be checked at Step 0 — before ANY price or item extraction.
# This prevents "Tell me about yourself" from being treated as a price query.
# ---------------------------------------------------------------------------
_CONVERSATIONAL_PATTERNS = [
    r"^(?:tell me about yourself|who are you|what are you)$",
    r"^(?:introduce yourself|about you|what is your name|who made you|who created you)$",
    r"^(?:what do you do|how can you help me|what are your capabilities|your features|about yourself)$",
    r"^(?:tell me more about yourself|explain yourself|what is your purpose)$",
    r"^(?:how do you work|what can you do|help me understand you)$",
]

# ---------------------------------------------------------------------------
# ITEM DETAIL PATTERNS
# Must be checked before customer_rules sees "details of X", otherwise
# "show item details of Cap Measuring" steals the item name as a customer.
# ---------------------------------------------------------------------------
_ITEM_DETAIL_PATTERNS = [
    # "show item/items details of X" — singular OR plural
    r"(?:show|get|view|display|fetch)\s+items?\s+details?\s+(?:of|for)\s+(.+)",
    r"(?:show|get|view|display|fetch)\s+products?\s+details?\s+(?:of|for)\s+(.+)",
    # bare "item/items details of X"
    r"items?\s+details?\s+(?:of|for|about)\s+(.+)",
    r"products?\s+details?\s+(?:of|for|about)\s+(.+)",
    # "details of item/items X"
    r"details?\s+(?:of|for|about)\s+(?:items?|products?)\s+(.+)",
    r"(?:show|get|view)\s+details?\s+(?:of|for)\s+(?:items?|products?)\s+(.+)",
    # Swahili
    r"(?:maelezo|taarifa)\s+ya\s+bidhaa\s+(.+)",
]

# ---------------------------------------------------------------------------
# ITEM DETAIL SIGNAL WORDS
# If any of these appear BEFORE "details" in the query, the subject is an
# item — not a customer. Used as a guard in customer_rules as well.
# ---------------------------------------------------------------------------
ITEM_DETAIL_SIGNALS = {
    "item", "product", "sku", "stock", "inventory",
    "bidhaa", "kitu",
}

# ---------------------------------------------------------------------------
# LISTING / BROWSE PATTERNS
# Detects "show me 10 items", "list all products", "browse inventory" etc.
# Checked before price/stock patterns so a number ("10") is never mistaken
# for part of a price/stock query, and the context resolver never inherits
# item_name from the previous turn.
# Tuple format: (regex_pattern, has_numeric_qty_capture_group)
# ---------------------------------------------------------------------------
_LISTING_PATTERNS = [
    # "show me 10 items" / "list 5 products" / "get me 20 items"
    (r"(?:show(?:\s+me)?|list|get(?:\s+me)?|display|browse|view)\s+(\d+)\s+(?:items?|products?|inventory)", True),
    # "show me all items" / "list all products"
    (r"(?:show(?:\s+me)?|list|get(?:\s+me)?|display|browse|view)\s+(?:all|every)\s+(?:items?|products?|inventory)", False),
    # bare "show me items" / "browse items" / "view products"
    (r"(?:show(?:\s+me)?|list|get(?:\s+me)?|display|browse|view)\s+(?:items?|products?|inventory)$", False),
    # Swahili: "onyesha bidhaa" / "orodhesha 10 bidhaa"
    (r"(?:onyesha|orodhesha|pata)\s+(\d+)?\s*(?:bidhaa|vitu)", False),
]


class QueryRewriter:
    """
    Rewrites vague or poorly phrased queries into structured patterns
    that the intent classifier can better understand.
    """

    def __init__(self):
        # =========================================================
        # CRITICAL: PRICE-RELATED PATTERNS - HIGHEST PRIORITY
        # =========================================================
        self.price_patterns = [
            # Highest specificity first
            (r"^(?:what is|what\'s|whats)\s+the\s+price\s+of\s+(.+)", "price"),
            (r"^(?:price|cost|bei|gharama)\s+(?:of|ya)?\s*(.+)", "price"),
            (r"^how\s+much\s+(?:is|does)\s+(.+)\s+(?:cost|price)?$", "price"),
            (r"(?:how much|what'?s the price|how much is|price of|cost of|bei ya|gharama ya)\s+(.+)", "price"),
            # FIX: "QUALIFIER price for ITEM" — capture what's AFTER "for"
            # Handles: "best price for vegimax", "competitors price for vegimax 30ml",
            #          "cheapest price for cabbage", "market price for maize"
            # Must run BEFORE the greedy (.+)\s+price pattern.
            (r"(?:best|cheapest|lowest|highest|market|retail|wholesale|competitor[s]?|current|latest|going)\s+(?:price|cost|rate|bei|gharama)\s+(?:for|of|ya)\s+(.+)", "price"),
            (r"(?:tell me|show me|get me)\s+(?:the )?price\s+(?:of|for)?\s*(.+)", "price"),
            (r"(?:what does|how much does)\s+(.+)\s+(?:cost|sell for)", "price"),
            # Greedy catch-all: "ITEM price/cost" where item is BEFORE price word.
            # Non-greedy (.+?) so it stops at the first space before price/cost.
            (r"^(.+?)\s+(?:price|cost|bei|gharama)(?:\s+for\s+\S+)?$", "price"),
            (r"(?:expensive|cheap|costly)\s+(.+)", "price"),
        ]

        # Stock-related patterns — require "of/for" before the item to
        # avoid capturing generic words from "show me stock levels" etc.
        self.stock_patterns = [
            (r"(?:stock|inventory|available|hisa|viwango|idadi)\s+(?:of|for|ya|za)\s+(.+)", "stock"),
            (r"(?:how many|quantity of)\s+(.+)\s+(?:do we have|is available|zilizopo)", "stock"),
            (r"(?:is there|do we have)\s+(.+)\s+(?:in stock|available)", "stock"),
            (r"(?:check|look up)\s+(?:stock of|inventory for)\s+(.+)", "stock"),
            (r"(.+)\s+(?:stock|inventory|hisa)", "stock"),
        ]

        # =========================================================
        # INVOICE PATTERNS
        # =========================================================
        self.invoice_patterns = [
            (r"(?:show|list|get|view|display)\s+(?:ar|sales|customer)?\s*invoices?\s*(?:for\s+([A-Za-z0-9\s]+))?", "ar_invoices"),
            (r"(?:overdue|past due|late)\s+invoices?\s*(?:for\s+([A-Za-z0-9\s]+))?", "overdue_invoices"),
            (r"(?:customer\s+balance|balance\s+for|what does)\s+([A-Za-z0-9\s]+)\s+owe", "customer_balance"),
            (r"(?:send|email)\s+(?:payment\s+)?reminder\s+(?:to|for)\s+([A-Za-z0-9\s]+)", "payment_reminder"),
            (r"(?:aging|invoice aging)\s+report", "aging_report"),
            (r"(?:who\s+owes|outstanding\s+payments|unpaid\s+bills)", "overdue_invoices"),
        ]

        # =========================================================
        # PURCHASE PATTERNS - LOWER PRIORITY
        # =========================================================
        self.purchase_patterns = [
            (r"^(?:show|list|get)\s+(?:purchase\s+)?orders?\s*(?:for\s+([A-Za-z0-9\s]+))?$", "purchase_orders"),
            (r"create\s+(?:a\s+)?purchase\s+order\s+(?:for\s+)?([A-Za-z0-9\s]+)(?:\s+with\s+|\s+containing\s+)(.+)", "create_purchase_order"),
            (r"create\s+purchase\s+order$", "create_purchase_order"),
            (r"(?:show|list|get)\s+(?:purchase\s+)?requests?", "purchase_requests"),
            (r"(?:goods|stock)\s+receipt\s+(?:for\s+po\s+)?(\d+)", "goods_receipt"),
            (r"approve\s+(?:purchase\s+)?order\s+(\d+)", "approve_purchase_order"),
        ]

        # =========================================================
        # INVENTORY MOVEMENT PATTERNS
        # =========================================================
        self.inventory_movement_patterns = [
            (r"create\s+(?:a\s+)?(?:goods|stock)\s+issue\s+(?:from\s+)?([A-Z0-9]+)?\s+for\s+(.+)", "goods_issue"),
            (r"create\s+(?:a\s+)?(?:goods|stock)\s+receipt\s+(?:from\s+po\s+(\d+)|for\s+(.+))", "goods_receipt"),
            (r"transfer\s+stock\s+from\s+([A-Z0-9]+)\s+to\s+([A-Z0-9]+)\s+for\s+(.+)", "stock_transfer"),
            (r"(?:what|which)\s+needs\s+reordering", "reorder_report"),
            (r"(?:allocate|reserve)\s+stock\s+for\s+order\s+(\d+)", "allocate_stock"),
            (r"inventory\s+valuation|stock\s+value|worth\s+of\s+inventory", "inventory_valuation"),
        ]

        # =========================================================
        # DOCUMENT TRANSITION PATTERNS
        # =========================================================
        self.document_transition_patterns = [
            (r"convert\s+(?:quotation|quote)\s+(\d+)\s+to\s+(?:order|sales order)", "convert_quotation"),
            (r"convert\s+it\s+to\s+order", "convert_quotation"),
            (r"post\s+invoice\s+for\s+delivery\s+(\d+)", "post_invoice"),
            (r"post\s+the\s+invoice", "post_invoice"),
            (r"cancel\s+(?:order|quotation|purchase order)\s+(\d+)", "cancel_document"),
            (r"reverse\s+(?:goods receipt|transfer)\s+(\d+)", "reverse_document"),
        ]

        # =========================================================
        # BUSINESS RULES PATTERNS
        # =========================================================
        self.business_rules_patterns = [
            (r"check\s+credit\s+limit\s+for\s+([A-Za-z0-9\s]+)", "credit_limit"),
            (r"(?:is|check)\s+stock\s+available\s+for\s+(.+)", "stock_availability"),
            (r"(?:does|can)\s+([A-Za-z0-9\s]+)\s+need\s+approval", "approval_check"),
        ]

        # Churn risk / Customer health patterns (HIGH PRIORITY)
        self.churn_risk_patterns = [
            (r"(?:show|customer|list|get|find)\s+customers?\s+(?:at|with|having)?\s+(?:churn\s+risk|churn risk|risk)", "customer_health"),
            (r"(?:who|customers)\s+(?:is|are)\s+(?:likely|about)\s+to\s+(?:leave|churn)", "customer_health"),
            (r"(?:customer\s+health|health\s+score|health\s+check)", "customer_health"),
            (r"(?:churn\s+analysis|churn\s+prediction|churn\s+alert)", "customer_health"),
            (r"(?:high|medium|low)\s+risk\s+customers?", "customer_health"),
            (r"wateja\s+walio\s+katika\s+hatari", "customer_health"),
            (r"afya\s+ya\s+wateja", "customer_health"),
        ]

        # Warehouse-related patterns
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
            "GET_ITEM_PRICE":             "price of",
            "GET_STOCK_LEVELS":           "stock of",
            "GET_LOW_STOCK":              "low stock alerts",
            "GET_ITEM_DETAILS":           "item details of",
            "GET_TOP_SELLING_ITEMS":      "top selling items",
            "GET_SLOW_MOVING_ITEMS":      "slow moving items",
            "GET_OUTSTANDING_DELIVERIES": "outstanding deliveries",
            "TRACK_DELIVERY":             "track delivery",
            "CREATE_QUOTATION":           "create quotation for",
            "GET_CUSTOMERS":              "show customers",
            "GET_CUSTOMER_HEALTH":        "show customers at churn risk",
            "GET_CUSTOMER_ORDERS":        "customer orders for",
            "GET_WAREHOUSES":             "show warehouses",
            "FIND_CUSTOMERS_BY_ITEM":     "customers who buy",
            "GET_AR_INVOICES":            "show invoices",
            "GET_OVERDUE_INVOICES":       "overdue invoices",
            "GET_CUSTOMER_BALANCE":       "customer balance for",
            "SEND_PAYMENT_REMINDER":      "send reminder to",
            "GET_PURCHASE_ORDERS":        "purchase orders",
            "CREATE_PURCHASE_ORDER":      "create purchase order for",
            "GET_REORDER_REPORT":         "what needs reordering",
            "CREATE_STOCK_TRANSFER":      "transfer stock",
            "CONVERT_QUOTATION_TO_ORDER": "convert quotation to order",
            "POST_INVOICE":               "post invoice for",
        }

    # =========================================================
    # PUBLIC ENTRY POINT
    # =========================================================

    def rewrite(self, message: str) -> Tuple[str, str, Optional[dict]]:
        """
        Rewrite query and extract structured information.

        Priority ladder (first match wins, short-circuits the rest):
          0a. Conversational queries     → GREETING
          0b. Low-stock alert queries    → GET_LOW_STOCK
          0c. Item detail queries        → GET_ITEM_DETAILS
          0d. Price queries              → GET_ITEM_PRICE
          1.  Protected patterns         → GET_CUSTOMER_HEALTH
          2.  Invoice patterns
          3.  Purchase patterns
          4.  Inventory movement
          5.  Document transitions
          6.  Business rules
          7.  Warehouse patterns
          8.  Misspelling fix
          9.  _detect_intent_and_extract (inner rules)
          10. _rewrite_for_intent
          11. _pattern_based_rewrite
          12. Query cleanup

        Returns:
            (rewritten_message, detected_intent, extracted_entities)
        """
        original = message
        message_lower = message.lower().strip()

        # =================================================================
        # STEP 0a: CONVERSATIONAL / GREETING QUERIES
        # Must run before ANY price or item extraction.
        # This prevents "Tell me about yourself" from being treated as a price query.
        # =================================================================
        for pattern in _CONVERSATIONAL_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                logger.info(f"Conversational pattern detected: '{original}' → GREETING")
                return original, "GREETING", {}

        # Also check for variations of conversational queries
        conversational_variations = [
            "tell me about yourself", "who are you", "what are you",
            "introduce yourself", "about you", "what is your name",
            "who made you", "who created you", "what do you do",
            "how can you help me", "what are your capabilities",
            "your features", "about yourself", "tell me more about yourself",
            "explain yourself", "what is your purpose", "how do you work",
            "what can you do", "help me understand you", "tell me about you",
            "what's your name", "whats your name", "who are you?"
        ]
        for variation in conversational_variations:
            if variation in message_lower:
                logger.info(f"Conversational variation detected: '{original}' → GREETING")
                return original, "GREETING", {}

        # =================================================================
        # STEP 0b: LOW-STOCK ALERT QUERIES
        # Must run before stock/price patterns so "low" is never treated
        # as an item name (e.g. "Low stock alerts" → item_name="low").
        # =================================================================
        for pattern in _LOW_STOCK_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                logger.info(f"Low-stock pattern: '{original}' → GET_LOW_STOCK")
                return original, "GET_LOW_STOCK", {}

        # =================================================================
        # STEP 0c: ITEM DETAIL QUERIES
        # Must run before customer_rules sees "details of X", otherwise
        # "show item details of Cap Measuring" is stolen as customer_name.
        # =================================================================
        for pattern in _ITEM_DETAIL_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                item_name = match.group(1).strip()
                logger.info(f"Item detail pattern: '{original}' → GET_ITEM_DETAILS (item: {item_name})")
                return f"item details of {item_name}", "GET_ITEM_DETAILS", {"item_name": item_name}

        # =================================================================
        # STEP 0c-2: ITEM LISTING / BROWSE QUERIES
        # "show me 10 items", "list all products", "browse inventory" etc.
        # Must run before price/stock patterns so "10" is never mistaken for
        # part of a price query, and before context resolution so item_name
        # is never inherited from the previous turn for a generic browse.
        # =================================================================
        for _pat, _has_qty in _LISTING_PATTERNS:
            _m = re.search(_pat, message_lower, re.IGNORECASE)
            if _m:
                _qty = None
                if _has_qty and _m.lastindex and _m.group(1):
                    _qty = int(_m.group(1))
                _list_entities: dict = {"_is_listing": True}
                if _qty:
                    _list_entities["quantity"] = _qty
                logger.info(
                    f"Item listing pattern: '{original}' → GET_ITEMS "
                    f"(qty={_qty}, _is_listing=True)"
                )
                return original, "GET_ITEMS", _list_entities

        # =================================================================
        # STEP 0d: PRICE QUERIES
        # =================================================================
        for pattern, _ in self.price_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                item_name = self._extract_item_name(match.group(1) if match.groups() else message)
                if item_name:
                    extracted_entities = {"item_name": item_name}
                    logger.info(f"Price pattern: '{original}' → GET_ITEM_PRICE (item: {item_name})")
                    return f"price of {item_name}", "GET_ITEM_PRICE", extracted_entities

        # Step 1: PROTECTED patterns (churn risk — cannot be overridden by anything)
        for patterns, intent_type in [(self.churn_risk_patterns, "GET_CUSTOMER_HEALTH")]:
            for pattern, _ in patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    logger.info(f"Protected pattern: '{original}' → {intent_type}")
                    return original, intent_type, {}

        # Step 2: INVOICE patterns
        for pattern, inv_type in self.invoice_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                entities = {}
                if match.groups() and match.group(1):
                    entities["customer_name"] = self._extract_customer_name(match.group(1))
                if inv_type == "overdue_invoices":
                    return f"overdue invoices for {entities.get('customer_name', '')}".strip(), "GET_OVERDUE_INVOICES", entities
                elif inv_type == "customer_balance":
                    return f"customer balance for {entities.get('customer_name', '')}".strip(), "GET_CUSTOMER_BALANCE", entities
                elif inv_type == "payment_reminder":
                    return f"send reminder to {entities.get('customer_name', '')}".strip(), "SEND_PAYMENT_REMINDER", entities
                elif inv_type == "aging_report":
                    return "aging report", "GET_AGING_REPORT", {}
                else:
                    return f"show invoices for {entities.get('customer_name', '')}".strip(), "GET_AR_INVOICES", entities

        # Step 3: PURCHASE patterns
        for pattern, po_type in self.purchase_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                entities = {}
                if po_type == "create_purchase_order" and match.groups():
                    if len(match.groups()) >= 2:
                        entities["vendor_name"] = self._extract_customer_name(match.group(1))
                        entities["items_raw"] = match.group(2)
                    elif match.groups():
                        entities["vendor_name"] = self._extract_customer_name(match.group(1))
                    return message, "CREATE_PURCHASE_ORDER", entities
                elif po_type == "purchase_orders" and match.groups() and match.group(1):
                    entities["vendor_name"] = self._extract_customer_name(match.group(1))
                    return f"purchase orders for {entities['vendor_name']}", "GET_PURCHASE_ORDERS", entities
                elif po_type == "purchase_requests":
                    return "purchase requests", "GET_PURCHASE_REQUESTS", {}
                elif po_type == "goods_receipt" and match.groups():
                    entities["po_num"] = match.group(1)
                    return f"goods receipt for po {entities['po_num']}", "GET_GOODS_RECEIPT_PO", entities
                elif po_type == "approve_purchase_order" and match.groups():
                    entities["po_num"] = match.group(1)
                    return f"approve purchase order {entities['po_num']}", "APPROVE_PURCHASE_ORDER", entities
                else:
                    return "purchase orders", "GET_PURCHASE_ORDERS", {}

        # Step 4: INVENTORY MOVEMENT patterns
        for pattern, inv_type in self.inventory_movement_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                entities = {}
                if inv_type == "goods_issue" and match.groups():
                    if len(match.groups()) >= 2:
                        entities["warehouse"] = match.group(1) if match.group(1) else "MAIN"
                        entities["items_raw"] = match.group(2)
                    return message, "CREATE_GOODS_ISSUE", entities
                elif inv_type == "goods_receipt":
                    if match.groups():
                        if match.group(1):
                            entities["po_num"] = match.group(1)
                            return f"create goods receipt for po {entities['po_num']}", "CREATE_GOODS_RECEIPT", entities
                        elif match.group(2):
                            entities["items_raw"] = match.group(2)
                    return message, "CREATE_GOODS_RECEIPT", entities
                elif inv_type == "stock_transfer" and len(match.groups()) >= 3:
                    entities["from_warehouse"] = match.group(1)
                    entities["to_warehouse"] = match.group(2)
                    entities["items_raw"] = match.group(3)
                    return message, "CREATE_STOCK_TRANSFER", entities
                elif inv_type == "reorder_report":
                    return "what needs reordering", "GET_REORDER_REPORT", {}
                elif inv_type == "allocate_stock" and match.groups():
                    entities["order_num"] = match.group(1)
                    return f"allocate stock for order {entities['order_num']}", "ALLOCATE_STOCK", entities
                elif inv_type == "inventory_valuation":
                    return "inventory valuation", "GET_INVENTORY_VALUATION", {}

        # Step 5: DOCUMENT TRANSITION patterns
        for pattern, trans_type in self.document_transition_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                entities = {}
                if trans_type == "convert_quotation":
                    if match.groups() and match.group(1):
                        entities["doc_num"] = match.group(1)
                    return message, "CONVERT_QUOTATION_TO_ORDER", entities
                elif trans_type == "post_invoice":
                    if match.groups() and match.group(1):
                        entities["doc_num"] = match.group(1)
                    return message, "POST_INVOICE", entities
                elif trans_type == "cancel_document" and match.groups():
                    entities["doc_num"] = match.group(1)
                    return f"cancel document {entities['doc_num']}", "CANCEL_DOCUMENT", entities
                elif trans_type == "reverse_document" and match.groups():
                    entities["doc_num"] = match.group(1)
                    return f"reverse document {entities['doc_num']}", "REVERSE_DOCUMENT", entities

        # Step 6: BUSINESS RULES patterns
        for pattern, rule_type in self.business_rules_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                entities = {}
                if rule_type == "credit_limit" and match.groups():
                    entities["customer_name"] = self._extract_customer_name(match.group(1))
                    return f"check credit limit for {entities['customer_name']}", "CHECK_CREDIT_LIMIT", entities
                elif rule_type == "stock_availability" and match.groups():
                    entities["item_name"] = self._extract_item_name(match.group(1))
                    return f"check stock availability for {entities['item_name']}", "CHECK_STOCK_AVAILABILITY", entities

        # Step 7: WAREHOUSE patterns
        for pattern, _ in self.warehouse_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return "show warehouses?", "GET_WAREHOUSES", {}

        # Step 8: Fix misspellings
        rewritten = self._fix_misspellings(message)

        # Step 9: Rule-based intent + entity detection
        detected_intent, extracted_entities = self._detect_intent_and_extract(rewritten)

        # Step 10: Rewrite to standard phrase
        if detected_intent:
            rewritten = self._rewrite_for_intent(rewritten, detected_intent, extracted_entities)

        # Step 11: Pattern-based fallback
        if not detected_intent:
            detected_intent, rewritten, extracted_entities = self._pattern_based_rewrite(rewritten)

        # Step 12: Clean up
        rewritten = self._clean_query(rewritten)

        if rewritten != original:
            logger.info(f"Query rewritten: '{original}' → '{rewritten}' (intent: {detected_intent})")

        return rewritten, detected_intent, extracted_entities

    # =========================================================
    # INTERNAL HELPERS
    # =========================================================

    def _fix_misspellings(self, text: str) -> str:
        result = text.lower()
        for wrong, correct in self.misspellings.items():
            if wrong in result:
                result = result.replace(wrong, correct)
        return result

    def _detect_intent_and_extract(self, text: str) -> Tuple[Optional[str], dict]:
        """Inner rule-based intent + entity detection (runs after Steps 0-7)."""
        text_lower = text.lower()
        entities = {}

        # ================================================================
        # FIX: Check conversational queries again
        # ================================================================
        for pattern in _CONVERSATIONAL_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return "GREETING", entities

        # Churn risk — highest priority inside this method too
        for pattern, _ in self.churn_risk_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return "GET_CUSTOMER_HEALTH", entities

        # Low-stock — check again in case query was misspelling-corrected
        for pattern in _LOW_STOCK_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return "GET_LOW_STOCK", {}

        # Item details — check again after misspelling correction
        for pattern in _ITEM_DETAIL_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return "GET_ITEM_DETAILS", {"item_name": match.group(1).strip()}

        # Price queries
        for pattern, _ in self.price_patterns:
            match = re.search(pattern, text_lower)
            if match:
                entities["item_name"] = self._extract_item_name(match.group(1))
                if entities["item_name"]:
                    return "GET_ITEM_PRICE", entities

        # Stock queries — only when captured word is a real item name
        for pattern, _ in self.stock_patterns:
            match = re.search(pattern, text_lower)
            if match:
                candidate = self._extract_item_name(match.group(1) if match.groups() else text)
                if candidate and candidate.lower().strip() not in _NON_ITEM_WORDS:
                    entities["item_name"] = candidate
                    return "GET_STOCK_LEVELS", entities
                if re.search(r'\b(?:stock|inventory)\b', text_lower):
                    return "GET_STOCK_LEVELS", {}

        # Delivery queries
        for pattern, delivery_type in self.delivery_patterns:
            match = re.search(pattern, text_lower)
            if match:
                if delivery_type == "outstanding_deliveries":
                    return "GET_OUTSTANDING_DELIVERIES", entities
                elif delivery_type in ("delivery", "delivery_status"):
                    if match.groups() and match.group(1):
                        entities["delivery_number"] = match.group(1)
                    return "TRACK_DELIVERY", entities

        # Top/slow selling
        for pattern, _ in self.top_selling_patterns:
            if re.search(pattern, text_lower):
                return "GET_TOP_SELLING_ITEMS", entities

        for pattern, _ in self.slow_moving_patterns:
            if re.search(pattern, text_lower):
                return "GET_SLOW_MOVING_ITEMS", entities

        # Quotation
        for pattern, _ in self.quotation_patterns:
            match = re.search(pattern, text_lower)
            if match:
                if match.groups():
                    entities["customer_name"] = self._extract_customer_name(match.group(1))
                return "CREATE_QUOTATION", entities

        # Customer queries
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

    # Size token pattern — matches "30ml", "1l", "500g", "2kg", "125ml" etc.
    _SIZE_TOKEN_RE = re.compile(
        r"^\d+(?:\.\d+)?\s*(?:ml|l(?![a-zA-Z])|lt|g(?![a-zA-Z])|kg|gm|pcs?|units?|x(?![a-zA-Z]))",
        re.IGNORECASE,
    )

    def _extract_item_name(self, text: str) -> Optional[str]:
        if not text:
            return None
        text = text.strip()

        # Try known-item patterns first.
        # FIX: after matching the base name, also capture a trailing size token
        # ("vegimax 30ml" → "vegimax" matched by pattern, then "30ml" appended).
        for pattern in self.item_extraction:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                base = match.group(0)
                # Check for a size token immediately after the matched name
                remainder = text[match.end():].strip()
                size_match = self._SIZE_TOKEN_RE.match(remainder)
                if size_match:
                    return f"{base} {size_match.group(0).strip()}"
                return base

        filler_words = {
            "the", "a", "an", "of", "for", "to", "in", "at",
            "with", "about", "tell", "me", "show", "get",
            "levels", "level", "all", "alerts", "alert",
            "summary", "overview", "report", "list",
        }
        # Keep size tokens even though they look like non-words
        words = text.split()
        cleaned = []
        for w in words:
            if self._SIZE_TOKEN_RE.match(w):
                cleaned.append(w)          # always keep size tokens
            elif w.lower() not in filler_words:
                cleaned.append(w)

        if cleaned:
            result = " ".join(cleaned[:4]).strip()  # up to 4 tokens for "brand size"
            if result.lower() in _NON_ITEM_WORDS:
                return None
            return result
        return None

    def _extract_customer_name(self, text: str) -> Optional[str]:
        if not text:
            return None
        remove_words = {"a", "quotation", "quote", "for", "with", "the", "and", "new"}
        words = text.split()
        cleaned = [w for w in words if w.lower() not in remove_words]
        return " ".join(cleaned[:2]) if cleaned else None

    def _rewrite_for_intent(self, text: str, intent: str, entities: dict) -> str:
        standard_phrase = self.intent_phrases.get(intent, "")

        if intent == "GET_ITEM_PRICE" and entities.get("item_name"):
            return f"{standard_phrase} {entities['item_name']}"
        if intent == "GET_STOCK_LEVELS" and entities.get("item_name"):
            return f"{standard_phrase} {entities['item_name']}"
        if intent == "GET_LOW_STOCK":
            return standard_phrase
        if intent == "GET_ITEM_DETAILS" and entities.get("item_name"):
            return f"{standard_phrase} {entities['item_name']}"
        if intent == "GET_CUSTOMER_ORDERS" and entities.get("customer_name"):
            return f"{standard_phrase} {entities['customer_name']}"
        if intent == "GET_CUSTOMER_BALANCE" and entities.get("customer_name"):
            return f"{standard_phrase} {entities['customer_name']}"
        if intent == "SEND_PAYMENT_REMINDER" and entities.get("customer_name"):
            return f"{standard_phrase} {entities['customer_name']}"
        if intent == "CREATE_PURCHASE_ORDER" and entities.get("vendor_name"):
            return f"{standard_phrase} {entities['vendor_name']}"
        if intent in ("CREATE_QUOTATION", "GET_CUSTOMER_HEALTH",
                      "CONVERT_QUOTATION_TO_ORDER", "POST_INVOICE",
                      "CREATE_STOCK_TRANSFER", "CREATE_GOODS_ISSUE", "CREATE_GOODS_RECEIPT"):
            return text
        return text

    def _pattern_based_rewrite(self, text: str) -> Tuple[Optional[str], str, dict]:
        text_lower = text.lower()
        entities = {}

        # ================================================================
        # FIX: Check conversational queries in pattern-based fallback
        # ================================================================
        for pattern in _CONVERSATIONAL_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return "GREETING", text, entities

        # Low-stock check first — belt-and-suspenders for this method
        for pattern in _LOW_STOCK_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return "GET_LOW_STOCK", self.intent_phrases["GET_LOW_STOCK"], {}

        # Item detail check — belt-and-suspenders
        for pattern in _ITEM_DETAIL_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                item_name = match.group(1).strip()
                return "GET_ITEM_DETAILS", f"item details of {item_name}", {"item_name": item_name}

        # "what is..." patterns
        if text_lower.startswith("what is") or text_lower.startswith("what's"):
            if "price" in text_lower or "cost" in text_lower:
                item = self._extract_item_name(text_lower.replace("what is", "").replace("what's", ""))
                if item:
                    return "GET_ITEM_PRICE", f"price of {item}", {"item_name": item}
            if "stock" in text_lower or "available" in text_lower:
                item = self._extract_item_name(text_lower)
                if item:
                    return "GET_STOCK_LEVELS", f"stock of {item}", {"item_name": item}
            if "overdue" in text_lower or "invoice" in text_lower:
                return "GET_OVERDUE_INVOICES", "overdue invoices", {}

        # "how many/much" patterns
        if text_lower.startswith("how many") or text_lower.startswith("how much"):
            if "stock" in text_lower or "available" in text_lower or "left" in text_lower:
                item = self._extract_item_name(text_lower)
                if item:
                    return "GET_STOCK_LEVELS", f"stock of {item}", {"item_name": item}
            if "price" in text_lower or "cost" in text_lower:
                item = self._extract_item_name(text_lower)
                if item:
                    return "GET_ITEM_PRICE", f"price of {item}", {"item_name": item}

        # "show / view / list / display / see" patterns
        if re.match(r'^(?:show(?:\s+me)?|view|list|display|see)\b', text_lower):
            rest = re.sub(r'^(?:show(?:\s+me)?|view|list|display|see)\s*', '', text_lower).strip()

            if "churn risk" in rest or "customer health" in rest or "at risk" in rest:
                return "GET_CUSTOMER_HEALTH", text, {}
            if "invoice" in rest:
                if "overdue" in rest:
                    return "GET_OVERDUE_INVOICES", "overdue invoices", {}
                return "GET_AR_INVOICES", "show invoices", {}
            if "purchase order" in rest or "po" in rest:
                return "GET_PURCHASE_ORDERS", "purchase orders", {}
            if "warehouse" in rest or "warehouses" in rest:
                return "GET_WAREHOUSES", "show warehouses", {}
            if "price" in rest:
                item = self._extract_item_name(rest)
                if item:
                    return "GET_ITEM_PRICE", f"price of {item}", {"item_name": item}
            if "stock" in rest or "inventory" in rest:
                item = self._extract_item_name(rest)
                if item and item.lower() not in _NON_ITEM_WORDS:
                    return "GET_STOCK_LEVELS", f"stock of {item}", {"item_name": item}
                return "GET_STOCK_LEVELS", text, {}
            if "customer" in rest or "customers" in rest:
                return "GET_CUSTOMERS", "show customers", {}
            if "order" in rest or "orders" in rest:
                customer = self._extract_customer_name(rest)
                if customer:
                    return "GET_CUSTOMER_ORDERS", f"customer orders for {customer}", {"customer_name": customer}

        # "tell me about" patterns
        if text_lower.startswith("tell me about"):
            topic = text_lower.replace("tell me about", "").strip()
            # Check if it's conversational
            if topic in ["yourself", "you", "yourself?", "you?"]:
                return "GREETING", text, entities
            item = self._extract_item_name(topic)
            if item:
                return "GET_ITEM_PRICE", f"price of {item}", {"item_name": item}

        return None, text, entities

    def _clean_query(self, text: str) -> str:
        text = re.sub(r'\s+', ' ', text).strip()
        if not text.endswith(('?', '.', '!')):
            text += '?'
        return text

    def expand_query(self, query: str) -> List[str]:
        variations = [query]
        if "price of" in query:
            item = query.replace("price of", "").strip()
            variations += [f"how much is {item}", f"what does {item} cost", f"{item} price"]
        if "stock of" in query:
            item = query.replace("stock of", "").strip()
            variations += [f"how many {item} in stock", f"inventory of {item}", f"{item} available"]
        direct = re.sub(r'^(what|how|where|when|why|tell me|show me|can you)\s+', '', query.lower())
        if direct != query.lower():
            variations.append(direct)
        return list(set(variations))


# Singleton instance
_query_rewriter = None


def get_query_rewriter() -> QueryRewriter:
    global _query_rewriter
    if _query_rewriter is None:
        _query_rewriter = QueryRewriter()
    return _query_rewriter