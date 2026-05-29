"""
intent_classifier.py - Optimized with async support, caching, and fast-path
Enhanced with natural language understanding for conversational queries
Enhanced with Swahili language detection and multilingual support
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

_SWAHILI_GREETINGS = {
    "mambo", "habari", "sasa", "vipi", "jambo", "hujambo", "sijambo",
    "shikamoo", "marahaba", "poa", "fresh", "nzuri", "salama", "njema", "noma"
}

_SWAHILI_WORDS = {
    "naomba", "tafadhali", "asante", "samahani", "karibu", "kwaheri",
    "sawa", "ndio", "hapana", "unauza", "bei", "ghali", "nafuu", "huduma",
    "hisa", "ghala", "maghala", "mteja", "wateja", "oda", "nukuu", "bidhaa",
    "unauza", "nanunua", "kipimo", "kiasi", "sana", "kidogo", "ngapi"
}

_SWAHILI_QUESTION_PHRASES = {
    "lipo?", "iko?", "wapi?", "ngapi?", "gani?", "lini?", "kwanini?"
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

_CHURN_RISK_PHRASES = {
    "churn risk", "churning", "at risk", "risk of leaving",
    "customer health", "health score", "unhealthy customers",
    "likely to leave", "likely to churn", "churn prediction",
    "churn analysis", "churn alert", "churn warning",
    "customers at risk", "risk customers", "high risk customers",
    "medium risk customers", "low risk customers", "health check",
    "customer health check", "health report", "customer wellbeing",
    "churn score", "attrition risk", "loyalty risk",
    "wateja walio katika hatari", "hatari ya kuondoka", "afya ya mteja"
}

TOP_SELLING_PHRASES = {
    "top selling", "best selling", "most popular", "top items",
    "bestsellers", "best sellers", "most sold", "highest selling",
    "top 5", "top 10", "top 15", "top 20", "top products",
    "what sells most", "popular items", "fast moving", "fastest selling",
    "top performing", "best performers", "hot items", "trending products",
    "most purchased", "frequently bought", "high volume", "best movers",
    "what's popular", "what are people buying", "customers are buying",
    "selling like hotcakes", "flying off the shelves",
    "bidhaa zinazouzwa sana", "zinazouzwa zaidi", "maarufu"
}

SLOW_MOVING_PHRASES = {
    "slow moving", "slow selling", "least popular", "worst selling",
    "lowest selling", "slowest selling", "dead stock", "obsolete",
    "not selling", "poorly selling", "slow items", "slow products",
    "dormant stock", "stagnant", "low turnover", "inactive items",
    "non moving", "non-moving", "excess stock", "surplus",
    "gathering dust", "not moving", "sitting on shelves", "hard to sell",
    "zinazosonga polepole", "hazijauzwa", "haziuZiki", "zimelala"
}

SALES_ANALYTICS_PHRASES = {
    "sales analytics", "sales analysis", "sales report", "sales data",
    "sales overview", "sales summary", "sales performance", "sales metrics",
    "sales statistics", "sales insights", "sales trends", "sales dashboard",
    "show sales", "view sales", "sales figures", "revenue report",
    "revenue analytics", "sales breakdown", "sales by period", "sales summary",
    "sales performance report", "monthly sales", "weekly sales", "daily sales",
    "yearly sales", "quarterly sales", "sales by category", "sales by product",
    "sales history", "sales record", "transaction report", "sales totals",
    "total sales", "gross sales", "net sales", "sales volume",
    "uchambuzi wa mauzo", "ripoti ya mauzo", "mauzo kwa mwezi"
}

_INVOICE_PHRASES = {
    "ar invoice", "customer invoice", "sales invoice", "receivable invoice",
    "show invoices", "list invoices", "get invoices", "view invoices",
    "overdue invoices", "past due invoices", "late invoices", "unpaid invoices",
    "invoice aging", "aging report", "invoice balance", "customer balance",
    "send reminder", "payment reminder", "follow up payment",
    "who owes money", "outstanding payments", "unpaid bills",
    "invoice za wateja", "baki ya invoice", "malipo yaliyochelewa"
}

_PURCHASE_PHRASES = {
    "purchase order", "buy order", "supplier order", "vendor order",
    "create po", "make purchase order", "new purchase order",
    "purchase request", "requisition", "buy request",
    "goods receipt", "gr po", "receive goods", "stock in",
    "ap invoice", "supplier invoice", "vendor invoice", "payable invoice",
    "approve po", "authorize purchase", "po approval",
    "agizo la ununuzi", "mapokezi ya bidhaa", "invoice ya muuzaji"
}
# NOTE: bare "po" removed from _PURCHASE_PHRASES — too short, causes false matches
# on phrases like "customer details for..." when Groq sees "po" in its context.

_INVENTORY_MOVEMENT_PHRASES = {
    "goods issue", "issue stock", "stock out", "dispatch goods",
    "goods receipt", "receive stock", "stock in", "goods in",
    "stock transfer", "move stock", "transfer inventory", "warehouse transfer",
    "allocate stock", "reserve stock", "hold stock",
    "inventory valuation", "stock value", "inventory worth",
    "reorder report", "what to reorder", "low stock report",
    "utoaji wa bidhaa", "upokaji wa bidhaa", "uhamisho wa hisa"
}

_DOCUMENT_TRANSITION_PHRASES = {
    "convert quotation", "quote to order", "turn quote into order",
    "post invoice", "invoice delivery", "bill delivery",
    "cancel document", "void document", "reverse document",
    "approve purchase order", "authorize po"
}

_STOCK_LEVELS_GENERAL_PHRASES = {
    "stock levels", "show stock levels", "show me stock levels",
    "view stock levels", "display stock levels", "get stock levels",
    "stock overview", "stock summary", "stock report", "stock status",
    "current stock", "all stock", "inventory levels", "inventory overview",
    "inventory summary", "inventory report", "inventory status",
    "what's in stock", "what is in stock", "show stock", "view stock",
    "display stock", "get stock", "check stock", "stock check",
    "how much stock", "stock on hand", "available stock", "stock availability",
    "hisa zote", "hisa za maghala yote", "hisa ya bidhaa"
}

_COMMON_PRODUCTS = [
    "cabbage", "tomato", "maize", "pepper", "cauliflower", "onion",
    "vegimax", "easeed", "tosheka", "kh500", "mh401", "snowball",
    "yolo wonder", "seed", "seeds", "fertilizer", "pesticide"
]

# ---------------------------------------------------------------------------
# CUSTOMER DETAIL PATTERNS
# Used by _check_direct_intents as the very first guard so queries like
# "customer details for Mahakali Enterprises" are never misrouted to
# GET_PURCHASE_ORDERS by the LLM.
# ---------------------------------------------------------------------------
_CUSTOMER_DETAIL_PATTERNS = [
    r'customer\s+details?\s+for\s+',
    r'details?\s+(?:for|of|about)\s+(?:the\s+)?customer\s+',
    r'show\s+(?:me\s+)?(?:the\s+)?customer\s+details?\s+(?:for|of)\s+',
    r'tell\s+me\s+(?:more\s+)?about\s+(?:the\s+)?customer\s+',
    r'info(?:rmation)?\s+(?:on|about|for)\s+(?:the\s+)?customer\s+',
    r'get\s+(?:me\s+)?(?:the\s+)?customer\s+details?\s+(?:for|of)\s+',
    r'customer\s+info(?:rmation)?\s+(?:for|on|about)\s+',
    r'maelezo\s+ya\s+mteja\s+',          # Swahili: "details of customer"
    r'taarifa\s+ya\s+mteja\s+',           # Swahili: "info of customer"
]

FAST_PATH_PATTERNS = [
    # =========================================================
    # ITEM BROWSING PATTERNS
    # =========================================================
    (r'^(?:show|list|display|view|get|browse|find|fetch|see|check|pull\s+up|look\s+up|search\s+for|explore)\s+me\s+(?:all\s+)?(?:items|products|inventory|stock)$', "GET_ITEMS"),
    (r'^(?:show|list|display|view|get|browse|find|fetch|see|check|pull\s+up|look\s+up|search\s+for|explore)\s+(?:all\s+)?(?:items|products|inventory|stock|available\s+items|sellable\s+items)$', "GET_ITEMS"),
    (r'^(?:items|products|inventory|stock|what\s+do\s+you\s+have|what\s+is\s+available)$', "GET_ITEMS"),
    (r'^what\s+(?:items|products|stock)\s+(?:are|do\s+you\s+have|is\s+available|are\s+available)\?*$', "GET_ITEMS"),
    (r'^tell\s+me\s+about\s+(?:your\s+)?(?:items|products|inventory)$', "GET_ITEMS"),
    (r'^show\s+me\s+(?:the\s+)?(?:items|products|inventory)$', "GET_ITEMS"),
    (r'^list\s+(?:all\s+)?(?:items|products|inventory)$', "GET_ITEMS"),

    # =========================================================
    # INVOICE PATTERNS
    # =========================================================
    (r'^(?:show|list|get|view|display)\s+(?:ar|sales|customer)?\s*invoices?$', "GET_AR_INVOICES"),
    (r'^(?:overdue|past due|late)\s+invoices?$', "GET_OVERDUE_INVOICES"),
    (r'^(?:what|show me)\s+(?:is\s+the\s+)?(?:customer\s+balance|balance\s+for)\s+(?:of\s+)?([A-Za-z0-9\s]+)$', "GET_CUSTOMER_BALANCE"),
    (r'^(?:send|email)\s+(?:payment\s+)?reminder\s+(?:to|for)\s+([A-Za-z0-9\s]+)$', "SEND_PAYMENT_REMINDER"),
    (r'^(?:aging|invoice aging)\s+report$', "GET_AGING_REPORT"),

    # =========================================================
    # PURCHASE PATTERNS
    # =========================================================
    (r'^(?:show|list|get)\s+(?:purchase\s+)?orders?\s*(?:for\s+([A-Za-z0-9\s]+))?$', "GET_PURCHASE_ORDERS"),
    (r'^create\s+(?:a\s+)?purchase\s+order\s+(?:for\s+)?([A-Za-z0-9\s]+)(?:\s+with\s+|\s+containing\s+)(.+)$', "CREATE_PURCHASE_ORDER"),
    (r'^create\s+purchase\s+order$', "CREATE_PURCHASE_ORDER"),
    (r'^(?:show|list|get)\s+(?:purchase\s+)?requests?$', "GET_PURCHASE_REQUESTS"),
    (r'^(?:goods|stock)\s+receipt\s+(?:for\s+po\s+)?(\d+)$', "GET_GOODS_RECEIPT_PO"),
    (r'^approve\s+(?:purchase\s+)?order\s+(\d+)$', "APPROVE_PURCHASE_ORDER"),

    # =========================================================
    # INVENTORY MOVEMENT PATTERNS
    # =========================================================
    (r'^create\s+(?:a\s+)?(?:goods|stock)\s+issue\s+(?:from\s+)?([A-Z0-9]+)?\s+for\s+(.+)$', "CREATE_GOODS_ISSUE"),
    (r'^create\s+(?:a\s+)?(?:goods|stock)\s+receipt\s+(?:from\s+po\s+(\d+)|for\s+(.+))$', "CREATE_GOODS_RECEIPT"),
    (r'^transfer\s+stock\s+from\s+([A-Z0-9]+)\s+to\s+([A-Z0-9]+)\s+for\s+(.+)$', "CREATE_STOCK_TRANSFER"),
    (r'^what\s+needs\s+reordering$', "GET_REORDER_REPORT"),
    (r'^(?:allocate|reserve)\s+stock\s+for\s+order\s+(\d+)$', "ALLOCATE_STOCK"),

    # =========================================================
    # DOCUMENT TRANSITION PATTERNS
    # =========================================================
    (r'^convert\s+(?:quotation|quote)\s+(\d+)\s+to\s+(?:order|sales order)$', "CONVERT_QUOTATION_TO_ORDER"),
    (r'^convert\s+it\s+to\s+order$', "CONVERT_QUOTATION_TO_ORDER"),
    (r'^post\s+invoice\s+for\s+delivery\s+(\d+)$', "POST_INVOICE"),
    (r'^post\s+the\s+invoice$', "POST_INVOICE"),

    # =========================================================
    # BUSINESS RULES PATTERNS
    # =========================================================
    (r'^check\s+credit\s+limit\s+for\s+([A-Za-z0-9\s]+)$', "CHECK_CREDIT_LIMIT"),
    (r'^(?:is|check)\s+stock\s+available\s+for\s+(.+)$', "CHECK_STOCK_AVAILABILITY"),

    # =========================================================
    # STOCK LEVELS GENERAL
    # =========================================================
    (r'^(?:show|view|display|get|check)\s+(?:me\s+)?(?:the\s+)?stock\s+levels?\s*$', "GET_STOCK_LEVELS"),
    (r'^(?:stock|inventory)\s+(?:levels?|overview|summary|report|status|check)\s*$', "GET_STOCK_LEVELS"),
    (r'^(?:what(?:\'s| is)\s+)?(?:the\s+)?(?:current\s+)?stock\s+(?:levels?|status|overview)\s*$', "GET_STOCK_LEVELS"),
    (r'^(?:how\s+much\s+)?stock\s+(?:do\s+we\s+have|is\s+there|is\s+available)\s*$', "GET_STOCK_LEVELS"),
    (r'^(?:all|overall|general)\s+stock\s+(?:levels?|overview)\s*$', "GET_STOCK_LEVELS"),
    (r'^(?:onyesha|angalia|tazama)\s+(?:hisa|stock)\s+(?:zote|yote)?\s*$', "GET_STOCK_LEVELS"),
    (r'^hisa\s+(?:za|ya|kwa)?\s*$', "GET_STOCK_LEVELS"),

    # =========================================================
    # CHURN RISK PATTERNS
    # =========================================================
    (r'(?:show|list|get|view|display)\s+(?:customers|wateja)\s+(?:at|with|having)\s+(?:churn|churn risk|risk|customer health)', "GET_CUSTOMER_HEALTH"),
    (r'(?:churn\s+risk|customer\s+health|health\s+score).*(?:customers|wateja)', "GET_CUSTOMER_HEALTH"),
    (r'^(?:show|list|get)\s+(?:me\s+)?(?:the\s+)?(?:customer health|churn risk)\s*(?:report|analysis)?$', "GET_CUSTOMER_HEALTH"),
    (r'customers?\s+(?:at|with)\s+risk\s+(?:of\s+)?(?:churn|leaving)', "GET_CUSTOMER_HEALTH"),
    (r'who\s+is\s+(?:likely|about)\s+to\s+(?:leave|churn)', "GET_CUSTOMER_HEALTH"),
    (r'(?:high|medium|low)\s+risk\s+customers', "GET_CUSTOMER_HEALTH"),
    (r'wateja\s+walio\s+katika\s+hatari', "GET_CUSTOMER_HEALTH"),
    (r'afya\s+ya\s+mteja', "GET_CUSTOMER_HEALTH"),

    # =========================================================
    # Swahili greeting patterns
    # =========================================================
    (r'^(?:mambo|habari|sasa|vipi|jambo|hujambo|shikamoo|poa)(?:\s|$)', "GREETING", "sw"),
    (r'^(?:nzuri|salama|njema|sawa|fresh)(?:\s|$)', "GREETING", "sw"),

    # =========================================================
    # Quotation creation patterns
    # =========================================================
    (r'^create\s+(?:a\s+)?quotation\s+(?:for\s+)?([A-Za-z0-9\s]+)(?:\s+with\s+|\s+containing\s+|\s+including\s+)(.+)', "CREATE_QUOTATION"),
    (r'^make\s+(?:a\s+)?quotation\s+(?:for\s+)?([A-Za-z0-9\s]+)(?:\s+with\s+|\s+containing\s+)(.+)', "CREATE_QUOTATION"),
    (r'^new\s+quotation\s+(?:for\s+)?([A-Za-z0-9\s]+)(?:\s+with\s+)(.+)', "CREATE_QUOTATION"),
    (r'^quotation\s+(?:for\s+)?([A-Za-z0-9\s]+)(?:\s+with\s+|\s+for\s+)(.+)', "CREATE_QUOTATION"),
    (r'^(?:cash sale|cash sale -)\s+([A-Za-z0-9\s]+)(?:\s+with\s+)(.+)', "CREATE_QUOTATION"),
    (r'^create\s+quotation$', "CREATE_QUOTATION"),
    (r'^make\s+quotation$', "CREATE_QUOTATION"),
    (r'^unda\s+(?:nukuu|quote)\s+(?:kwa|ya|kwa ajili ya)?\s*([A-Za-z0-9\s]+)', "CREATE_QUOTATION"),
    (r'^nukuu\s+(?:mpya)?\s*(?:kwa)?\s*([A-Za-z0-9\s]+)', "CREATE_QUOTATION"),

    # =========================================================
    # Company Info
    # =========================================================
    (r'^(?:tell me about|what is|about)\s+leysco\s*$', "COMPANY_INFO"),
    (r'^(?:tell me about|what is|about)\s+the\s+company\s*$', "COMPANY_INFO"),
    (r'^company\s+(?:info|information|details|profile)\s*$', "COMPANY_INFO"),
    (r'^what\s+is\s+leysco\s*$', "COMPANY_INFO"),
    (r'^who\s+is\s+leysco\s*$', "COMPANY_INFO"),
    (r'^about\s+leysco\s*$', "COMPANY_INFO"),

    # =========================================================
    # Top Selling & Analytics
    # =========================================================
    (r'^(?:show|get|list)\s+(?:top|best)\s+(?:selling|sellers)\s+(?:items|products)$', "GET_TOP_SELLING_ITEMS"),
    (r'^(?:top|best)\s+(\d+)\s+(?:selling|sellers)\s+(?:items|products)$', "GET_TOP_SELLING_ITEMS"),
    (r'^(?:show|get|list)\s+(?:slow|least)\s+(?:moving|selling)\s+(?:items|products)$', "GET_SLOW_MOVING_ITEMS"),

    # =========================================================
    # Sales Analytics & Reporting
    # =========================================================
    (r'^(?:show|get|view|display)\s+(?:sales|revenue)\s+(?:analytics|analysis|report|data|overview|summary)$', "GET_SALES_ANALYTICS"),
    (r'^(?:sales|revenue)\s+(?:analytics|analysis|report|data|overview|summary)$', "GET_SALES_ANALYTICS"),
    (r'^show\s+sales$', "GET_SALES_ANALYTICS"),
    (r'^sales\s+(?:performance|metrics|statistics|insights|trends)$', "GET_SALES_ANALYTICS"),
    (r'^(?:monthly|weekly|daily|yearly|quarterly)\s+sales$', "GET_SALES_ANALYTICS"),
    (r'^(?:what|show me)\s+(?:are\s+)?(?:my\s+)?(?:total|gross|net)\s+sales$', "GET_SALES_ANALYTICS"),

    # Price patterns
    (r'^(price|bei)\s+(of|ya)?\s*([a-zA-Z0-9\-\(\)\s]+)$', "GET_ITEM_PRICE"),
    (r'^(stock|hisa)\s+(level|kiwango)?\s*(for|of|ya)?\s*([a-zA-Z0-9\-\(\)\s]{3,})$', "GET_STOCK_LEVELS"),
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

    # Conversational greetings (English)
    (r'^(?:hi|hello|hey|good morning|good afternoon|good evening|howdy|sup|yo)(?:\s|$)', "GREETING", "en"),

    # Conversational greetings (Swahili)
    (r'^(?:jambo|habari|mambo|sasa|vipi|hujambo|shikamoo|poa|fresh)(?:\s|$)', "GREETING", "sw"),

    (r'^(?:thanks|thank you|appreciate it|nice one|good one|asante|shukran)(?:\s|$)', "THANKS"),

    # Help queries
    (r'^(?:help|what can you do|how do i use this|capabilities|what do you do)(?:\s|\?)?$', "FAQ"),
    (r'^(?:msaada|unaweza kufanya nini|unafanya nini|uwezo wako)(?:\s|\?)?$', "FAQ"),

    # Warehouse queries
    (r'^(?:show|list|where are).*(?:warehouses?|maghala|storage|depots?)$', "GET_WAREHOUSES"),
    (r'^(?:what|which).*(?:warehouses?|maghala).*(?:have|has|stock|hisa).*(?:for|of|ya)\s+([a-zA-Z0-9\-\(\)\s]+)$', "GET_WAREHOUSE_STOCK"),
    (r'^(?:onyesha|orodhesha|wapi)\s+(?:maghala|warehouses|ghala)\s*$', "GET_WAREHOUSES"),

    # Low stock alerts
    (r'^(?:what|which).*(?:low|critical|danger).*(?:stock|inventory|hisa|items|bidhaa).*(?:alert|alerts?|warning|arifa)$', "GET_LOW_STOCK_ALERTS"),
    (r'^(?:what\'?s|what is).*(?:low|running low|almost out)$', "GET_LOW_STOCK_ALERTS"),
    (r'^(?:arifa|onyo)\s+(?:za|la)\s+hisa\s+chini$', "GET_LOW_STOCK_ALERTS"),
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
        self._fast_path_cache = {}

    # -------------------------------------------------------------------------
    # LANGUAGE DETECTION
    # -------------------------------------------------------------------------
    def _detect_language(self, message: str) -> str:
        """Detect if the message is in Swahili or English."""
        message_lower = message.lower().strip()

        swahili_score = 0
        english_score = 0

        for greeting in _SWAHILI_GREETINGS:
            if greeting in message_lower:
                swahili_score += 3

        for word in _SWAHILI_WORDS:
            if word in message_lower:
                swahili_score += 1

        for phrase in _SWAHILI_QUESTION_PHRASES:
            if phrase in message_lower:
                swahili_score += 2

        english_indicators = ["the", "this", "that", "these", "those", "please", "help", "show", "list"]
        for word in english_indicators:
            if word in message_lower:
                english_score += 1

        if len(message_lower.split()) <= 3:
            for greeting in _SWAHILI_GREETINGS:
                if greeting == message_lower or message_lower.startswith(greeting):
                    return "sw"

        if swahili_score > english_score and swahili_score >= 2:
            return "sw"
        elif english_score > swahili_score:
            return "en"
        else:
            return "en"

    # -------------------------------------------------------------------------
    # DIRECT INTENT CHECK FOR COMMON PHRASES
    # -------------------------------------------------------------------------
    def _check_direct_intents(self, message: str) -> Optional[Tuple[str, dict, str]]:
        """Direct pattern matching for common phrases before LLM."""
        message_lower = message.lower().strip()
        language = self._detect_language(message)

        # =====================================================================
        # FIX: Customer detail queries MUST be checked first.
        # Without this guard, queries like "customer details for Mahakali
        # Enterprises" fall through to the purchase phrase check (or the LLM),
        # which incorrectly returns GET_PURCHASE_ORDERS.
        # =====================================================================
        for pattern in _CUSTOMER_DETAIL_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                logger.info(f"Direct intent match (customer detail): '{message}' → GET_CUSTOMER_DETAILS")
                return ("GET_CUSTOMER_DETAILS", {}, language)

        # Check for invoice queries
        if any(phrase in message_lower for phrase in _INVOICE_PHRASES):
            if "overdue" in message_lower or "past due" in message_lower:
                return ("GET_OVERDUE_INVOICES", {}, language)
            if "balance" in message_lower:
                return ("GET_CUSTOMER_BALANCE", {}, language)
            if "reminder" in message_lower:
                return ("SEND_PAYMENT_REMINDER", {}, language)
            return ("GET_AR_INVOICES", {}, language)

        # Check for purchase queries
        if any(phrase in message_lower for phrase in _PURCHASE_PHRASES):
            if "create" in message_lower or "make" in message_lower or "new" in message_lower:
                return ("CREATE_PURCHASE_ORDER", {}, language)
            if "approve" in message_lower:
                return ("APPROVE_PURCHASE_ORDER", {}, language)
            if "request" in message_lower:
                return ("GET_PURCHASE_REQUESTS", {}, language)
            if "receipt" in message_lower:
                return ("GET_GOODS_RECEIPT_PO", {}, language)
            return ("GET_PURCHASE_ORDERS", {}, language)

        # Check for inventory movement queries
        if any(phrase in message_lower for phrase in _INVENTORY_MOVEMENT_PHRASES):
            if "transfer" in message_lower or "move" in message_lower:
                return ("CREATE_STOCK_TRANSFER", {}, language)
            if "issue" in message_lower or "dispatch" in message_lower:
                return ("CREATE_GOODS_ISSUE", {}, language)
            if "receipt" in message_lower or "receive" in message_lower:
                return ("CREATE_GOODS_RECEIPT", {}, language)
            if "reorder" in message_lower:
                return ("GET_REORDER_REPORT", {}, language)
            if "allocate" in message_lower or "reserve" in message_lower:
                return ("ALLOCATE_STOCK", {}, language)

        # Check for document transitions
        if any(phrase in message_lower for phrase in _DOCUMENT_TRANSITION_PHRASES):
            if "convert" in message_lower and "quotation" in message_lower:
                return ("CONVERT_QUOTATION_TO_ORDER", {}, language)
            if "post" in message_lower and "invoice" in message_lower:
                return ("POST_INVOICE", {}, language)
            if "approve" in message_lower and "purchase" in message_lower:
                return ("APPROVE_PURCHASE_ORDER", {}, language)

        # Direct check for item browsing
        browse_patterns = [
            r'^(?:show|list|display|view|get|browse|find|fetch|see|check)\s+me\s+(?:all\s+)?(?:items|products|inventory|stock)',
            r'^(?:show|list|display|view|get|browse|find|fetch|see|check)\s+(?:all\s+)?(?:items|products|inventory|stock|available\s+items)',
            r'^what\s+items\s+do\s+you\s+have',
            r'^what\s+products\s+are\s+available',
            r'^tell\s+me\s+about\s+(?:your\s+)?(?:items|products)',
            r'^items$',
            r'^products$',
            r'^show\s+me\s+(?:the\s+)?(?:items|products)',
            r'^list\s+items$',
        ]

        for pattern in browse_patterns:
            if re.search(pattern, message_lower, re.IGNORECASE):
                logger.info(f"Direct intent match: '{message}' → GET_ITEMS")
                return ("GET_ITEMS", {}, language)

        # Check for greetings
        if any(w in message_lower for w in _SWAHILI_GREETINGS):
            return ("GREETING", {}, "sw")

        if any(w in message_lower for w in ["hi", "hello", "hey", "good morning", "good afternoon"]):
            return ("GREETING", {}, "en")

        return None

    # -------------------------------------------------------------------------
    # FAST-PATH DETECTION (No LLM)
    # -------------------------------------------------------------------------
    def _try_fast_path(self, message: str) -> Optional[Tuple[str, dict, str]]:
        """Try to classify using fast-path patterns (no LLM call)."""
        message_lower = message.lower().strip()

        cache_key = f"fast_path:{message_lower}"
        if cache_key in self._fast_path_cache:
            return self._fast_path_cache[cache_key]

        detected_language = self._detect_language(message)

        for phrase in _STOCK_LEVELS_GENERAL_PHRASES:
            if phrase in message_lower:
                result = ("GET_STOCK_LEVELS", {}, detected_language)
                self._fast_path_cache[cache_key] = result
                return result

        for pattern_tuple in FAST_PATH_PATTERNS:
            if len(pattern_tuple) == 2:
                pattern, intent = pattern_tuple
                pattern_lang = None
            else:
                pattern, intent, pattern_lang = pattern_tuple

            if pattern_lang and pattern_lang != detected_language and detected_language != "en":
                continue

            match = re.match(pattern, message_lower, re.IGNORECASE)
            if match:
                entities = {}
                groups = match.groups()

                if intent == "CREATE_QUOTATION" and len(groups) >= 2:
                    entities["customer_name"] = groups[0].strip()
                elif intent == "CREATE_PURCHASE_ORDER" and len(groups) >= 2:
                    entities["vendor_name"] = groups[0].strip()
                elif intent == "GET_CUSTOMER_BALANCE" and groups:
                    entities["customer_name"] = groups[0].strip()
                elif intent == "SEND_PAYMENT_REMINDER" and groups:
                    entities["customer_name"] = groups[0].strip()
                elif intent == "CONVERT_QUOTATION_TO_ORDER" and groups:
                    entities["doc_num"] = groups[0].strip()
                elif intent == "POST_INVOICE" and groups:
                    entities["doc_num"] = groups[0].strip()
                elif intent == "APPROVE_PURCHASE_ORDER" and groups:
                    entities["doc_num"] = groups[0].strip()
                elif intent == "CREATE_STOCK_TRANSFER" and len(groups) >= 3:
                    entities["from_warehouse"] = groups[0].strip()
                    entities["to_warehouse"] = groups[1].strip()

                result = (intent, entities, detected_language)
                self._fast_path_cache[cache_key] = result
                return result

        return None

    # -------------------------------------------------------------------------
    # SAFE JSON PARSER
    # -------------------------------------------------------------------------
    def _extract_json(self, text: str) -> dict | None:
        """Safely extract JSON from LLM response."""
        try:
            if not text or not text.strip():
                return None

            clean_text = text.strip()

            try:
                return json.loads(clean_text)
            except json.JSONDecodeError:
                pass

            json_match = re.search(r'\{[^{}]*\}', clean_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0).strip()
                json_str = json_str.replace(',}', '}')
                json_str = json_str.replace(', ]', ']')

                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    intent_match = re.search(r'"intent"\s*:\s*"([^"]+)"', json_str)
                    if intent_match:
                        intent_value = intent_match.group(1).strip()
                        if intent_value in _VALID_INTENTS_SET:
                            return {"intent": intent_value}

            for intent in _VALID_INTENTS_SET:
                if re.search(rf'\b{intent}\b', clean_text, re.IGNORECASE):
                    return {"intent": intent}

            return None
        except Exception as e:
            logger.warning(f"JSON extraction error: {e}")
            return None

    # -------------------------------------------------------------------------
    # RULE-BASED INTENT ENGINE
    # -------------------------------------------------------------------------
    @lru_cache(maxsize=512)
    def _rule_based_intent(self, text: str) -> str:
        """Cached rule-based intent detection."""
        text = text.lower().strip()

        # Customer detail check first (mirrors _check_direct_intents priority)
        for pattern in _CUSTOMER_DETAIL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "GET_CUSTOMER_DETAILS"

        # Invoice intents
        if any(phrase in text for phrase in _INVOICE_PHRASES):
            if "overdue" in text:
                return "GET_OVERDUE_INVOICES"
            if "balance" in text:
                return "GET_CUSTOMER_BALANCE"
            return "GET_AR_INVOICES"

        # Purchase intents
        if any(phrase in text for phrase in _PURCHASE_PHRASES):
            if "create" in text or "make" in text:
                return "CREATE_PURCHASE_ORDER"
            if "request" in text:
                return "GET_PURCHASE_REQUESTS"
            if "receipt" in text:
                return "GET_GOODS_RECEIPT_PO"
            if "approve" in text:
                return "APPROVE_PURCHASE_ORDER"
            return "GET_PURCHASE_ORDERS"

        # Inventory movement intents
        if any(phrase in text for phrase in _INVENTORY_MOVEMENT_PHRASES):
            if "transfer" in text:
                return "CREATE_STOCK_TRANSFER"
            if "issue" in text:
                return "CREATE_GOODS_ISSUE"
            if "receipt" in text:
                return "CREATE_GOODS_RECEIPT"
            if "reorder" in text:
                return "GET_REORDER_REPORT"
            return "CREATE_GOODS_RECEIPT"

        # Document transitions
        if "convert" in text and "quotation" in text:
            return "CONVERT_QUOTATION_TO_ORDER"
        if "post" in text and "invoice" in text:
            return "POST_INVOICE"

        # Item browsing
        browse_keywords = ['browse', 'show', 'list', 'view', 'display', 'get', 'see', 'check']
        if any(kw in text for kw in browse_keywords) and any(t in text for t in ['items', 'products', 'inventory', 'stock']):
            return "GET_ITEMS"

        if text in ['items', 'products', 'inventory', 'stock', 'list', 'show']:
            return "GET_ITEMS"

        if any(phrase in text for phrase in _STOCK_LEVELS_GENERAL_PHRASES):
            return "GET_STOCK_LEVELS"

        if any(phrase in text for phrase in _CHURN_RISK_PHRASES):
            return "GET_CUSTOMER_HEALTH"

        if 'quotation' in text or 'quote' in text or 'nukuu' in text:
            if any(w in text for w in ['create', 'make', 'generate', 'prepare', 'new', 'unda', 'mpya']):
                return "CREATE_QUOTATION"

        if any(p in text for p in TOP_SELLING_PHRASES):
            return "GET_TOP_SELLING_ITEMS"

        if any(p in text for p in SALES_ANALYTICS_PHRASES):
            return "GET_SALES_ANALYTICS"

        if any(p in text for p in SLOW_MOVING_PHRASES):
            return "GET_SLOW_MOVING_ITEMS"

        if any(p in text for p in ['price', 'cost', 'bei', 'how much', 'gharama']):
            if re.search(r'(?:for|kwa|ya)\s+([A-Za-z][A-Za-z\s]+)$', text):
                return "GET_CUSTOMER_PRICE"
            return "GET_ITEM_PRICE"

        if any(w in text for w in _SWAHILI_GREETINGS):
            return "GREETING"

        if any(w in text for w in ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]):
            return "GREETING"

        return "UNKNOWN"

    # -------------------------------------------------------------------------
    # CLARIFICATION SUGGESTIONS
    # -------------------------------------------------------------------------
    def _clarify_suggestions(self, text: str, language: str = "en") -> list[str]:
        sw = language == "sw"

        if sw:
            return ["Angalia bei ya bidhaa", "Angalia hisa", "Unda nukuu", "Onyesha wateja", "Bidhaa zinazouzwa sana"]
        return ["Check item price", "Check stock levels", "Create a quotation", "Show customers", "Top selling items"]

    # -------------------------------------------------------------------------
    # MAIN CLASSIFIER
    # -------------------------------------------------------------------------
    def classify(self, user_message: str) -> dict:
        """Sync classification."""
        return asyncio.run(self.classify_async(user_message))

    async def classify_async(self, user_message: str) -> dict:
        """Async intent classification."""
        text_lower = user_message.lower().strip()
        detected_language = self._detect_language(user_message)
        logger.info(f"🌐 Language detected: {detected_language.upper()} for: '{user_message[:50]}'")
        language = detected_language

        # Step 1: Check cache
        cache_key = f"intent:{user_message}:{language}"
        cached = await cache_service.get_simple_async(cache_key)
        if cached:
            return cached

        # Step 2: Direct intent check (bypass LLM for common phrases)
        direct_result = self._check_direct_intents(user_message)
        if direct_result:
            intent, entities, direct_lang = direct_result
            result = _result(intent=intent, language=direct_lang, confidence=_CONF["fast_path"], entities=entities)
            await cache_service.set_simple_async(cache_key, result, ttl=300)
            logger.info(f"🎯 Final intent: {result['intent']} (confidence: {result['confidence']}, lang: {direct_lang})")
            return result

        # Step 3: Try fast-path patterns
        fast_path_result = self._try_fast_path(user_message)
        if fast_path_result:
            intent, entities, fp_language = fast_path_result
            final_language = fp_language if fp_language else language
            result = _result(intent=intent, language=final_language, confidence=_CONF["fast_path"], entities=entities)
            await cache_service.set_simple_async(cache_key, result, ttl=300)
            logger.info(f"🎯 Final intent: {result['intent']} (confidence: {result['confidence']}, lang: {final_language})")
            return result

        # Step 4: Rule-based fallback
        rule_intent = self._rule_based_intent(user_message)
        if rule_intent != "UNKNOWN":
            result = _result(intent=rule_intent, language=language, confidence=_CONF["rule_fallback"])
            await cache_service.set_simple_async(cache_key, result, ttl=300)
            logger.info(f"🎯 Final intent: {result['intent']} (confidence: {result['confidence']}, lang: {language})")
            return result

        # Step 5: AI classification (only if all rule-based methods failed)
        try:
            prompt = self.prompt_manager.get_intent_prompt(user_message)
            response = await self.llm.generate_async(prompt)

            if response and response.strip():
                data = self._extract_json(response)
                if data:
                    ai_intent = data.get("intent", "").strip().upper()
                    if ai_intent in _VALID_INTENTS_SET:
                        result = _result(intent=ai_intent, language=language, confidence=_CONF["ai_clean"])
                        await cache_service.set_simple_async(cache_key, result, ttl=300)
                        logger.info(f"🎯 Final intent: {result['intent']} (confidence: {result['confidence']}, lang: {language})")
                        return result
        except Exception as e:
            logger.warning(f"LLM intent failed: {e}")

        # Final fallback
        suggestions = self._clarify_suggestions(user_message, language)
        result = _result(intent="CLARIFY", language=language, confidence=0.30, alternatives=suggestions)
        await cache_service.set_simple_async(cache_key, result, ttl=60)
        logger.info(f"🎯 Final intent: {result['intent']} (confidence: {result['confidence']}, lang: {language})")
        return result

    async def classify_batch(self, messages: list[str]) -> list[dict]:
        """Classify multiple messages in parallel."""
        tasks = [self.classify_async(msg) for msg in messages]
        return await asyncio.gather(*tasks)


# Singleton instance
intent_classifier = IntentClassifier()