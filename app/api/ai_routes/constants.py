"""Constants for AI routing"""

# ============================================================================
# INTENT CLASSIFICATION FOR ROUTING
# ============================================================================

# Intents that should go to Knowledge Base
KNOWLEDGE_BASE_INTENTS = {
    "COMPANY_INFO",
    "PRODUCT_INFO",
    "HOW_TO_ORDER",
    "PAYMENT_METHODS",
    "CONTACT_INFO",
    "POLICY_QUESTION",
    "FAQ"
}

# Intents that should go to Delivery Tracking
DELIVERY_INTENTS = {
    "GET_OUTSTANDING_DELIVERIES",
    "TRACK_DELIVERY",
    "GET_DELIVERY_HISTORY"
}

# Intents that should go to Decision Support
DECISION_SUPPORT_INTENTS = {
    "GET_TOP_SELLING_ITEMS",
    "GET_SLOW_MOVING_ITEMS",
    "GET_SALES_ANALYTICS",
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "ANALYZE_CUSTOMER_BEHAVIOR",
    "FORECAST_DEMAND"
}

# Intents that should go to Action Router - ADD GET_CUSTOMER_HEALTH HERE
ACTION_ROUTER_INTENTS = {
    # Item intents
    "GET_ITEMS",
    "GET_SELLABLE_ITEMS",
    "GET_PURCHASABLE_ITEMS",
    "GET_INVENTORY_ITEMS",
    "GET_ITEMS_ADVANCED",
    "GET_ITEM_DETAILS",
    "GET_STOCK_LEVELS",
    
    # Customer intents - ADD GET_CUSTOMER_HEALTH HERE
    "GET_CUSTOMERS",
    "GET_CUSTOMER_DETAILS",
    "GET_CUSTOMER_HEALTH",  # <-- CRITICAL: Add this line
    "GET_CUSTOMER_ORDERS",
    "GET_CUSTOMER_INVOICES",
    "GET_OUTSTANDING_INVOICES",
    "FIND_CUSTOMERS_BY_ITEM",
    
    # Pricing intents
    "GET_ITEM_PRICE",
    "GET_CUSTOMER_PRICE",
    
    # Quotation intents
    "CREATE_QUOTATION",
    "GET_QUOTATIONS",
    "FOLLOW_UP_QUOTATIONS",
    
    # Delivery intents
    "GET_OUTSTANDING_DELIVERIES",
    "TRACK_DELIVERY",
    "GET_DELIVERY_HISTORY",
    
    # Recommendation intents
    "RECOMMEND_ITEMS",
    "RECOMMEND_CUSTOMERS",
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
    
    # Analytics intents
    "GET_TOP_SELLING_ITEMS",
    "GET_SLOW_MOVING_ITEMS",
    "GET_SALES_ANALYTICS",
    
    # Decision support intents
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "ANALYZE_CUSTOMER_BEHAVIOR",
    "FORECAST_DEMAND",
    
    # Warehouse intents
    "GET_WAREHOUSES",
    "GET_WAREHOUSE_STOCK",
    "GET_LOW_STOCK_ALERTS",
    
    # Knowledge base intents
    "COMPANY_INFO",
    "PRODUCT_INFO",
    "HOW_TO_ORDER",
    "PAYMENT_METHODS",
    "CONTACT_INFO",
    "POLICY_QUESTION",
    "FAQ",
}

# Price-related intents
PRICE_INTENTS = {
    "GET_ITEM_PRICE",
    "GET_CUSTOMER_PRICE"
}

# Recommendation intents
RECOMMENDATION_INTENTS = {
    "RECOMMEND_ITEMS",
    "RECOMMEND_CUSTOMERS",
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
    "FIND_CUSTOMERS_BY_ITEM"
}

# Manager-only intents
MANAGER_ONLY_INTENTS = {
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "FORECAST_DEMAND"
}

# Candidate labels for CLARIFY intent
CANDIDATE_LABELS = {
    "GET_ITEMS": "Show items",
    "GET_ITEM_PRICE": "Check price",
    "GET_STOCK_LEVELS": "Stock levels",
    "GET_TOP_SELLING_ITEMS": "Top selling",
    "GET_SLOW_MOVING_ITEMS": "Slow moving",
    "GET_OUTSTANDING_DELIVERIES": "Outstanding deliveries",
    "GET_CUSTOMERS": "Show customers",
    "GET_CUSTOMER_HEALTH": "Customer health",  # Add this
    "CREATE_QUOTATION": "Create quotation"
}