"""Constants for action router"""

# ============================================================================
# INTENT CLASSIFICATION
# ============================================================================

ACTION_ROUTER_INTENTS = {
    "GET_ITEMS",
    "GET_SELLABLE_ITEMS",
    "GET_PURCHASABLE_ITEMS",
    "GET_INVENTORY_ITEMS",
    "GET_ITEMS_ADVANCED",
    "GET_ITEM_DETAILS",
    "GET_STOCK_LEVELS",
    "GET_CUSTOMERS",
    "GET_CUSTOMER_DETAILS",
    "GET_CUSTOMER_HEALTH",
    "GET_CUSTOMER_ORDERS",
    "GET_CUSTOMER_INVOICES",
    "GET_OUTSTANDING_INVOICES",
    "FIND_CUSTOMERS_BY_ITEM",
    "GET_ITEM_PRICE",
    "GET_CUSTOMER_PRICE",
    "CREATE_QUOTATION",
    "GET_QUOTATIONS",
    "FOLLOW_UP_QUOTATIONS",
    "GET_OUTSTANDING_DELIVERIES",
    "TRACK_DELIVERY",
    "GET_DELIVERY_HISTORY",
    "RECOMMEND_ITEMS",
    "RECOMMEND_CUSTOMERS",
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
    "GET_TOP_SELLING_ITEMS",
    "GET_SLOW_MOVING_ITEMS",
    "GET_SALES_ANALYTICS",
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "ANALYZE_CUSTOMER_BEHAVIOR",
    "FORECAST_DEMAND",
    "GET_WAREHOUSES",
    "GET_WAREHOUSE_STOCK",
    "GET_LOW_STOCK_ALERTS",
    "COMPANY_INFO",
    "PRODUCT_INFO",
    "HOW_TO_ORDER",
    "PAYMENT_METHODS",
    "CONTACT_INFO",
    "POLICY_QUESTION",
    "FAQ",
}

DATA_INTENTS = ACTION_ROUTER_INTENTS.copy()

OPERATIONAL_INTENTS = {
    "CREATE_QUOTATION",
}

RECOMMENDATION_INTENTS = {
    "RECOMMEND_ITEMS",
    "RECOMMEND_CUSTOMERS",
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
    "FIND_CUSTOMERS_BY_ITEM",
}

PRICE_INTENTS = {"GET_ITEM_PRICE", "GET_CUSTOMER_PRICE"}
DELIVERY_INTENTS = {"GET_OUTSTANDING_DELIVERIES", "TRACK_DELIVERY", "GET_DELIVERY_HISTORY"}
CUSTOMER_INTENTS = {
    "GET_CUSTOMERS",
    "GET_CUSTOMER_DETAILS",
    "GET_CUSTOMER_ORDERS",
    "GET_CUSTOMER_HEALTH",
    "GET_CUSTOMER_INVOICES",
    "GET_OUTSTANDING_INVOICES",
    "FIND_CUSTOMERS_BY_ITEM",
}
INVENTORY_INTENTS = {"GET_STOCK_LEVELS", "GET_LOW_STOCK_ALERTS", "GET_WAREHOUSE_STOCK"}
ANALYTICS_INTENTS = {"GET_TOP_SELLING_ITEMS", "GET_SLOW_MOVING_ITEMS", "GET_SALES_ANALYTICS"}

# ============================================================================
# SKIP PATTERNS FOR ITEM FILTERING
# ============================================================================

SKIP_GROUPS = {
    "seed", "seeds", "packet", "packets", "kg", "g", "gm", "gram", "grams",
    "bottle", "bottles", "ml", "l", "liter", "liters", "litre", "litres",
    "carton", "cartons", "box", "boxes", "bag", "bags", "sachet", "sachets",
    "tin", "tins", "can", "cans", "bunch", "bunches", "piece", "pieces",
    "kgs", "kgm", "gms", "gramm", "kgms", "kilo", "kilos", "kilogram", "kilograms",
    "local", "imported", "premium", "standard", "economy", "value", "basic",
}

# FIXED: tuple instead of set so str.startswith() works directly.
# item_handler.py uses `any(code.startswith(p) for p in SKIP_PREFIXES)` — still works.
# pricing_handler.py uses `code.startswith(SKIP_PREFIXES)` — now works too.
SKIP_PREFIXES = (
    "0001", "0011", "0111", "fg", "fgop", "fghy", "fgpu", "kavgx", "kavg",
    "kav", "kamg", "rmmb", "rm", "raw", "pack", "pkg", "item", "prod",
    "leysco-", "leysco_", "leysco", "agri-", "agri_", "agri",
)

# ============================================================================
# RESPONSE TEMPLATES
# ============================================================================

GREETING_RESPONSES = {
    "en": [
        "Hello! How can I help you today?",
        "Hi there! What can I do for you?",
        "Greetings! How may I assist you?",
        "Hello! What would you like to know?",
    ],
    "sw": [
        "Habari! Naweza kukusaidia vipi?",
        "Hujambo! Nini ninaweza kukufanyia?",
        "Shikamoo! Naweza kukusaidiaje?",
        "Habari! Unataka kujua nini?",
    ],
}

SMALL_TALK_RESPONSES = {
    "en": {
        "how are you": "I'm doing great, thank you for asking! How can I help you today?",
        "what's up": "Not much, just here to help you with your business needs!",
        "good morning": "Good morning! Hope you're having a great day. What can I help you with?",
        "good afternoon": "Good afternoon! How can I assist you today?",
        "good evening": "Good evening! I'm here if you need any help.",
        "thank you": "You're very welcome! Let me know if there's anything else.",
        "thanks": "You're welcome! Happy to help.",
        "ok": "Great! Let me know what you need.",
        "cool": "Awesome! What can I do for you?",
        "nice": "Glad you think so! How can I assist you?",
        "great": "Wonderful! What would you like to know?",
        "awesome": "Thanks! Let me know what you need help with.",
    },
    "sw": {
        "how are you": "Nimezuri, asante kwa kuuliza! Naweza kukusaidia vipi leo?",
        "what's up": "Sijambo, niko hapa kukusaidia na mahitaji yako ya biashara!",
        "good morning": "Habari za asubuhi! Natumai una siku njema. Naweza kukusaidia nini?",
        "good afternoon": "Habari za mchana! Naweza kukusaidia vipi leo?",
        "good evening": "Habari za jioni! Niko hapa kama unahitaji msaada wowote.",
        "thank you": "Karibu sana! Niambi kama kuna kitu kingine.",
        "thanks": "Karibu! Nimefurahi kusaidia.",
        "ok": "Sawa! Niambie unachohitaji.",
        "cool": "Nzuri! Ninaweza kukufanyia nini?",
        "nice": "Nzuri! Naweza kukusaidia vipi?",
        "great": "Nzuri sana! Ungependa kujua nini?",
        "awesome": "Asante! Niambie unahitaji msaada gani.",
    },
}

# ============================================================================
# ERROR MESSAGES
# ============================================================================

ERROR_MESSAGES = {
    "en": {
        "auth_failed": "Sorry, I couldn't authenticate with the server. Please check your credentials.",
        "no_data": "No data found for your request.",
        "invalid_item": "I couldn't find that item. Please check the item name and try again.",
        "invalid_customer": "I couldn't find that customer. Please check the customer name and try again.",
        "api_error": "Sorry, I encountered an error while processing your request. Please try again later.",
        "permission_denied": "You don't have permission to perform this action.",
        "network_error": "Network error. Please check your connection and try again.",
        "timeout_error": "The request timed out. Please try again.",
        "rate_limit": "Too many requests. Please wait a moment and try again.",
    },
    "sw": {
        "auth_failed": "Samahani, sikuweza kuthibitisha na seva. Tafadhali angalia hati zako.",
        "no_data": "Hakuna data iliyopatikana kwa ombi lako.",
        "invalid_item": "Sikuweza kupata bidhaa hiyo. Tafadhali angalia jina la bidhaa na ujaribu tena.",
        "invalid_customer": "Sikuweza kupata mteja huyo. Tafadhali angalia jina la mteja na ujaribu tena.",
        "api_error": "Samahani, nilikumbana na hitilafu wakati wa kuchakata ombi lako. Tafadhali jaribu tena baadaye.",
        "permission_denied": "Huna ruhusa ya kufanya kitendo hiki.",
        "network_error": "Hitilafu ya mtandao. Tafadhali angalia muunganisho wako na ujaribu tena.",
        "timeout_error": "Ombi limechukua muda mrefu. Tafadhali jaribu tena.",
        "rate_limit": "Maombi mengi sana. Tafadhali subiri kidogo na ujaribu tena.",
    },
}

# ============================================================================
# SUCCESS MESSAGES
# ============================================================================

SUCCESS_MESSAGES = {
    "en": {
        "quotation_created": "✓ Quotation created successfully!",
        "order_created": "✓ Sales order created successfully!",
        "price_retrieved": "✓ Price retrieved successfully.",
        "stock_retrieved": "✓ Stock information retrieved.",
        "delivery_tracked": "✓ Delivery information retrieved.",
    },
    "sw": {
        "quotation_created": "✓ Nukuu imeundwa kwa mafanikio!",
        "order_created": "✓ Oda ya mauzo imeundwa kwa mafanikio!",
        "price_retrieved": "✓ Bei imepatikana kwa mafanikio.",
        "stock_retrieved": "✓ Taarifa za hisa zimepatikana.",
        "delivery_tracked": "✓ Taarifa za usafirishaji zimepatikana.",
    },
}

# ============================================================================
# VALIDATION CONSTANTS
# ============================================================================

MIN_QUANTITY = 1
MAX_QUANTITY = 99999
MIN_PRICE = 0
MAX_PRICE = 999999999
MIN_DAYS = 1
MAX_DAYS = 365
MIN_LIMIT = 1
MAX_LIMIT = 100

DEFAULT_LIMIT = 10
DEFAULT_DAYS = 30
DEFAULT_ANALYSIS_DAYS = 90
DEFAULT_TURNOVER_THRESHOLD = 0.5