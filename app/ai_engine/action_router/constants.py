"""Constants for action router"""

# ============================================================================
# INTENT CLASSIFICATION
# ============================================================================

ACTION_ROUTER_INTENTS = {
    # Existing - Items
    "GET_ITEMS",
    "GET_SELLABLE_ITEMS",
    "GET_PURCHASABLE_ITEMS",
    "GET_INVENTORY_ITEMS",
    "GET_ITEMS_ADVANCED",
    "GET_ITEM_DETAILS",
    "GET_STOCK_LEVELS",
    
    # Existing - Customers
    "GET_CUSTOMERS",
    "GET_CUSTOMER_DETAILS",
    "GET_CUSTOMER_HEALTH",
    "GET_CUSTOMER_ORDERS",
    "GET_CUSTOMER_INVOICES",
    "GET_OUTSTANDING_INVOICES",
    "FIND_CUSTOMERS_BY_ITEM",
    
    # Existing - Pricing
    "GET_ITEM_PRICE",
    "GET_CUSTOMER_PRICE",
    
    # Existing - Quotations
    "CREATE_QUOTATION",
    "GET_QUOTATIONS",
    "FOLLOW_UP_QUOTATIONS",
    "CONVERT_QUOTATION_TO_ORDER",      # NEW: Convert quotation to sales order
    "POST_INVOICE",                    # NEW: Post AR invoice from delivery
    
    # Existing - Deliveries
    "GET_OUTSTANDING_DELIVERIES",
    "TRACK_DELIVERY",
    "GET_DELIVERY_HISTORY",
    
    # NEW - Invoice Management
    "GET_AR_INVOICES",
    "GET_AP_INVOICES",
    "GET_OVERDUE_INVOICES",
    "GET_CUSTOMER_BALANCE",
    "GET_PAYMENT_STATUS",
    "SEND_PAYMENT_REMINDER",
    "GET_AGING_REPORT",
    
    # NEW - Purchase Cycle
    "GET_PURCHASE_ORDERS",
    "CREATE_PURCHASE_ORDER",
    "GET_PURCHASE_REQUESTS",
    "GET_GOODS_RECEIPT_PO",
    "APPROVE_PURCHASE_ORDER",
    "GET_AP_INVOICES_PURCHASE",
    
    # NEW - Inventory Movements
    "CREATE_GOODS_ISSUE",
    "CREATE_GOODS_RECEIPT",
    "CREATE_STOCK_TRANSFER",
    "GET_INVENTORY_VALUATION",
    "GET_REORDER_REPORT",
    "ALLOCATE_STOCK",
    
    # NEW - Business Rules
    "CHECK_CREDIT_LIMIT",
    "CHECK_STOCK_AVAILABILITY",
    "GET_APPROVAL_STATUS",
    
    # Existing - Recommendations
    "RECOMMEND_ITEMS",
    "RECOMMEND_CUSTOMERS",
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
    
    # Existing - Analytics
    "GET_TOP_SELLING_ITEMS",
    "GET_SLOW_MOVING_ITEMS",
    "GET_SALES_ANALYTICS",
    
    # Existing - Decision Support
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "ANALYZE_CUSTOMER_BEHAVIOR",
    "FORECAST_DEMAND",
    
    # Existing - Warehouses
    "GET_WAREHOUSES",
    "GET_WAREHOUSE_STOCK",
    "GET_LOW_STOCK_ALERTS",
    
    # Existing - Knowledge Base
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
    "CREATE_PURCHASE_ORDER",           # NEW
    "CREATE_GOODS_ISSUE",              # NEW
    "CREATE_GOODS_RECEIPT",            # NEW
    "CREATE_STOCK_TRANSFER",           # NEW
    "CONVERT_QUOTATION_TO_ORDER",      # NEW
    "POST_INVOICE",                    # NEW
    "SEND_PAYMENT_REMINDER",           # NEW
    "APPROVE_PURCHASE_ORDER",          # NEW
    "ALLOCATE_STOCK",                  # NEW
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

DELIVERY_INTENTS = {
    "GET_OUTSTANDING_DELIVERIES", 
    "TRACK_DELIVERY", 
    "GET_DELIVERY_HISTORY"
}

# NEW: Invoice intent groups
INVOICE_INTENTS = {
    "GET_AR_INVOICES",
    "GET_AP_INVOICES", 
    "GET_OVERDUE_INVOICES",
    "GET_CUSTOMER_BALANCE",
    "GET_PAYMENT_STATUS",
    "SEND_PAYMENT_REMINDER",
    "GET_AGING_REPORT",
}

# NEW: Purchase intent groups
PURCHASE_INTENTS = {
    "GET_PURCHASE_ORDERS",
    "CREATE_PURCHASE_ORDER",
    "GET_PURCHASE_REQUESTS",
    "GET_GOODS_RECEIPT_PO",
    "APPROVE_PURCHASE_ORDER",
    "GET_AP_INVOICES_PURCHASE",
}

# NEW: Inventory movement intents
INVENTORY_MOVEMENT_INTENTS = {
    "CREATE_GOODS_ISSUE",
    "CREATE_GOODS_RECEIPT",
    "CREATE_STOCK_TRANSFER",
    "GET_INVENTORY_VALUATION",
    "GET_REORDER_REPORT",
    "ALLOCATE_STOCK",
}

# NEW: Business rules intents
BUSINESS_RULES_INTENTS = {
    "CHECK_CREDIT_LIMIT",
    "CHECK_STOCK_AVAILABILITY",
    "GET_APPROVAL_STATUS",
}

CUSTOMER_INTENTS = {
    "GET_CUSTOMERS",
    "GET_CUSTOMER_DETAILS",
    "GET_CUSTOMER_ORDERS",
    "GET_CUSTOMER_HEALTH",
    "GET_CUSTOMER_INVOICES",
    "GET_OUTSTANDING_INVOICES",
    "FIND_CUSTOMERS_BY_ITEM",
    "GET_CUSTOMER_BALANCE",           # NEW
}

INVENTORY_INTENTS = {
    "GET_STOCK_LEVELS", 
    "GET_LOW_STOCK_ALERTS", 
    "GET_WAREHOUSE_STOCK",
    "GET_INVENTORY_VALUATION",        # NEW
    "GET_REORDER_REPORT",             # NEW
}

ANALYTICS_INTENTS = {
    "GET_TOP_SELLING_ITEMS", 
    "GET_SLOW_MOVING_ITEMS", 
    "GET_SALES_ANALYTICS",
    "GET_AGING_REPORT",               # NEW
}

# ============================================================================
# DOCUMENT LIFECYCLE TRANSITIONS
# ============================================================================

# Mapping of document transitions (for query_rewriter and router)
DOCUMENT_TRANSITIONS = {
    "quotation": ["sales_order", "cancelled"],
    "sales_order": ["delivery", "ar_invoice", "cancelled"],
    "delivery": ["ar_invoice", "returns"],
    "purchase_order": ["goods_receipt_po", "ap_invoice", "cancelled"],
    "goods_receipt_po": ["ap_invoice"],
    "ar_invoice": ["incoming_payment", "credit_memo"],
    "ap_invoice": ["outgoing_payment", "credit_memo"],
}

# Action phrases that trigger document transitions
TRANSITION_PHRASES = {
    "convert": ("quotation", "sales_order"),
    "post": ("delivery", "ar_invoice"),
    "approve": ("purchase_order", "approved"),
    "cancel": (None, "cancelled"),
    "reverse": (None, "reversed"),
}

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
        "credit_limit_exceeded": "Order exceeds customer's credit limit.",
        "insufficient_stock": "Insufficient stock available for this item.",
        "approval_required": "This action requires manager approval.",
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
        "credit_limit_exceeded": "Oda inazidi kikomo cha mkopo cha mteja.",
        "insufficient_stock": "Hisa za kutosha hazipo kwa bidhaa hii.",
        "approval_required": "Kitendo hiki kinahitaji idhini ya meneja.",
    },
}

# ============================================================================
# SUCCESS MESSAGES
# ============================================================================

SUCCESS_MESSAGES = {
    "en": {
        "quotation_created": "✓ Quotation created successfully!",
        "order_created": "✓ Sales order created successfully!",
        "purchase_order_created": "✓ Purchase order created successfully!",
        "goods_receipt_created": "✓ Goods receipt created successfully!",
        "goods_issue_created": "✓ Goods issue created successfully!",
        "stock_transfer_created": "✓ Stock transfer created successfully!",
        "invoice_posted": "✓ Invoice posted successfully!",
        "payment_reminder_sent": "✓ Payment reminder sent successfully!",
        "price_retrieved": "✓ Price retrieved successfully.",
        "stock_retrieved": "✓ Stock information retrieved.",
        "delivery_tracked": "✓ Delivery information retrieved.",
        "quotation_converted": "✓ Quotation converted to sales order successfully!",
    },
    "sw": {
        "quotation_created": "✓ Nukuu imeundwa kwa mafanikio!",
        "order_created": "✓ Oda ya mauzo imeundwa kwa mafanikio!",
        "purchase_order_created": "✓ Agizo la ununuzi limeundwa kwa mafanikio!",
        "goods_receipt_created": "✓ Upokaji wa bidhaa umeundwa kwa mafanikio!",
        "goods_issue_created": "✓ Utoaji wa bidhaa umeundwa kwa mafanikio!",
        "stock_transfer_created": "✓ Uhamisho wa hisa umeundwa kwa mafanikio!",
        "invoice_posted": "✓ Invoice imetumwa kwa mafanikio!",
        "payment_reminder_sent": "✓ Kumbusho la malipo limetumwa kwa mafanikio!",
        "price_retrieved": "✓ Bei imepatikana kwa mafanikio.",
        "stock_retrieved": "✓ Taarifa za hisa zimepatikana.",
        "delivery_tracked": "✓ Taarifa za usafirishaji zimepatikana.",
        "quotation_converted": "✓ Nukuu imebadilishwa kuwa oda ya mauzo kwa mafanikio!",
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