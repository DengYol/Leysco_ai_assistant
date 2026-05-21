"""Constants for Leysco API Service"""

# Business Partner Types
BP_TYPES = {
    "CUSTOMER": "C",
    "VENDOR": "V",
    "LEAD": "L",
    "ALL": None
}

# Document type mapping
DOC_TYPES = {
    13: "Invoices",
    14: "Credit Notes",
    15: "Deliveries",
    16: "Returns",
    17: "Sales Orders",
    20: "Returns / Credit Notes",
    22: "Purchase Orders",
    23: "Quotations",
    1470000113: "Custom Document Type",
    540000006: "Custom Document Type",
}

# Status mapping for documents
STATUS_MAP = {
    "open": "Pending",
    "Open": "Pending",
    "OPEN": "Pending",
    "bost_Open": "Pending",
    1: "Pending",
    "1": "Pending",
    "closed": "Completed",
    "Closed": "Completed",
    "CLOSED": "Completed",
    "completed": "Completed",
    "Completed": "Completed",
    "COMPLETED": "Completed",
    "delivered": "Completed",
    "Delivered": "Completed",
    "DELIVERED": "Completed",
    "bost_Close": "Completed",
    2: "Completed",
    "2": "Completed",
    "cancelled": "Cancelled",
    "Cancelled": "Cancelled",
    "CANCELLED": "Cancelled",
    3: "Cancelled",
    "3": "Cancelled",
    "in_transit": "In Transit",
    "In Transit": "In Transit",
    "partial": "Partially Delivered",
    "Partially Delivered": "Partially Delivered",
}

DOC_STATUS_MAP = {
    "open": 1,
    "pending": 1,
    "closed": 2,
    "completed": 2,
    "all": None
}

# Endpoint patterns for discovery
ENDPOINT_PATTERNS = {
    "quotations": [
        "/documents/quotation",
        "/documents/quotations",
        "/quotations",
        "/sales/quotations",
        "/marketing/quotation",
        "/quotation/create",
        "/marketing/docs/23",
    ],
    "orders": [
        "/orders",
        "/sales/orders",
        "/marketing/orders",
        "/marketing/docs/17",
    ],
    "invoices": [
        "/invoices",
        "/sales/invoices",
        "/marketing/invoices",
        "/marketing/docs/13",
    ],
    "deliveries": [
        "/deliveries",
        "/sales/deliveries",
        "/marketing/docs/15",
    ],
    "documents": [
        "/documents/quotation",
        "/documents/quotations",
        "/documents/order",
        "/documents/invoice",
        "/documents/delivery",
    ],
}

KNOWN_POST_ENDPOINTS = {
    "quotations": [
        "/documents/quotation",
        "/documents/quotations",
        "/quotations",
    ],
    "orders": [
        "/documents/order",
        "/orders",
    ],
}

# Words to strip from search terms
STRIP_FROM_SEARCH = {
    "suppliers", "supplier", "vendor", "vendors", "traders", "trader",
    "enterprises", "enterprise", "company", "co", "ltd", "limited",
    "inc", "group", "associates", "agency", "agencies",
    "industries", "industry", "international", "brothers", "bros",
    "holdings", "services", "distributors", "distributor",
}

# Cache TTLs
CUSTOMER_CACHE_TTL = 300  # 5 minutes
ITEM_CACHE_TTL = 300       # 5 minutes
INVENTORY_CACHE_TTL = 120  # 2 minutes
PRICE_CACHE_TTL = 300      # 5 minutes
DELIVERY_CACHE_TTL = 60    # 1 minute
ANALYTICS_CACHE_TTL = 3600  # 1 hour for analytics (less frequent changes)

# Default values
DEFAULT_TIMEOUT = 30
DEFAULT_RETRY_TOTAL = 2
DEFAULT_RETRY_BACKOFF = 0.3