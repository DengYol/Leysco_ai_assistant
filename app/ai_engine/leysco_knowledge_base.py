"""
app/ai_engine/leysco_knowledge_base.py (P1.3 - ERP-SOURCED)
===========================================================
Leysco AI Assistant — Knowledge Base

CHANGE: Knowledge is now sourced from ERP API instead of hardcoded.
- Items, customers, pricing are LIVE from ERP
- Training/policy/contact info remains static (policy)
- All data is cached with tenant scoping
"""

import logging
import asyncio
import hashlib
from typing import Dict, Any, Optional, List
from functools import wraps
from datetime import datetime, timedelta

from app.services.cache_service import get_cache_service
from app.services.leysco_api.client import get_leysco_api_client

logger = logging.getLogger(__name__)


# ============================================================================
# CACHE DECORATOR (unchanged from before)
# ============================================================================

def cache_kb(ttl_seconds: int = 3600):
    """Cache knowledge base responses for configurable TTL."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache = get_cache_service()
            
            # Generate cache key
            func_name = func.__name__
            cache_str = f"kb:{func_name}:{str(args[1:])}:{str(sorted(kwargs.items()))}"
            cache_key = hashlib.md5(cache_str.encode()).hexdigest()
            
            # Check cache
            cached = cache.get_simple(cache_key)
            if cached is not None:
                logger.info(f"⚡ KB cache hit: {func_name}")
                return cached
            
            # Execute function (now async)
            result = await func(*args, **kwargs)
            
            # Cache result
            if result:
                cache.set_simple(cache_key, result, ttl=ttl_seconds)
            
            return result
        return wrapper
    return decorator


# ============================================================================
# 1. STATIC COMPANY PROFILE (Policy - doesn't change from ERP)
# ============================================================================

COMPANY_PROFILE = """
Company Name: Leysco Limited
Tagline: Simply Reliable
Industry: Software Development & IT Consultancy — Kenya
Location: APA Arcade, Hurlingham, Nairobi, Kenya
Phone: +254(0) 780 457 591
Email: info@leysco.com
Website: https://leysco.com

Who We Are:
Leysco is a software development and consultancy company specialising in
enterprise-wide Resource Planning and Management Systems that support
critical business processes and decision-making for organisations in Kenya.

What differentiates Leysco is their culture that fosters creativity and open
communication, enabling their team to achieve their full potential with a
clear sense of purpose.

Core Services:
1. SAP ERP Implementation
2. Leysco Systems Consulting
3. Web Application Development
4. Mobile Apps Development
5. Web Development and Hosting
6. EDMS (Electronic Document Management System)
"""

CONTACT_INFO = """
Leysco Limited — Contact Details

Company: Leysco Limited
Address: APA Arcade, Hurlingham, Nairobi, Kenya
Phone: +254(0) 780 457 591
Email: info@leysco.com
Website: https://leysco.com
EDMS Portal: https://pgtl.xedms.com

System Support (Leysco100 / SAP):
- For SAP system issues: Contact Leysco IT support via info@leysco.com
- Phone support: +254(0) 780 457 591
"""

PAYMENT_METHODS = """
Leysco Payment Methods:

ACCEPTED PAYMENT OPTIONS:
1. M-Pesa — Paybill number (get current details from Finance)
2. Bank Transfer — Account details available from Finance department
3. Cash — At our offices (receipt issued)
4. Cheque — Subject to clearance before goods release

CREDIT TERMS:
- Credit customers: Payment due within agreed credit period (30/60 days)
- New customers: Cash on delivery until credit account is approved
"""

# ============================================================================
# 2. TRAINING MODULES (Static - policy-based)
# ============================================================================

TRAINING_MODULES = {
    "TRAINING_MODULE": """
LEYSCO100 TRAINING OVERVIEW

Available training topics — just ask me about any of these:

1. HOW TO CREATE A QUOTATION
2. HOW TO CHECK STOCK
3. HOW TO FIND CUSTOMER INFORMATION
4. HOW TO TRACK DELIVERIES
5. HOW TO USE PRICING
6. PAYMENT METHODS
7. RETURNS & REFUNDS
8. UNDERSTANDING THE DASHBOARD

Which topic would you like to start with?
""",
    "TRAINING_GUIDE": """
LEYSCO100 STEP-BY-STEP GUIDES

I can walk you through:
- Creating a quotation
- Checking stock levels
- Looking up customer details
- Understanding pricing and discounts
- Processing returns and refunds
- Reading the dashboard KPIs

Just ask: "How do I [task]?" and I'll guide you step by step.
""",
    "TRAINING_FAQ": """
FREQUENTLY ASKED QUESTIONS

Q: How do I check if an item is in stock?
A: Ask me: "Stock level for [item name]"

Q: Why is my customer's price different from the list price?
A: Customers can have special pricing agreements. Always use "Price of [item] for [customer]"

Q: What if the item a customer wants is out of stock?
A: Ask me to "recommend alternatives for [crop/use]"

Q: How long is a quotation valid?
A: Check with your sales manager for the current validity period.

Q: How do I know a customer's credit limit?
A: Ask me "Customer details for [name]" — it shows their credit status.
""",
    "TRAINING_WEBINAR": """
LEYSCO100 LIVE TRAINING SESSIONS

For live training sessions, webinars, and workshops:
- Contact your sales manager or HR department
- Ask about the next scheduled Leysco100 onboarding session
""",
    "TRAINING_VIDEO": """
LEYSCO100 VIDEO TRAINING

For video tutorials and screencasts on using Leysco100:
- Contact your IT department or system administrator
- Ask your manager about available training materials
""",
}

HOW_TO_CREATE_QUOTATION = """
HOW TO CREATE A SALES QUOTATION

Step 1 — Find your customer
  Ask: "Show me customer [name]" or "Customer details for [name]"

Step 2 — Check what's in stock
  Ask: "What's the stock level for [product]?"

Step 3 — Get the right price
  Ask: "Price of [item] for customer [name]"

Step 4 — Create the quotation
  Say: "Create a quote for [customer] — [quantity] [item]"

Step 5 — Confirm with customer
  Share the quotation number with the customer for reference.
"""

HOW_TO_ORDER = """
HOW TO PLACE A SALES ORDER

Step 1 — Verify customer account
Step 2 — Confirm stock availability
Step 3 — Get customer pricing
Step 4 — Create quotation first (recommended)
Step 5 — Submit order
"""

SALES_REP_QUICK_REFERENCE = """
SALES REP DAILY CHEAT SHEET

--- MOST USEFUL COMMANDS ---
Check stock: "Stock level for [item name]"
Get prices: "Price of [item] for customer [name]"
Find a customer: "Show customer [name]"
Create a quote: "Create a quote for [customer] — [qty] [item]"
Track deliveries: "Outstanding deliveries"

--- BEFORE A CUSTOMER VISIT ---
1. Check their order history: "Orders for [customer name]"
2. Check prices for their key products: "Price of [item] for [customer]"
3. Check current stock of what they usually buy
"""

ONBOARDING_GUIDE = """
WELCOME TO LEYSCO100 AI ASSISTANT!

I'm your AI-powered assistant for the Leysco100 ERP system.
I can help you navigate all 10 system modules using plain English.

--- WHAT I CAN DO ---

SALES & PRICING:
  "Price of VegiMax"
  "Create a quote for [customer] — [qty] [item]"
  "Show orders for [customer]"

INVENTORY:
  "Show me all items"
  "Stock level for cabbage seeds"
  "Low stock alerts"

BUSINESS PARTNERS:
  "Show me customers"
  "Customer details for [name]"

LOGISTICS:
  "Outstanding deliveries"

TRAINING & GUIDANCE:
  "How do I create a quotation?"
  "What does DAP mean?"
  "Show me the sales rep cheat sheet"

--- YOUR FIRST 5 ACTIONS ---
1. "Show me items" — see the full product catalogue
2. "Show me customers" — browse your customer list
3. "Low stock alerts" — see what needs restocking
4. "Price of [top product]" — confirm your pricing
5. "How do I create a quote?" — step-by-step guide
"""

# ============================================================================
# 3. GLOSSARY (Static)
# ============================================================================

GLOSSARY = {
    "SKU": "Stock Keeping Unit — the unique code for each product",
    "MOQ": "Minimum Order Quantity — the smallest amount you can order",
    "UOM": "Unit of Measure — how the item is sold (e.g. KG, BAG, PIECE)",
    "ETA": "Estimated Time of Arrival — when a shipment is expected",
    "GRN": "Goods Received Note — document confirming stock received",
    "DN": "Delivery Note — document that goes with goods sent to a customer",
    "PO": "Purchase Order — an order placed to a supplier",
    "SO": "Sales Order — a confirmed order from a customer",
    "CAN": "Calcium Ammonium Nitrate — a common nitrogen fertilizer",
    "DAP": "Di-Ammonium Phosphate — fertilizer used at planting",
    "NPK": "Nitrogen, Phosphorus, Potassium — main nutrients in fertilizers",
    "SAP": "Systems, Applications and Products — the ERP system",
    "ERP": "Enterprise Resource Planning — integrated business management",
    "KPI": "Key Performance Indicator — a measurable target",
    "BOM": "Bill of Materials — list of components for production",
    "WH": "Warehouse — storage location for inventory items",
    "GP": "Gate Pass — authorisation for goods entering/leaving",
    "KES": "Kenyan Shilling — the currency used",
}

# ============================================================================
# 4. ANALYTICS KNOWLEDGE (Static)
# ============================================================================

SALES_ANALYTICS_KNOWLEDGE = """
📊 SALES ANALYTICS OVERVIEW

The sales analytics feature provides insights into your sales performance:

KEY METRICS AVAILABLE:
- Total Revenue — overall sales value
- Total Transactions — number of sales orders
- Average Order Value — revenue per transaction
- Unique Customers — customer count
- Total Items Sold — quantity of products sold

TRENDS YOU CAN TRACK:
- Revenue change over time (daily, weekly, monthly)
- Transaction volume trends
- Customer acquisition patterns

TOP SELLING PRODUCTS:
- Which items sell the most by quantity
- Which items generate the most revenue
- Seasonal product performance

HOW TO USE SALES ANALYTICS:
1. "Show sales analytics" — basic overview
2. "Sales report for last month" — specific period
3. "Top selling items" — best performing products
4. "Sales by product category" — category breakdown
"""

TOP_SELLING_KNOWLEDGE = """
🏆 TOP SELLING ITEMS

Top selling items show which products are most popular with customers.

WHAT YOU CAN LEARN:
- Which products generate the most revenue
- Which items have the highest sales volume
- Seasonal trends in product popularity
- Customer purchasing preferences

HOW TO USE:
- "Show top selling items" — see current best sellers
- "Top 10 selling products" — specify limit
- "Best selling items this month" — time-specific

INTERPRETING THE DATA:
- High volume items may have low margins
- High revenue items drive profitability
- Fast movers need consistent stock levels
- Best sellers are good for promotions
"""

SLOW_MOVING_KNOWLEDGE = """
🐌 SLOW MOVING ITEMS

Slow moving items are products with low turnover rates.

IDENTIFYING SLOW MOVERS:
- Items with low sales volume
- Products with high inventory levels but few sales
- Items that haven't sold in extended periods

BUSINESS ACTIONS:
1. Review pricing — may be too high
2. Consider promotions — discount to move inventory
3. Discontinue — remove from catalog if consistently slow
4. Bundle with fast movers — increase appeal
"""

WAREHOUSE_KNOWLEDGE = """
🏭 WAREHOUSE MANAGEMENT

Leysco operates multiple warehouses across Kenya:

WAREHOUSE LOCATIONS:
- Nairobi Main — Central hub, largest inventory
- Mombasa — Coastal region, import handling
- Kisumu — Western Kenya distribution
- Eldoret — Rift Valley region
- Nakuru — Central Rift coverage

WHAT YOU CAN CHECK:
- "Show all warehouses" — view all locations
- "Stock in [warehouse]" — inventory by location
- "Low stock alerts in Nairobi" — specific warehouse alerts
"""

DELIVERY_KNOWLEDGE = """
📦 DELIVERY TRACKING

Track and manage customer deliveries through the system.

DELIVERY STATUSES:
- Open — Order created, not yet processed
- In Transit — On the way to customer
- Partially Delivered — Some items delivered
- Completed — Fully delivered
- Overdue — Past due date

WHAT YOU CAN TRACK:
- "Outstanding deliveries" — pending deliveries
- "Track delivery [order number]" — specific order
- "Delivery history for [customer]" — past deliveries
"""

CROSS_SELL_KNOWLEDGE = """
🔄 CROSS-SELL & UPSELL

CROSS-SELL: Complementary products customers often buy together

EXAMPLES:
- Fertilizer + Seeds — planting combo
- Pesticide + Protective gear — safety bundle

UPSELL: Premium alternatives with better features/benefits

EXAMPLES:
- Standard seed → Hybrid variety (higher yield)
- Basic fertilizer → Controlled-release (efficiency)
"""

# ============================================================================
# 5. DYNAMIC ERP-SOURCED FUNCTIONS (NEW)
# ============================================================================

async def get_erp_items_knowledge(tenant_code: str) -> str:
    """
    Get current items from ERP API.
    Returns formatted knowledge text for LLM context.
    
    This replaces hardcoded PRODUCTS_AND_BRANDS.
    """
    try:
        api = get_leysco_api_client(tenant_code)
        items = await api.get_items()
        
        if not items:
            return "No items found in ERP."
        
        # Group by category
        by_category = {}
        for item in items:
            category = item.get("category", "Other")
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(item)
        
        # Format as knowledge text
        lines = ["📦 PRODUCT CATALOGUE (from ERP)\n"]
        for category, items_in_cat in by_category.items():
            lines.append(f"\n{category}:")
            for item in items_in_cat[:10]:  # Limit to 10 per category
                sku = item.get("sku", "N/A")
                name = item.get("name", "Unknown")
                lines.append(f"  - {name} (SKU: {sku})")
        
        return "\n".join(lines)
    
    except Exception as e:
        logger.error(f"Failed to load ERP items: {e}")
        return "Items data temporarily unavailable from ERP."


async def get_erp_customers_knowledge(tenant_code: str) -> str:
    """
    Get current customers from ERP API.
    Returns formatted knowledge text for LLM context.
    
    This replaces hardcoded customer references.
    """
    try:
        api = get_leysco_api_client(tenant_code)
        customers = await api.get_customers()
        
        if not customers:
            return "No customers found in ERP."
        
        lines = ["👥 CUSTOMER DIRECTORY (from ERP)\n"]
        lines.append(f"Total customers: {len(customers)}\n")
        lines.append("Top 10 customers by recent activity:")
        
        for customer in customers[:10]:
            name = customer.get("name", "Unknown")
            city = customer.get("city", "")
            lines.append(f"  - {name}" + (f" ({city})" if city else ""))
        
        return "\n".join(lines)
    
    except Exception as e:
        logger.error(f"Failed to load ERP customers: {e}")
        return "Customer data temporarily unavailable from ERP."


async def get_erp_warehouses_knowledge(tenant_code: str) -> str:
    """
    Get current warehouses from ERP API.
    Returns formatted knowledge text for LLM context.
    """
    try:
        api = get_leysco_api_client(tenant_code)
        warehouses = await api.get_warehouses()
        
        if not warehouses:
            return WAREHOUSE_KNOWLEDGE  # Fall back to static
        
        lines = ["🏭 WAREHOUSE LOCATIONS (from ERP)\n"]
        for wh in warehouses:
            name = wh.get("name", "Unknown")
            location = wh.get("location", "")
            lines.append(f"  - {name}" + (f" — {location}" if location else ""))
        
        return "\n".join(lines)
    
    except Exception as e:
        logger.error(f"Failed to load ERP warehouses: {e}")
        return WAREHOUSE_KNOWLEDGE  # Fall back to static


# ============================================================================
# 6. MAIN KNOWLEDGE RETRIEVAL FUNCTION (Updated)
# ============================================================================

async def get_knowledge(intent: str, query: str = "", tenant_code: str = "TEST001") -> str:
    """
    Returns the most relevant knowledge base content for a given intent.
    
    NOW: Combines static knowledge (policy) with dynamic knowledge (ERP data).
    
    Args:
        intent: The user's intent (GET_ITEMS, GET_CUSTOMERS, etc.)
        query: The original user query
        tenant_code: The tenant making the request (for multi-tenancy)
    """
    intent = intent.upper()

    knowledge_map = {
        # ===== STATIC KNOWLEDGE (Policy) =====
        "COMPANY_INFO": COMPANY_PROFILE,
        "CONTACT_INFO": CONTACT_INFO,
        "PAYMENT_METHODS": PAYMENT_METHODS,
        "POLICY_QUESTION": PAYMENT_METHODS,
        "HOW_TO_ORDER": HOW_TO_ORDER,
        "CREATE_QUOTATION": HOW_TO_CREATE_QUOTATION,
        "FAQ": ONBOARDING_GUIDE,
        "GREETING": ONBOARDING_GUIDE,
        "SMALL_TALK": ONBOARDING_GUIDE,
        "TRAINING_MODULE": TRAINING_MODULES.get("TRAINING_MODULE", ""),
        "TRAINING_GUIDE": TRAINING_MODULES.get("TRAINING_GUIDE", ""),
        "TRAINING_FAQ": TRAINING_MODULES.get("TRAINING_FAQ", ""),
        "TRAINING_WEBINAR": TRAINING_MODULES.get("TRAINING_WEBINAR", ""),
        "TRAINING_VIDEO": TRAINING_MODULES.get("TRAINING_VIDEO", ""),
        
        # ===== ANALYTICS (Static) =====
        "GET_SALES_ANALYTICS": SALES_ANALYTICS_KNOWLEDGE,
        "GET_TOP_SELLING_ITEMS": TOP_SELLING_KNOWLEDGE,
        "GET_SLOW_MOVING_ITEMS": SLOW_MOVING_KNOWLEDGE,
        "GET_WAREHOUSES": WAREHOUSE_KNOWLEDGE,
        "GET_DELIVERY_HISTORY": DELIVERY_KNOWLEDGE,
        "GET_OUTSTANDING_DELIVERIES": DELIVERY_KNOWLEDGE,
        "TRACK_DELIVERY": DELIVERY_KNOWLEDGE,
        "GET_CROSS_SELL": CROSS_SELL_KNOWLEDGE,
        "GET_UPSELL": CROSS_SELL_KNOWLEDGE,
        
        # ===== DYNAMIC KNOWLEDGE (from ERP - async loaded) =====
        "GET_ITEMS": "ASYNC_LOAD",  # Will be loaded below
        "GET_CUSTOMERS": "ASYNC_LOAD",
        "FIND_CUSTOMERS_BY_ITEM": "ASYNC_LOAD",
        "GET_CUSTOMER_DETAILS": "ASYNC_LOAD",
        "GET_CUSTOMER_ORDERS": "ASYNC_LOAD",
        "GET_WAREHOUSES": "ASYNC_LOAD",  # Can also be ERP-sourced
    }

    # ===== HANDLE GLOSSARY =====
    if intent == "TRAINING_GLOSSARY":
        query_lower = query.lower()
        matched = {
            term: definition
            for term, definition in GLOSSARY.items()
            if term.lower() in query_lower
        }
        if matched:
            lines = [f"{term}: {defn}" for term, defn in matched.items()]
            return "GLOSSARY DEFINITIONS:\n" + "\n".join(lines)
        lines = [f"{term}: {defn}" for term, defn in GLOSSARY.items()]
        return "LEYSCO GLOSSARY:\n" + "\n".join(lines)

    # ===== GET STATIC CONTENT =====
    content = knowledge_map.get(intent)
    
    # ===== LOAD DYNAMIC CONTENT FROM ERP =====
    if content == "ASYNC_LOAD":
        try:
            if intent == "GET_ITEMS":
                content = await get_erp_items_knowledge(tenant_code)
            elif intent == "GET_CUSTOMERS":
                content = await get_erp_customers_knowledge(tenant_code)
            elif intent == "GET_WAREHOUSES":
                content = await get_erp_warehouses_knowledge(tenant_code)
            elif intent in ["FIND_CUSTOMERS_BY_ITEM", "GET_CUSTOMER_DETAILS", "GET_CUSTOMER_ORDERS"]:
                content = await get_erp_customers_knowledge(tenant_code)
            else:
                content = ONBOARDING_GUIDE
        except Exception as e:
            logger.error(f"Failed to load ERP knowledge: {e}")
            content = "Data temporarily unavailable. Please try again."
    
    # ===== FALLBACK =====
    if not content:
        content = ONBOARDING_GUIDE

    return content


# ============================================================================
# 7. STRUCTURED INFO FUNCTIONS (Updated for async)
# ============================================================================

async def get_company_info() -> dict:
    """Returns structured company info dict."""
    return {
        "name": "Leysco Limited",
        "tagline": "Simply Reliable",
        "about": (
            "Leysco is a software development and consultancy company specialising in "
            "enterprise-wide Resource Planning and Management Systems."
        ),
        "phone": "+254(0) 780 457 591",
        "email": "info@leysco.com",
        "website": "https://leysco.com",
        "address": "APA Arcade, Hurlingham, Nairobi, Kenya",
    }


async def get_contact_info() -> dict:
    """Returns structured contact info dict."""
    return {
        "customer_support": {
            "phone": "+254(0) 780 457 591",
            "email": "info@leysco.com",
            "hours": "Monday – Friday, 8:00 AM – 5:00 PM EAT",
        },
        "technical_support": "Email: info@leysco.com | Phone: +254(0) 780 457 591",
        "address": "APA Arcade, Hurlingham, Nairobi, Kenya",
        "website": "https://leysco.com",
    }


async def get_policies() -> dict:
    """Returns structured policy info dict."""
    return {
        "returns": "Returns accepted within 7 days with original receipt.",
        "quality_guarantee": "All seeds are certified. Products failing quality standards will be replaced.",
        "credit_policy": "Credit limits set per customer based on payment history.",
        "delivery_policy": "All deliveries require a signed gate pass.",
    }


async def get_glossary_term(term: str) -> str:
    """Look up a single glossary term."""
    return GLOSSARY.get(term.upper(), f"Term '{term}' not found in glossary.")


def get_sales_rep_reference() -> str:
    """Returns the quick reference cheat sheet for sales reps."""
    return SALES_REP_QUICK_REFERENCE


def get_onboarding_guide() -> str:
    """Returns the new user onboarding guide."""
    return ONBOARDING_GUIDE


def clear_knowledge_cache():
    """Clear the knowledge base cache."""
    cache = get_cache_service()
    cache.clear()
    logger.info("Knowledge base cache cleared")