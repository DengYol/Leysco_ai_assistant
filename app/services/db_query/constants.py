"""
Constants for DB Query Service
"""

import re

# =========================================================
# INTENT GROUPS for db_query
# =========================================================

# Delivery intents that db_query can handle
DELIVERY_INTENTS = {
    "GET_OUTSTANDING_DELIVERIES",
    "TRACK_DELIVERY",
    "GET_DELIVERY_HISTORY",
}

# Price intents that db_query can handle
PRICE_INTENTS = {
    "GET_ITEM_PRICE",
    "GET_CUSTOMER_PRICE",
}

# Customer intents that db_query can handle
CUSTOMER_INTENTS = {
    "GET_CUSTOMERS",
    "GET_CUSTOMER_DETAILS",
    "GET_CUSTOMER_ORDERS",
    "GET_CUSTOMER_INVOICES",
    "GET_OUTSTANDING_INVOICES",
    "GET_CUSTOMER_HEALTH",
    "GET_CUSTOMER_BALANCE",
}

# Invoice intents
INVOICE_INTENTS = {
    "GET_AR_INVOICES",
    "GET_AP_INVOICES",
    "GET_OVERDUE_INVOICES",
    "GET_CUSTOMER_BALANCE",
}

# Purchase intents
PURCHASE_INTENTS = {
    "GET_PURCHASE_ORDERS",
    "GET_PURCHASE_REQUESTS",
    "GET_GOODS_RECEIPT_PO",
}

# Inventory intents
INVENTORY_INTENTS = {
    "GET_INVENTORY_VALUATION",
    "GET_REORDER_REPORT",
}

# Item intents
ITEM_INTENTS = {
    "GET_ITEMS",
    "GET_SELLABLE_ITEMS",
    "GET_PURCHASABLE_ITEMS",
    "GET_INVENTORY_ITEMS",
    "GET_ITEM_DETAILS",
    "GET_STOCK_LEVELS",
}

# Warehouse intents
WAREHOUSE_INTENTS = {
    "GET_WAREHOUSES",
    "GET_WAREHOUSE_STOCK",
    "GET_LOW_STOCK_ALERTS",
}

# =========================================================
# SIZE PATTERNS (used by price transformer)
# =========================================================

SIZE_PATTERNS = [
    # ML patterns
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:ml|ML|mL)', re.IGNORECASE),
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:milliliter|millilitre|millilitres|milliliters)', re.IGNORECASE),
    
    # Liter patterns
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:l|L)', re.IGNORECASE),
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:liter|litre|liters|litres)', re.IGNORECASE),
    
    # Gram patterns
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:g|G|gm|GM|gram|Gram)', re.IGNORECASE),
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:grams|grammes)', re.IGNORECASE),
    
    # Kilogram patterns
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:kg|KG)', re.IGNORECASE),
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:kilogram|kilograms|kilo|kilos)', re.IGNORECASE),
    
    # Piece patterns
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:pc|pcs|PCS|piece|pieces)', re.IGNORECASE),
    
    # Packet patterns
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:pkt|packet|packets|pack|packs)', re.IGNORECASE),
    
    # Bottle patterns
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:bottle|bottles|btl|btls)', re.IGNORECASE),
    
    # Carton patterns
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:carton|cartons|ctn|ctns)', re.IGNORECASE),
]

# Size units for normalization
SIZE_UNITS = {
    'ml': 'ml',
    'milliliter': 'ml',
    'millilitre': 'ml',
    'milliliters': 'ml',
    'millilitres': 'ml',
    'l': 'l',
    'liter': 'l',
    'litre': 'l',
    'liters': 'l',
    'litres': 'l',
    'g': 'g',
    'gm': 'g',
    'gram': 'g',
    'grams': 'g',
    'grammes': 'g',
    'kg': 'kg',
    'kilogram': 'kg',
    'kilograms': 'kg',
    'kilo': 'kg',
    'kilos': 'kg',
}

# =========================================================
# DEFAULT VALUES
# =========================================================

DEFAULT_MAX_ITEMS = 20
DEFAULT_PRICE_CACHE_TTL = 3600

# =========================================================
# SWAHILI TRANSLATIONS
# =========================================================

SWAHILI_GREETINGS = [
    "Habari", "Mambo", "Sasa", "Vipi", "Jambo", "Hujambo", "Shikamoo"
]

SWAHILI_ERRORS = {
    "not_found": "Samahani, hakuna data iliyopatikana.",
    "invalid_input": "Tafadhali ingiza taarifa sahihi.",
    "server_error": "Hitilafu ya seva. Tafadhali jaribu tena baadaye.",
}