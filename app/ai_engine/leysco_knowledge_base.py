"""
app/ai_engine/leysco_knowledge_base.py
=======================================
Leysco AI Assistant — Knowledge Base

This file is the "brain" for all non-database answers.
Optimized with caching and async support.
"""

import logging
import asyncio
import hashlib
from typing import Dict, Any, Optional, List
from functools import lru_cache, wraps
from datetime import datetime

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


# Cache decorator for knowledge base functions
def cache_kb(ttl_seconds: int = 3600):
    """Cache knowledge base responses for 1 hour."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
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
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            if result:
                cache.set_simple(cache_key, result, ttl=ttl_seconds)
            
            return result
        return wrapper
    return decorator


# ===========================================================================
# 1. COMPANY PROFILE
# ===========================================================================

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

About Leysco100:
Leysco100 is Leysco's SAP Business One ERP system for Demo Company Kenya,
an agricultural inputs business. It manages the full business operation
end-to-end across 10 modules.

Core Values: Safety, Stability, Technical Support, Complete Solutions
"""

# ===========================================================================
# 2. CONTACT INFORMATION
# ===========================================================================

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

# ===========================================================================
# 3. PRODUCTS & BRANDS
# ===========================================================================

PRODUCTS_AND_BRANDS = """
Leysco Product Categories:

SEEDS:
- Vegetable seeds: Cabbage, Tomato, Pepper, Cauliflower, Onion, Watermelon
- Maize seeds: Various hybrid varieties (MH401, KH500, etc.)
- Key brands: EaSeed, Agriscope, Technisem, Syngenta

FERTILIZERS:
- CAN (Calcium Ammonium Nitrate)
- DAP (Di-Ammonium Phosphate)
- NPK blends
- Foliar fertilizers

AGRO-CHEMICALS:
- Pesticides, herbicides, fungicides
- Key brands: various licensed agrochemical brands

SPECIALTY PRODUCTS:
- VegiMax (vegetable nutrition)
- Tosheka (specialty crop inputs)
- Yolo Wonder (pepper variety)
- Snowball (cauliflower variety)
"""

# ===========================================================================
# 4. ORDERING & QUOTATIONS
# ===========================================================================

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

# ===========================================================================
# 5. PAYMENT METHODS & POLICIES
# ===========================================================================

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

# ===========================================================================
# 6. SALES REP QUICK REFERENCE
# ===========================================================================

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

# ===========================================================================
# 7. ONBOARDING GUIDE
# ===========================================================================

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

# ===========================================================================
# 8. TRAINING MODULES
# ===========================================================================

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

# ===========================================================================
# 9. GLOSSARY
# ===========================================================================

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

# ===========================================================================
# 10. FAQ
# ===========================================================================

FAQ = """
LEYSCO100 AI ASSISTANT — WHAT CAN I HELP WITH?

SALES MODULE:
- Create quotations: "Create a quote for [customer] — [qty] [item]"
- View orders: "Show orders for [customer]"
- Check invoices: "Invoices for [customer]"
- Track deliveries: "Outstanding deliveries for [customer]"

INVENTORY MODULE:
- Browse items: "Show me all items"
- Check stock: "Stock level for [item]"
- Low stock alerts: "Show low stock alerts"
- Warehouse list: "Show all warehouses"

PRICING:
- Base price: "Price of [item]"
- Customer price: "Price of [item] for [customer]"

BUSINESS PARTNERS:
- Find customers: "Show customer [name]"
- Customer details: "Details for [customer]"
- Order history: "Orders for [customer]"

TRAINING & GUIDANCE:
- Step-by-step guides: "How do I create a quotation?"
- Glossary: "What does [term] mean?"
- Sales coaching tips: "How should I approach [customer type]?"

Just ask naturally — I understand plain English!
"""

# ===========================================================================
# 11. SALES ANALYTICS KNOWLEDGE (NEW)
# ===========================================================================

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

For detailed sales data with real numbers, ask for specific analytics.
"""

# ===========================================================================
# 12. TOP SELLING ITEMS KNOWLEDGE (NEW)
# ===========================================================================

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

Combine with stock levels to ensure top sellers are always available.
"""

# ===========================================================================
# 13. SLOW MOVING ITEMS KNOWLEDGE (NEW)
# ===========================================================================

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

STOCK MANAGEMENT:
- Reduce reorder quantities for slow movers
- Consider warehouse consolidation
- Monitor expiration dates for perishables

Ask "Show slow moving items" to identify products needing attention.
"""

# ===========================================================================
# 14. CUSTOMER SEGMENTATION KNOWLEDGE (NEW)
# ===========================================================================

CUSTOMER_SEGMENTATION_KNOWLEDGE = """
🎯 CUSTOMER SEGMENTATION (Sell Out Analysis)

Customer segmentation helps identify who would buy specific products.

HOW TO FIND CUSTOMERS FOR A PRODUCT:
- "Who would buy [product]?"
- "Sell out [product]" — find potential customers
- "Target customers for [item]"

SEGMENTATION CRITERIA:
- Purchase history — what they've bought before
- Industry or crop focus — what they grow
- Location — regional relevance
- Customer tier — high, medium, low volume

USING SEGMENTATION:
1. Identify top customers for similar products
2. Create targeted quotations
3. Personalize sales approach
4. Focus marketing efforts

Example: "Sell out VegiMax" finds customers who buy crop nutrition products.
"""

# ===========================================================================
# 15. WAREHOUSE KNOWLEDGE (NEW)
# ===========================================================================

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

WAREHOUSE FUNCTIONS:
- Inventory storage and management
- Order fulfillment and picking
- Delivery coordination
- Stock transfers between warehouses

Use warehouse information to optimize delivery times and stock allocation.
"""

# ===========================================================================
# 16. LOW STOCK ALERTS KNOWLEDGE (NEW)
# ===========================================================================

LOW_STOCK_ALERTS_KNOWLEDGE = """
🔔 LOW STOCK ALERTS

Low stock alerts notify you when inventory needs replenishment.

ALERT LEVELS:
- CRITICAL — 0-5 units available (reorder immediately)
- LOW — 5-20 units available (reorder soon)
- MEDIUM — 20-100 units available (monitor)

WHY ALERTS MATTER:
- Prevent stockouts and lost sales
- Plan reorders proactively
- Maintain customer satisfaction
- Optimize inventory levels

HOW TO USE:
- "Low stock alerts" — view all
- "Critical stock alerts" — most urgent
- "Low stock in [warehouse]" — location-specific

Combine with "Reorder decisions" for automated replenishment suggestions.
"""

# ===========================================================================
# 17. DELIVERY TRACKING KNOWLEDGE (NEW)
# ===========================================================================

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

TAKING ACTION:
- Overdue deliveries — Contact logistics
- Partially delivered — Check remaining items
- In transit — Estimated arrival times

Check outstanding deliveries regularly to ensure customer satisfaction.
"""

# ===========================================================================
# 18. CROSS-SELL & UPSELL KNOWLEDGE (NEW)
# ===========================================================================

CROSS_SELL_KNOWLEDGE = """
🔄 CROSS-SELL & UPSELL

CROSS-SELL: Complementary products customers often buy together

EXAMPLES:
- Fertilizer + Seeds — planting combo
- Pesticide + Protective gear — safety bundle
- VegiMax + Foliar spray — nutrition package

UPSELL: Premium alternatives with better features/benefits

EXAMPLES:
- Standard seed → Hybrid variety (higher yield)
- Basic fertilizer → Controlled-release (efficiency)
- Small pack → Bulk size (better value)

HOW TO FIND:
- "What else do customers buy with [product]?"
- "Better version of [product]"
- "Upgrade from [product]"

Use cross-sell and upsell to increase order value and customer satisfaction.
"""

# ===========================================================================
# 19. FOLLOW-UP QUOTATIONS KNOWLEDGE (NEW)
# ===========================================================================

FOLLOW_UP_KNOWLEDGE = """
📋 FOLLOW-UP QUOTATIONS

Managing quotations that haven't converted to orders.

PENDING QUOTATIONS:
- "Stale quotes" — sent but no response
- "Unconverted quotations" — not yet ordered
- "Customers with pending quotes" — who to follow up

FOLLOW-UP STRATEGIES:
1. Check if quotation expired
2. Confirm customer received it
3. Offer assistance with quantities
4. Provide price adjustments if needed
5. Remind of stock availability

BEST PRACTICES:
- Follow up within 3-5 days of sending
- Be helpful, not pushy
- Note customer feedback for improvement

Ask "Follow up on quotations" to see what needs attention.
"""

# ===========================================================================
# 20. PRICING OPPORTUNITIES KNOWLEDGE (NEW)
# ===========================================================================

PRICING_KNOWLEDGE = """
💰 PRICING OPPORTUNITIES

Identify pricing trends and opportunities in the market.

WHAT TO ANALYZE:
- "Price opportunities" — where to adjust pricing
- "Price drops" — items with decreased costs
- "Price hikes" — items with increased costs

OPPORTUNITIES:
- Bundle discounts — combine products for better value
- Volume pricing — lower price for larger quantities
- Seasonal promotions — time-based offers
- Customer-specific pricing — special agreements

HOW TO USE:
1. Review competitor prices
2. Analyze margin opportunities
3. Adjust pricing strategy
4. Create promotional quotes

Combine with "Competitor price check" for market comparison.
"""

# ===========================================================================
# 21. SUGGESTED FOLLOW-UP QUESTIONS
# ===========================================================================

SUGGESTED_FOLLOWUPS = {
    "GET_ITEMS": [
        "Check stock levels: 'Stock level for [item]'",
        "Get a price: 'Price of [item]'",
        "Create a quote: 'Create a quote for [customer] — [qty] [item]'",
    ],
    "GET_CUSTOMERS": [
        "View their orders: 'Orders for [customer name]'",
        "Check their invoices: 'Invoices for [customer name]'",
        "Get their pricing: 'Price of [item] for [customer name]'",
    ],
    "GET_ITEM_PRICE": [
        "Check stock: 'Stock level for [item]'",
        "Get customer-specific price: 'Price of [item] for [customer]'",
        "Create a quote: 'Create a quote for [customer] — [qty] [item]'",
    ],
    "GET_CUSTOMER_PRICE": [
        "Check stock: 'Stock level for [item]'",
        "Create a quote now: 'Create a quote for [customer] — [qty] [item]'",
        "View customer orders: 'Orders for [customer]'",
    ],
    "GET_STOCK_LEVELS": [
        "See items in a specific warehouse: 'Stock in [warehouse name]'",
        "Check low stock alerts: 'Low stock alerts'",
        "Get the price: 'Price of [item]'",
    ],
    "CREATE_QUOTATION": [
        "View all quotations: 'Show my quotations'",
        "Check delivery status: 'Outstanding deliveries'",
        "Look up another customer: 'Customer details for [name]'",
    ],
    "GREETING": [
        "Show me all items",
        "Show me customers",
        "Low stock alerts",
        "How do I create a quotation?",
    ],
    "FIND_CUSTOMERS_BY_ITEM": [
        "Show customer details for top customers",
        "Create quotation for these customers",
        "Show orders for these customers",
        "Find similar customers",
    ],
    "GET_TOP_SELLING_ITEMS": [
        "Check stock for top sellers: 'Stock level for [item]'",
        "Get pricing: 'Price of [item]'",
        "Create quotes: 'Create a quote for [customer] — [qty] [item]'",
        "See slow moving items: 'Show slow moving items'",
    ],
    "GET_SLOW_MOVING_ITEMS": [
        "Review pricing: 'Price opportunities'",
        "Consider promotions for slow movers",
        "Check stock levels: 'Stock level for [item]'",
        "See top sellers: 'Show top selling items'",
    ],
    "GET_SALES_ANALYTICS": [
        "See top selling items: 'Show top selling items'",
        "Check low stock alerts: 'Low stock alerts'",
        "Analyze inventory health: 'Inventory health'",
        "View customer behavior: 'Analyze customer behavior'",
    ],
    "GET_WAREHOUSES": [
        "Check stock in a warehouse: 'Stock in [warehouse name]'",
        "View low stock alerts: 'Low stock alerts'",
        "See all inventory items: 'Show me all items'",
    ],
    "GET_LOW_STOCK_ALERTS": [
        "Create reorder suggestions: 'Reorder decisions'",
        "Check full inventory: 'Stock levels'",
        "See critical items first",
        "Review warehouse stock: 'Stock in [warehouse]'",
    ],
    "GET_OUTSTANDING_DELIVERIES": [
        "Track specific delivery: 'Track delivery [order number]'",
        "Check delivery history: 'Delivery history for [customer]'",
        "View customer orders: 'Orders for [customer]'",
    ],
    "GET_CROSS_SELL": [
        "Check stock for suggested items",
        "Create a quote with multiple items",
        "See upgrade options: 'Better version of [product]'",
    ],
    "GET_UPSELL": [
        "Check premium item stock",
        "Compare pricing: 'Price of [premium item]'",
        "Create upgraded quotation",
    ],
}

# ===========================================================================
# CACHED FUNCTIONS
# ===========================================================================

@cache_kb(ttl_seconds=3600)
def get_knowledge(intent: str, query: str = "") -> str:
    """
    Returns the most relevant knowledge base content for a given intent.
    The LLM uses this as context to answer the user's question.
    """
    intent = intent.upper()

    knowledge_map = {
        # Core business info
        "COMPANY_INFO": COMPANY_PROFILE,
        "CONTACT_INFO": CONTACT_INFO,
        "PRODUCT_INFO": PRODUCTS_AND_BRANDS,
        "HOW_TO_ORDER": HOW_TO_ORDER,
        "CREATE_QUOTATION": HOW_TO_CREATE_QUOTATION,
        "PAYMENT_METHODS": PAYMENT_METHODS,
        "POLICY_QUESTION": PAYMENT_METHODS,
        "FAQ": FAQ,
        "GREETING": ONBOARDING_GUIDE,
        "SMALL_TALK": ONBOARDING_GUIDE,
        "RECOMMEND_ITEMS": SALES_REP_QUICK_REFERENCE,
        "RECOMMEND_CUSTOMERS": SALES_REP_QUICK_REFERENCE,
        
        # Training intents
        "TRAINING_MODULE": TRAINING_MODULES.get("TRAINING_MODULE", ""),
        "TRAINING_GUIDE": TRAINING_MODULES.get("TRAINING_GUIDE", ""),
        "TRAINING_FAQ": TRAINING_MODULES.get("TRAINING_FAQ", ""),
        "TRAINING_WEBINAR": TRAINING_MODULES.get("TRAINING_WEBINAR", ""),
        "TRAINING_VIDEO": TRAINING_MODULES.get("TRAINING_VIDEO", ""),
        
        # NEW: Analytics and reporting intents
        "GET_SALES_ANALYTICS": SALES_ANALYTICS_KNOWLEDGE,
        "GET_TOP_SELLING_ITEMS": TOP_SELLING_KNOWLEDGE,
        "GET_SLOW_MOVING_ITEMS": SLOW_MOVING_KNOWLEDGE,
        
        # NEW: Customer and sales intents
        "FIND_CUSTOMERS_BY_ITEM": CUSTOMER_SEGMENTATION_KNOWLEDGE,
        "GET_CUSTOMER_PRICE": "Customer-specific pricing is handled by the price lookup system. Ask 'Price of [item] for [customer name]' to get the correct price for a specific customer.",
        
        # NEW: Warehouse and inventory intents
        "GET_WAREHOUSES": WAREHOUSE_KNOWLEDGE,
        "GET_LOW_STOCK_ALERTS": LOW_STOCK_ALERTS_KNOWLEDGE,
        
        # NEW: Delivery intents
        "GET_OUTSTANDING_DELIVERIES": DELIVERY_KNOWLEDGE,
        "TRACK_DELIVERY": DELIVERY_KNOWLEDGE,
        "GET_DELIVERY_HISTORY": DELIVERY_KNOWLEDGE,
        
        # NEW: Customer detail intents
        "GET_CUSTOMER_DETAILS": "To get customer details, ask 'Show customer [name]' or 'Customer details for [name]'. This will show their contact info, credit status, and order history.",
        "GET_CUSTOMER_ORDERS": "To view customer orders, ask 'Orders for [customer name]'. This shows their purchase history, delivery status, and order values.",
        
        # NEW: Sales optimization intents
        "GET_CROSS_SELL": CROSS_SELL_KNOWLEDGE,
        "GET_UPSELL": CROSS_SELL_KNOWLEDGE,
        "GET_SEASONAL_RECOMMENDATIONS": "Seasonal recommendations depend on current planting seasons. Ask about specific crops or check with your sales manager for current seasonal promotions.",
        "GET_TRENDING_PRODUCTS": "Trending products are typically your top sellers. Ask 'Show top selling items' to see current trends.",
        "FOLLOW_UP_QUOTATIONS": FOLLOW_UP_KNOWLEDGE,
        
        # NEW: Pricing intents
        "PRICE_ALERT": PRICING_KNOWLEDGE,
        "MARKET_INTELLIGENCE": PRICING_KNOWLEDGE,
        "COMPETITOR_PRICE_CHECK": PRICING_KNOWLEDGE,
        "FIND_BEST_PRICE": PRICING_KNOWLEDGE,
        
        # NEW: Analytics intents
        "ANALYZE_INVENTORY_HEALTH": "Inventory health analysis is available through the system. Ask 'Inventory health' to see stock turnover, critical items, and recommendations.",
        "GET_REORDER_DECISIONS": "Reorder decisions are based on stock levels and sales velocity. Ask 'Reorder decisions' or check 'Low stock alerts' for immediate needs.",
        "ANALYZE_PRICING_OPPORTUNITIES": PRICING_KNOWLEDGE,
        "ANALYZE_CUSTOMER_BEHAVIOR": "Customer behavior analysis looks at purchase patterns, order frequency, and product preferences. Ask specific questions like 'What does customer X usually buy?'",
        "FORECAST_DEMAND": "Demand forecasting uses historical sales data. For accurate forecasts, ask your sales manager or check the analytics dashboard.",
    }

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

    content = knowledge_map.get(intent, FAQ)

    followups = SUGGESTED_FOLLOWUPS.get(intent, [])
    if followups:
        content += "\n\n--- YOU MIGHT ALSO WANT TO ---\n"
        content += "\n".join(f"- {f}" for f in followups)

    return content


@cache_kb(ttl_seconds=3600)
def get_company_info() -> dict:
    """Returns structured company info dict."""
    return {
        "name": "Leysco Limited",
        "tagline": "Simply Reliable",
        "about": (
            "Leysco is a software development and consultancy company specialising in "
            "enterprise-wide Resource Planning and Management Systems that support critical "
            "business processes and decision-making for organisations in Kenya."
        ),
        "values": [
            "Safety — ensuring system and data security",
            "Stability — reliable, always-on systems",
            "Technical Support — responsive IT support",
            "Complete Solutions — end-to-end implementation",
        ],
        "phone": "+254(0) 780 457 591",
        "email": "info@leysco.com",
        "website": "https://leysco.com",
        "address": "APA Arcade, Hurlingham, Nairobi, Kenya",
    }


@cache_kb(ttl_seconds=3600)
def get_brand_info() -> dict:
    """Returns structured product brand/category info dict."""
    return {
        "seeds": {
            "name": "Seeds Division",
            "category": "Seeds & Planting Material",
            "description": "Certified vegetable, maize, and field crop seeds.",
            "key_products": ["Hybrid Cabbage", "Tomato F1 hybrids", "Maize hybrids", "Vegetable seeds"],
        },
        "fertilizers": {
            "name": "Fertilizers Division",
            "category": "Crop Nutrition",
            "description": "Straight and compound fertilizers for all crop stages.",
            "key_products": ["DAP", "CAN", "NPK blends", "Foliar fertilizers"],
        },
        "agro_chemicals": {
            "name": "Agro-Chemicals Division",
            "category": "Crop Protection",
            "description": "Licensed pesticides, herbicides, and fungicides.",
            "key_products": ["VegiMax", "Fungicides", "Herbicides", "Insecticides"],
        },
    }


@cache_kb(ttl_seconds=3600)
def get_ordering_info() -> dict:
    """Returns structured ordering and payment info dict."""
    return {
        "how_to_order": HOW_TO_ORDER,
        "how_to_quote": HOW_TO_CREATE_QUOTATION,
        "payment_terms": {
            "available_methods": ["M-Pesa", "Bank Transfer", "Cash", "Cheque"],
            "credit_terms": "Credit customers: 30/60 days. New customers: Cash on Delivery.",
        },
        "delivery": "Deliveries managed through Logistics Hub. Ask 'outstanding deliveries'.",
    }


@cache_kb(ttl_seconds=3600)
def get_contact_info() -> dict:
    """Returns structured contact info dict."""
    return {
        "customer_support": {
            "phone": "+254(0) 780 457 591",
            "email": "info@leysco.com",
            "hours": "Monday – Friday, 8:00 AM – 5:00 PM EAT",
        },
        "sales_regions": [
            {"name": "Nairobi & Central", "contact": "Contact head office"},
            {"name": "Rift Valley", "contact": "Contact head office"},
            {"name": "Western Kenya", "contact": "Contact head office"},
        ],
        "technical_support": "Email: info@leysco.com | Phone: +254(0) 780 457 591",
        "address": "APA Arcade, Hurlingham, Nairobi, Kenya",
        "website": "https://leysco.com",
    }


@cache_kb(ttl_seconds=3600)
def get_policies() -> dict:
    """Returns structured policy info dict."""
    return {
        "returns": "Returns accepted within 7 days with original receipt. Agro-chemicals: No returns once opened.",
        "quality_guarantee": "All seeds are certified. Products failing quality standards will be replaced.",
        "credit_policy": "Credit limits set per customer based on payment history.",
        "delivery_policy": "All deliveries require a signed gate pass.",
    }


@cache_kb(ttl_seconds=1800)
def get_faq_answer(query: str) -> str:
    """Returns the most relevant FAQ answer for a given query string."""
    query_lower = (query or "").lower()

    if any(w in query_lower for w in ["stock", "inventory", "available"]):
        return "To check stock levels, ask: 'Stock level for [item name]' or 'Low stock alerts'"

    if any(w in query_lower for w in ["price", "cost", "how much"]):
        return "To check prices: 'Price of [item]' or 'Price of [item] for [customer]'"

    if any(w in query_lower for w in ["order", "quotation", "quote", "create"]):
        return HOW_TO_CREATE_QUOTATION

    if any(w in query_lower for w in ["payment", "pay", "mpesa", "bank", "cash"]):
        return PAYMENT_METHODS

    if any(w in query_lower for w in ["deliver", "dispatch", "logistics"]):
        return "To track deliveries: 'Outstanding deliveries' or 'Delivery history for [customer]'"

    if any(w in query_lower for w in ["customer", "client", "account"]):
        return "To look up customers: 'Show customer [name]' or 'Customer details for [name]'"
    
    if any(w in query_lower for w in ["top selling", "best seller", "popular"]):
        return TOP_SELLING_KNOWLEDGE
    
    if any(w in query_lower for w in ["slow moving", "least popular", "not selling"]):
        return SLOW_MOVING_KNOWLEDGE
    
    if any(w in query_lower for w in ["sales analytics", "sales report", "revenue"]):
        return SALES_ANALYTICS_KNOWLEDGE

    return FAQ


def get_sales_rep_reference() -> str:
    """Returns the quick reference cheat sheet for sales reps."""
    return SALES_REP_QUICK_REFERENCE


def get_onboarding_guide() -> str:
    """Returns the new user onboarding guide."""
    return ONBOARDING_GUIDE


def get_glossary_term(term: str) -> str:
    """Look up a single glossary term."""
    return GLOSSARY.get(term.upper(), f"Term '{term}' not found in glossary.")


def get_sales_analytics_knowledge() -> str:
    """Returns sales analytics knowledge content."""
    return SALES_ANALYTICS_KNOWLEDGE


def get_top_selling_knowledge() -> str:
    """Returns top selling items knowledge content."""
    return TOP_SELLING_KNOWLEDGE


def get_slow_moving_knowledge() -> str:
    """Returns slow moving items knowledge content."""
    return SLOW_MOVING_KNOWLEDGE


def clear_knowledge_cache():
    """Clear the knowledge base cache."""
    # Clear function-specific caches
    get_knowledge.cache_clear()
    get_company_info.cache_clear()
    get_brand_info.cache_clear()
    get_ordering_info.cache_clear()
    get_contact_info.cache_clear()
    get_policies.cache_clear()
    get_faq_answer.cache_clear()
    logger.info("Knowledge base cache cleared")