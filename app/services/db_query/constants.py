"""Constants for DB Query Service"""

# Intents answered from knowledge base only — no API call needed
KNOWLEDGE_BASE_INTENTS = {
    "COMPANY_INFO",
    "PRODUCT_INFO",
    "HOW_TO_ORDER",
    "CONTACT_INFO",
    "PAYMENT_METHODS",
    "POLICY_QUESTION",
    "FAQ",
    "GREETING",
    "THANKS",
    "SMALL_TALK",
    "TRAINING_MODULE",
    "TRAINING_GUIDE",
    "TRAINING_FAQ",
    "TRAINING_VIDEO",
    "TRAINING_WEBINAR",
    "TRAINING_GLOSSARY",
    "TRAINING_ONBOARDING",
}

# Intents handled by action router - should NOT be processed here
ACTION_ROUTER_INTENTS = {
    "CREATE_QUOTATION",
    "GET_CUSTOMER_HEALTH",
    "FOLLOW_UP_QUOTATIONS",
    "FIND_CUSTOMERS_BY_ITEM",
    "RECOMMEND_ITEMS",
    "RECOMMEND_CUSTOMERS",
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
    "TRACK_DELIVERY",
    "GET_OUTSTANDING_DELIVERIES",
    "GET_DELIVERY_HISTORY",
    "GET_SALES_ANALYTICS",
    "GET_TOP_SELLING_ITEMS",
    "GET_SLOW_MOVING_ITEMS",
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "FORECAST_DEMAND",
    "PRICE_ALERT",
    "MARKET_INTELLIGENCE",
    "COMPETITOR_PRICE_CHECK",
    "FIND_BEST_PRICE",
}

# Size patterns for item prioritization with priority scores
SIZE_PATTERNS = {
    "10ml": 100, "10ML": 100, "10 ml": 100,
    "30ml": 90, "30ML": 90, "30 ml": 90,
    "125ml": 70, "125ML": 70, "125 ml": 70,
    "250ml": 60, "250ML": 60, "250 ml": 60,
    "500ml": 50, "500ML": 50, "500 ml": 50,
    "1kg": 100, "1KG": 100, "1 kg": 100,
    "2kg": 90, "2KG": 90, "2 kg": 90,
    "5kg": 70, "5KG": 70, "5 kg": 70,
    "10kg": 60, "10KG": 60, "10 kg": 60,
    "25kg": 50, "25KG": 50, "25 kg": 50,
    "50kg": 40, "50KG": 40, "50 kg": 40,
}

# Swahili prompts
SWAHILI_GREETINGS = [
    "Habari! Nikusaidie vipi?",
    "Mambo! Unauliza nini?",
    "Sasa! Niko hapa kukusaidia.",
    "Karibu! Naomba kukusaidia na nini?"
]

SWAHILI_ERRORS = {
    "not_found": "Samahani, siwezi kupata ile uliyoiomba. Tafadhali jaribu tena.",
    "timeout": "Muda umeisha. Tafadhali jaribu tena baadaye.",
    "no_results": "Hakuna matokeo yaliyopatikana.",
    "invalid_input": "Tafadhali ingiza taarifa sahihi."
}

# Default values
DEFAULT_MAX_ITEMS = 15
DEFAULT_PRICE_CACHE_TTL = 300