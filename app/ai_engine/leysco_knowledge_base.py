"""
app/ai_engine/leysco_knowledge_base.py
=======================================
Leysco AI Assistant — Knowledge Base

This file is the "brain" for all non-database answers.
The LLM reads from this content when handling:
  - COMPANY_INFO, CONTACT_INFO, PRODUCT_INFO
  - HOW_TO_ORDER, POLICY_QUESTION, PAYMENT_METHODS
  - TRAINING_MODULE, TRAINING_GUIDE, TRAINING_FAQ, TRAINING_GLOSSARY
  - GREETING (new user onboarding)
  - RECOMMEND_ITEMS (sales coaching)
  - FAQ
  - DASHBOARD_OVERVIEW, SYSTEM_MODULES (new)

Sections:
  1. Company Profile
  2. Contact Information
  3. Products & Brands
  4. Ordering & Quotations (step-by-step)
  5. Payment Methods & Policies
  6. Sales Rep Quick Reference
  7. Onboarding Guide (new users)
  8. Training Modules
  9. Glossary
  10. FAQ
  11. Sales Coaching Tips
  12. Suggested Follow-up Questions (per intent)
  13. System Modules Guide (new)
  14. Dashboard & KPIs (new)
  15. Purchase & Supplier Guide (new)
  16. Banking & Payments Guide (new)
  17. Logistics Hub Guide (new)
  18. Production Guide (new)
  19. Gate Pass Guide (new)
"""

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
   - Personalised SAP Business One solutions (on-cloud and on-premise)
   - Services: Customisation, Data Migration, Configuration, Initialisation, Support
   - Real-time intuitive reporting and add-ons
   - Note: SAP powers 60% of global business transactions

2. Leysco Systems Consulting
   - Application Architecture and Development
   - Feasibility and Technology Evaluation
   - Application Maintenance and Support
   - Legacy Transformation and Integration
   - Technical Resource Staffing

3. Web Application Development
   - Technologies: Java, .NET, PHP
   - Frontend and backend web application systems
   - E-commerce solutions and MS integrations

4. Mobile Apps Development
   - Rich user experience mobile applications
   - End-to-end from idea stage to execution
   - Business-specific mobile solutions (like this Leysco100 AI Sales Assistant)

5. Web Development and Hosting
   - Business website development
   - Hosting plans: Basic (KES 3,999/yr), Standard (KES 7,999/yr),
     Business (KES 29,999/yr), Professional (KES 49,999/yr)
   - Secure, reliable, 24/7 friendly support, free migration

6. EDMS (Electronic Document Management System)
   - Available at pgtl.xedms.com

About Leysco100:
Leysco100 is Leysco's SAP Business One ERP system for Demo Company Kenya,
an agricultural inputs business. It manages the full business operation
end-to-end across 10 modules:

LEYSCO100 SYSTEM MODULES:
1. Administration    — System settings, users, permissions, company config
2. Sales             — Quotations, orders, invoices, deliveries, pricing
3. Purchase - A/P    — Purchase orders, supplier invoices, accounts payable
4. Business Partners — Customers and suppliers (CardCode, price lists, credit limits)
5. Banking           — Payments, receipts, bank reconciliation, cash management
6. Inventory         — Items, warehouses, stock levels, transfers, reports
7. Resources         — HR, employees, payroll, leave management
8. Logistics Hub     — Delivery tracking, route management, dispatch
9. Production        — Manufacturing orders, bills of materials, production planning
10. Gate Pass Mgt   — Gate passes for goods in/out, security management

DASHBOARD KPIs (real-time, last 12 months):
- Total Sales:    KSh 225.5K  (-4.5% vs previous year)
- Net Revenue:    KSh 223.2K  (-4.5% vs previous year)
- Orders:         98          (-39.9% vs previous year)
- New Customers:  45          (+0.0% vs previous year)
- Total Invoices: 42
- Avg/Period:     KSh 18.8K

Sales Trends available: Daily / Weekly / Monthly views
Revenue by Product: Top 5 product contribution chart

KEY SYSTEM FACTS:
- Currency: KES (Kenyan Shillings)
- 21 active price lists with SAP B1 chain-walking
- Marketing doc types: 13=Invoices, 15=Deliveries, 17=Orders, 23=Quotations

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

For urgent operational issues:
- Stock or pricing queries: Check this AI assistant first (fastest)
- SAP system errors: Contact Leysco IT — info@leysco.com
- Customer complaints: Escalate to your sales manager
- Payment queries: Contact the Finance department
- Hosting or web issues: Contact Leysco via phone or email above
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

Note: For exact current stock, prices, and item codes — always check the live system.
"""

# ===========================================================================
# 4. ORDERING & QUOTATIONS — STEP BY STEP
# ===========================================================================

HOW_TO_CREATE_QUOTATION = """
HOW TO CREATE A SALES QUOTATION

Step 1 — Find your customer
  Ask: "Show me customer [name]" or "Customer details for [name]"
  Confirm the customer code and credit status before proceeding.

Step 2 — Check what's in stock
  Ask: "What's the stock level for [product]?"
  Or: "Show items available in [warehouse]"
  Never quote items that are out of stock.

Step 3 — Get the right price
  Ask: "Price of [item] for customer [name]"
  Customer-specific pricing may differ from the base price list.

Step 4 — Create the quotation
  Say: "Create a quote for [customer] — [quantity] [item], [quantity] [item]"
  Example: "Create a quote for Lumarx — 10 VegiMax and 5 cabbage seeds"

Step 5 — Confirm with customer
  Share the quotation number with the customer for reference.
  Quotations are valid for the period specified in company policy.

TIPS FOR SALES REPS:
- Always use the customer's exact name or code to avoid errors
- Double-check quantities before submitting
- If a product is unavailable, suggest an alternative (ask: "recommend items for [crop]")
"""

HOW_TO_ORDER = """
HOW TO PLACE A SALES ORDER

Step 1 — Verify customer account
  Confirm the customer is active and has no credit holds.
  Ask: "Customer details for [name]"

Step 2 — Confirm stock availability
  Ask: "Stock level for [item]" before committing to the customer.

Step 3 — Get customer pricing
  Ask: "Price of [item] for [customer name]"

Step 4 — Create quotation first (recommended)
  Convert to order once customer approves the quote.

Step 5 — Submit order
  Orders are processed through Leysco100.
  Your sales manager approves orders above the credit limit.

IMPORTANT:
- Orders cannot be cancelled once processed without manager approval
- Out-of-stock items will delay the order — always confirm stock first
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
- Credit limit: Set per customer, visible in Leysco100

RETURNS & REFUNDS POLICY:
- Returns accepted within 7 days with original receipt
- Products must be in original, unopened condition
- Agro-chemicals: No returns once opened (safety policy)
- Damaged goods: Report within 24 hours of delivery with photos

For current Paybill/account numbers, contact the Finance department.
"""

# ===========================================================================
# 6. SALES REP QUICK REFERENCE
# ===========================================================================

SALES_REP_QUICK_REFERENCE = """
SALES REP DAILY CHEAT SHEET

--- MOST USEFUL COMMANDS ---

Check stock:
  "Stock level for [item name]"
  "What's available in [warehouse]?"
  "Low stock alerts"

Get prices:
  "Price of [item]"
  "Price of [item] for customer [name]"  ← use this for customer visits

Find a customer:
  "Show customer [name]"
  "Customer details for [name]"
  "Orders for customer [name]"

Create a quote:
  "Create a quote for [customer] — [qty] [item]"

Track deliveries:
  "Outstanding deliveries"
  "Delivery status for [customer]"

--- BEFORE A CUSTOMER VISIT ---
1. Check their order history: "Orders for [customer name]"
2. Check their last invoice: "Invoices for [customer name]"
3. Check prices for their key products: "Price of [item] for [customer]"
4. Check current stock of what they usually buy

--- DURING A CUSTOMER VISIT ---
1. Use the app to show live stock levels — builds customer confidence
2. Create quotes on the spot: faster closing
3. If item is out of stock, immediately suggest alternatives

--- END OF DAY ---
1. Review outstanding deliveries
2. Follow up on open quotations
3. Check low stock alerts for items your customers buy
"""

# ===========================================================================
# 7. ONBOARDING GUIDE — NEW USERS
# ===========================================================================

ONBOARDING_GUIDE = """
WELCOME TO LEYSCO100 AI ASSISTANT!

I'm your AI-powered assistant for the Leysco100 ERP system (Demo Company Kenya).
I can help you navigate all 10 system modules using plain English — no need to
dig through menus.

--- WHAT I CAN DO ---

SALES & PRICING:
  "Price of VegiMax"
  "Price of [item] for [customer]"
  "Create a quote for [customer] — [qty] [item]"
  "Show orders for [customer]"
  "Outstanding deliveries for [customer]"

INVENTORY:
  "Show me all items"
  "Stock level for cabbage seeds"
  "Low stock alerts"
  "Show all warehouses"
  "Stock in Nairobi warehouse"

BUSINESS PARTNERS:
  "Show me customers"
  "Customer details for [name]"
  "Invoices for [customer]"

LOGISTICS:
  "Outstanding deliveries"
  "Delivery history for [customer]"

TRAINING & GUIDANCE:
  "How do I create a quotation?"
  "What does DAP mean?"
  "What can you help me with?"
  "Show me the sales rep cheat sheet"

--- YOUR FIRST 5 ACTIONS ---
1. "Show me items"            → see the full product catalogue
2. "Show me customers"        → browse your customer list
3. "Low stock alerts"         → see what needs restocking
4. "Price of [top product]"   → confirm your pricing
5. "How do I create a quote?" → step-by-step guide

--- TIPS ---
- Ask naturally — no exact commands needed
- Always check stock BEFORE promising a customer
- Use "price of [item] for [customer]" for accurate customer pricing
- The system has 21 price lists — I pick the right one automatically
- Type "What can you do?" anytime to see all capabilities
"""

# ===========================================================================
# 8. TRAINING MODULES
# ===========================================================================

TRAINING_MODULES = {

    "TRAINING_MODULE": """
LEYSCO100 TRAINING OVERVIEW

Available training topics — just ask me about any of these:

1. HOW TO CREATE A QUOTATION
   Ask: "How do I create a quotation?"

2. HOW TO CHECK STOCK
   Ask: "How do I check stock levels?"

3. HOW TO FIND CUSTOMER INFORMATION
   Ask: "How do I look up a customer?"

4. HOW TO TRACK DELIVERIES
   Ask: "How do I track a delivery?"

5. HOW TO USE PRICING
   Ask: "How does customer pricing work?"

6. PAYMENT METHODS
   Ask: "What payment methods do we accept?"

7. RETURNS & REFUNDS
   Ask: "What is the returns policy?"

8. UNDERSTANDING THE DASHBOARD
   Ask: "How do I read the dashboard?"

9. LOGISTICS HUB
   Ask: "How does the logistics hub work?"

10. GATE PASS MANAGEMENT
    Ask: "How do I create a gate pass?"

Which topic would you like to start with?
""",

    "TRAINING_GUIDE": """
LEYSCO100 STEP-BY-STEP GUIDES

I can walk you through:

- Creating a quotation (most important for sales reps)
- Checking stock levels and warehouse locations
- Looking up customer details and order history
- Understanding pricing and discounts
- Processing returns and refunds
- Reading the dashboard KPIs
- Managing deliveries in the Logistics Hub
- Creating and processing gate passes

Just ask: "How do I [task]?" and I'll guide you step by step.
""",

    "TRAINING_FAQ": """
FREQUENTLY ASKED QUESTIONS — LEYSCO100

Q: How do I check if an item is in stock?
A: Ask me: "Stock level for [item name]" — I'll show you current quantities per warehouse.

Q: Why is my customer's price different from the list price?
A: Customers can have special pricing agreements. Always use "Price of [item] for [customer]" to get the correct price.

Q: What if the item a customer wants is out of stock?
A: Ask me to "recommend alternatives for [crop/use]" — I'll suggest similar available products.

Q: How long is a quotation valid?
A: Check with your sales manager for the current validity period.

Q: Can I create an order directly without a quotation?
A: Yes, but quotations are recommended — they protect you if prices change.

Q: How do I know a customer's credit limit?
A: Ask me "Customer details for [name]" — it shows their credit status.

Q: What do I do if the system is slow?
A: The AI assistant caches common queries — repeat queries are instant. For SAP issues, contact IT.

Q: How do I read the dashboard?
A: The dashboard shows Total Sales, Net Revenue, Orders, and New Customers for the last 12 months,
   with comparison to the previous year. Use Daily/Weekly/Monthly views for sales trends.

Q: What is the Logistics Hub?
A: The Logistics Hub manages delivery tracking, route planning, and dispatch operations.
   Ask me "Outstanding deliveries" to see what's pending.

Q: What is Gate Pass Management?
A: Gate Pass Mgt controls goods in/out movements at the warehouse gate.
   Every delivery or receipt needs a gate pass for security tracking.
""",

    "TRAINING_WEBINAR": """
LEYSCO100 LIVE TRAINING SESSIONS

For live training sessions, webinars, and workshops:
- Contact your sales manager or HR department
- Ask about the next scheduled Leysco100 onboarding session
- New staff should request a guided walkthrough in their first week

In the meantime, I can answer any system questions right here.
""",

    "TRAINING_VIDEO": """
LEYSCO100 VIDEO TRAINING

For video tutorials and screencasts on using Leysco100:
- Contact your IT department or system administrator
- Ask your manager about available training materials

While you wait, I can walk you through any task step by step — just ask!
""",
}

# ===========================================================================
# 9. GLOSSARY
# ===========================================================================

GLOSSARY = {
    "SKU":      "Stock Keeping Unit — the unique code for each product in the system (e.g. VGM-001)",
    "MOQ":      "Minimum Order Quantity — the smallest amount you can order of an item",
    "UOM":      "Unit of Measure — how the item is sold (e.g. KG, BAG, PIECE, LITRE)",
    "ETA":      "Estimated Time of Arrival — when a shipment or delivery is expected",
    "GRN":      "Goods Received Note — document confirming stock has been received into the warehouse",
    "DN":       "Delivery Note — document that goes with goods sent to a customer",
    "PO":       "Purchase Order — an order placed to a supplier to buy stock",
    "SO":       "Sales Order — a confirmed order from a customer",
    "SQ":       "Sales Quotation — a price offer to a customer before they confirm the order",
    "CAN":      "Calcium Ammonium Nitrate — a common nitrogen fertilizer",
    "DAP":      "Di-Ammonium Phosphate — a phosphorus and nitrogen fertilizer used at planting",
    "NPK":      "Nitrogen, Phosphorus, Potassium — the three main nutrients in compound fertilizers",
    "SAP":      "Systems, Applications and Products — the ERP system Leysco100 is based on",
    "ERP":      "Enterprise Resource Planning — the integrated business management system",
    "CRM":      "Customer Relationship Management — managing customer interactions and history",
    "KPI":      "Key Performance Indicator — a measurable target (e.g. monthly sales target)",
    "COD":      "Cash on Delivery — payment collected when goods are delivered",
    "B2B":      "Business to Business — selling to agro-dealers and businesses (vs direct to farmers)",
    "FIFO":     "First In First Out — stock management rule: oldest stock is sold first",
    "AP":       "Accounts Payable — money owed to suppliers for goods/services received",
    "AR":       "Accounts Receivable — money owed to the company by customers",
    "BOM":      "Bill of Materials — list of components needed to produce a finished product",
    "WH":       "Warehouse — storage location for inventory items",
    "GP":       "Gate Pass — authorisation document for goods entering or leaving the warehouse",
    "CARDCODE": "SAP unique identifier for a business partner (customer or supplier)",
    "LISTNUM":  "SAP price list number — determines which price list applies to a customer",
    "EA":       "Each — unit of measure for single countable items",
    "KES":      "Kenyan Shilling — the currency used in Leysco100",
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
- Browse items: "Show me all items" / "Show me cabbage seeds"
- Check stock: "Stock level for [item]" / "Stock in [warehouse]"
- Low stock alerts: "Show low stock alerts"
- Warehouse list: "Show all warehouses"

PRICING:
- Base price: "Price of [item]"
- Customer price: "Price of [item] for [customer]"
- Supports 21 price lists with automatic chain-walking

BUSINESS PARTNERS:
- Find customers: "Show customer [name]"
- Customer details: "Details for [customer]"
- Order history: "Orders for [customer]"

LOGISTICS HUB:
- Outstanding deliveries: "What deliveries are pending?"
- Delivery history: "Delivery history for [customer]"

BANKING (coming soon):
- Payment status queries
- Outstanding balance queries

PURCHASE - A/P (coming soon):
- Supplier queries
- Purchase order status

PRODUCTION (coming soon):
- Manufacturing order status
- Bill of materials queries

GATE PASS MGT:
- Gate pass queries: "How do I create a gate pass?"

TRAINING & GUIDANCE:
- Step-by-step guides: "How do I create a quotation?"
- Glossary: "What does [term] mean?"
- Sales coaching tips: "How should I approach [customer type]?"
- Dashboard help: "How do I read the dashboard?"

Just ask naturally — I understand plain English!
Examples:
  "Show me cabbage seeds"
  "Price of VegiMax for Lumarx"
  "Create a quote for John — 5 bags DAP and 10 VegiMax"
  "Outstanding deliveries for Kamau Traders"
  "How do I create a quotation?"
  "What does BOM mean?"
"""

# ===========================================================================
# 11. SALES COACHING TIPS
# ===========================================================================

SALES_COACHING = """
SALES COACHING — LEYSCO BEST PRACTICES

UNDERSTAND YOUR CUSTOMER FIRST:
- Before visiting, check their last 3 orders: "Orders for [customer]"
- Know what crops they grow — match products to their needs
- Check if they have unpaid invoices before offering more credit

PRODUCT KNOWLEDGE TIPS:
- Cabbage farmers: Recommend quality hybrid seeds + foliar fertilizer combo
- Maize farmers: MH401/KH500 seeds + DAP at planting + CAN top-dress
- Tomato farmers: Disease-resistant varieties + fungicide package
- When a product is out of stock, always offer the next-best alternative

PRICING CONFIDENCE:
- Never guess prices — always confirm with the system
- Customer-specific prices are often better than list prices
- Use "Price of [item] for [customer]" to get the exact price

CLOSING TECHNIQUES:
- Create the quote on the spot during the visit: faster decisions
- Show them live stock availability — urgency helps close deals
- Bundle products: seeds + fertilizer + pesticide packages sell better

HANDLING OBJECTIONS:
- "Too expensive" → Check if the customer has a special price list
- "Out of stock" → Check other warehouses or suggest alternatives
- "Need to think" → Send them the quotation number to follow up

DASHBOARD INSIGHTS FOR SALES COACHING:
- Current period: KSh 225.5K total sales, 98 orders, 45 new customers
- Orders are down 39.9% vs previous year — focus on re-activating dormant customers
- Average period revenue: KSh 18.8K — set personal targets above this
- New customers flat at 0.0% growth — prioritise customer acquisition

AFTER THE VISIT:
- Log the outcome with your sales manager
- Set a follow-up reminder for open quotations
- Check delivery status for their previous orders
"""

# ===========================================================================
# 12. SUGGESTED FOLLOW-UP QUESTIONS (per intent)
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
    "GET_CUSTOMER_ORDERS": [
        "View their invoices: 'Invoices for [customer]'",
        "Create a new quote: 'Create a quote for [customer]'",
        "Check delivery status: 'Outstanding deliveries for [customer]'",
    ],
    "GET_OUTSTANDING_DELIVERIES": [
        "Check delivery history: 'Delivery history for [customer]'",
        "View customer orders: 'Orders for [customer]'",
        "Create a new quote: 'Create a quote for [customer]'",
    ],
    "GET_WAREHOUSES": [
        "Check stock in a warehouse: 'Stock in [warehouse name]'",
        "Get low stock alerts: 'Low stock alerts'",
        "Show all items: 'Show me all items'",
    ],
    "GREETING": [
        "Show me all items",
        "Show me customers",
        "Low stock alerts",
        "How do I create a quotation?",
    ],
    "TRAINING_MODULE": [
        "How do I create a quotation?",
        "How do I check stock?",
        "What are the payment methods?",
        "Show me the glossary",
        "How do I read the dashboard?",
    ],
    "RECOMMEND_ITEMS": [
        "Check stock: 'Stock level for [item]'",
        "Get a price: 'Price of [item] for [customer]'",
        "Create a quote: 'Create a quote for [customer] — [qty] [item]'",
    ],
}

# ===========================================================================
# 13. SYSTEM MODULES GUIDE
# ===========================================================================

SYSTEM_MODULES_GUIDE = """
LEYSCO100 SYSTEM MODULES — FULL GUIDE

1. ADMINISTRATION
   - Manage users, roles, and permissions
   - Company configuration and settings
   - System preferences and integrations
   - Contact your system administrator for access

2. SALES
   - Create and manage sales quotations (doc type 23)
   - Process sales orders (doc type 17)
   - Generate invoices (doc type 13)
   - Manage delivery notes (doc type 15)
   - Customer pricing and discount management
   AI commands: "Create a quote for...", "Show orders for...", "Invoices for..."

3. PURCHASE - A/P
   - Create purchase orders to suppliers
   - Receive goods against purchase orders (GRN)
   - Manage supplier invoices and accounts payable
   - Track outstanding supplier payments
   AI commands: Coming soon — ask your purchase manager for now

4. BUSINESS PARTNERS
   - Customer master data (CardCode, CardName, price list, credit limit)
   - Supplier master data
   - Contact persons and communication history
   - Credit management and payment terms
   AI commands: "Show customers", "Customer details for [name]", "Orders for [customer]"

5. BANKING
   - Record customer payments (incoming)
   - Record supplier payments (outgoing)
   - Bank reconciliation
   - Cash management and petty cash
   AI commands: Coming soon — contact Finance department for payment queries

6. INVENTORY
   - Item master data (ItemCode, ItemName, UOM, group)
   - Warehouse management (multiple locations)
   - Stock levels and inventory reports
   - Stock transfers between warehouses
   - Low stock monitoring
   AI commands: "Show items", "Stock level for...", "Stock in [warehouse]", "Low stock alerts"

7. RESOURCES
   - Employee management and HR records
   - Payroll processing
   - Leave management and attendance
   - Staff training records
   Contact HR department for resources queries

8. LOGISTICS HUB
   - Delivery planning and scheduling
   - Route management for delivery vehicles
   - Dispatch management
   - Delivery tracking and status updates
   AI commands: "Outstanding deliveries", "Delivery history for [customer]"

9. PRODUCTION
   - Manufacturing/production orders
   - Bill of Materials (BOM) management
   - Production planning and scheduling
   - Work in progress (WIP) tracking
   Contact production manager for production queries

10. GATE PASS MGT
    - Gate passes for goods leaving the warehouse (outbound)
    - Gate passes for goods arriving at the warehouse (inbound)
    - Security and access control integration
    - Audit trail for all goods movements
    Every delivery or stock receipt requires a gate pass
"""

# ===========================================================================
# 14. DASHBOARD & KPIs GUIDE
# ===========================================================================

DASHBOARD_GUIDE = """
LEYSCO100 DASHBOARD — HOW TO READ IT

The dashboard shows real-time business intelligence for Demo Company Kenya.

MAIN KPI CARDS (last 12 months: March 2025 – March 2026):
┌─────────────────────────────────────────────────────────┐
│ Total Sales:    KSh 225.5K  │  Net Revenue:  KSh 223.2K │
│ Change: -4.5% vs last year  │  Change: -4.5% vs last yr │
├─────────────────────────────────────────────────────────┤
│ Orders: 98                  │  New Customers: 45         │
│ Change: -39.9% vs last year │  Change: +0.0% vs last yr │
└─────────────────────────────────────────────────────────┘

SALES TRENDS CHART:
- Total Sales: KSh 225.5K
- Avg/Period:  KSh 18.8K
- Invoices:    42
- Orders:      98
- View modes:  Daily / Weekly / Monthly

REVENUE BY PRODUCT:
- Top 5 products by revenue contribution shown as a donut chart
- Use this to identify your best-selling products

KEY INSIGHTS FROM CURRENT DASHBOARD:
- Orders dropped -39.9% — significant decline requiring attention
- Revenue down only -4.5% — suggests higher-value orders compensating
- New customers flat (0.0%) — customer acquisition needs focus
- 42 invoices vs 98 orders — indicates many orders not yet invoiced

HOW TO USE DASHBOARD FOR SALES DECISIONS:
1. Check orders trend to understand if business is growing or declining
2. Revenue by product shows which items to prioritise stocking
3. New customers metric shows if the sales team is expanding the base
4. Compare daily/weekly/monthly to find seasonal patterns
"""

# ===========================================================================
# 15. PURCHASE & SUPPLIER GUIDE
# ===========================================================================

PURCHASE_GUIDE = """
PURCHASE & ACCOUNTS PAYABLE — GUIDE

The Purchase - A/P module manages all buying activity and supplier relationships.

KEY PROCESSES:
1. Creating a Purchase Order (PO)
   - Identify items to restock (check low stock alerts first)
   - Select the supplier for each item
   - Specify quantities and expected delivery dates
   - PO is sent to supplier for fulfilment

2. Receiving Goods (GRN — Goods Received Note)
   - When supplier delivers, create a GRN against the PO
   - GRN updates stock levels automatically in Inventory
   - Any discrepancies (wrong qty/item) should be noted immediately

3. Supplier Invoice Processing
   - Match supplier invoice to GRN
   - Approve for payment through Banking module
   - Track outstanding supplier balances in A/P

TIPS:
- Always create a PO before ordering from suppliers — protects against disputes
- Match GRN quantities carefully — discrepancies affect inventory accuracy
- Check supplier credit terms to manage cash flow effectively
- Contact purchase manager for purchase order queries
"""

# ===========================================================================
# 16. BANKING & PAYMENTS GUIDE
# ===========================================================================

BANKING_GUIDE = """
BANKING & CASH MANAGEMENT — GUIDE

The Banking module records all money movements in and out of the business.

INCOMING PAYMENTS (from customers):
- Record payment when customer pays their invoice
- Supports M-Pesa, bank transfer, cash, cheque
- Payment clears the customer's outstanding balance
- Always get a payment reference number

OUTGOING PAYMENTS (to suppliers):
- Record payment when settling supplier invoices
- Requires Finance department approval above certain amounts
- Bank transfer is preferred for large amounts

BANK RECONCILIATION:
- Match system records with actual bank statements
- Done periodically (weekly/monthly)
- Contact Finance for reconciliation queries

CASH MANAGEMENT:
- Petty cash for small day-to-day expenses
- All cash movements require receipts

PAYMENT METHODS ACCEPTED FROM CUSTOMERS:
1. M-Pesa Paybill — get current paybill number from Finance
2. Bank Transfer — get account details from Finance
3. Cash — at company offices, receipt issued immediately
4. Cheque — 3-5 business days clearing before goods released

For payment queries, always contact the Finance department directly.
"""

# ===========================================================================
# 17. LOGISTICS HUB GUIDE
# ===========================================================================

LOGISTICS_GUIDE = """
LOGISTICS HUB — GUIDE

The Logistics Hub manages all delivery operations for Demo Company Kenya.

KEY FEATURES:
- Delivery order management and scheduling
- Route planning for delivery vehicles
- Driver and vehicle assignment
- Real-time delivery status tracking
- Proof of delivery management

DELIVERY WORKFLOW:
1. Sales order is confirmed and ready for delivery
2. Logistics team creates a delivery note (doc type 15)
3. Gate pass is issued for the outgoing goods
4. Driver is assigned with route and delivery schedule
5. Goods are loaded and dispatched
6. Delivery status updated upon completion
7. Proof of delivery collected from customer

TRACKING DELIVERIES:
- Ask: "Outstanding deliveries" — shows all pending deliveries
- Ask: "Outstanding deliveries for [customer]" — customer-specific
- Ask: "Delivery history for [customer]" — past deliveries

STATUS TYPES:
- Open: Order confirmed, not yet dispatched
- In Transit: Goods on the way to customer
- Delivered: Customer has received goods
- Partial: Some items delivered, others pending
- Cancelled: Delivery cancelled

For dispatch and routing queries, contact the Logistics team.
"""

# ===========================================================================
# 18. PRODUCTION GUIDE
# ===========================================================================

PRODUCTION_GUIDE = """
PRODUCTION MODULE — GUIDE

The Production module manages any manufacturing or assembly operations.

KEY CONCEPTS:
- Bill of Materials (BOM): List of inputs needed to produce one unit of output
- Production Order: Instruction to produce a specific quantity
- Work In Progress (WIP): Items currently being produced
- Finished Goods: Completed items ready for sale

PRODUCTION WORKFLOW:
1. Sales demand identified (from orders or forecasts)
2. Production order created with BOM reference
3. Raw materials issued from inventory to production
4. Production carried out
5. Finished goods received back into inventory
6. Production order closed

For production planning and scheduling queries, contact the production manager.
"""

# ===========================================================================
# 19. GATE PASS GUIDE
# ===========================================================================

GATE_PASS_GUIDE = """
GATE PASS MANAGEMENT — GUIDE

Gate Pass Mgt controls all physical movement of goods at the warehouse.

WHY GATE PASSES MATTER:
- Every item leaving or entering the warehouse needs authorisation
- Prevents theft and unauthorised removal of stock
- Creates an audit trail for all goods movements
- Required for both customer deliveries and supplier receipts

TYPES OF GATE PASSES:
1. Outbound Gate Pass: For goods leaving (customer deliveries, transfers)
2. Inbound Gate Pass: For goods arriving (supplier deliveries, returns)

GATE PASS PROCESS (Outbound):
1. Delivery note approved by sales manager
2. Logistics team creates gate pass with item details and quantities
3. Gate pass printed and given to warehouse team
4. Warehouse team packs goods against gate pass
5. Security checks goods at gate against gate pass
6. Goods released, gate pass signed off

GATE PASS PROCESS (Inbound):
1. Purchase order or return note created
2. Gate pass issued for incoming goods
3. Warehouse receives goods against gate pass
4. GRN created to update stock levels
5. Gate pass closed

For gate pass queries, contact the Logistics or Warehouse team.
"""


# ===========================================================================
# EXISTING FUNCTION — kept unchanged
# ===========================================================================

def get_knowledge(intent: str, query: str = "") -> str:
    """
    Returns the most relevant knowledge base content for a given intent.
    The LLM uses this as context to answer the user's question.
    """
    intent = intent.upper()

    knowledge_map = {
        "COMPANY_INFO":         COMPANY_PROFILE,
        "CONTACT_INFO":         CONTACT_INFO,
        "PRODUCT_INFO":         PRODUCTS_AND_BRANDS,
        "HOW_TO_ORDER":         HOW_TO_ORDER,
        "CREATE_QUOTATION":     HOW_TO_CREATE_QUOTATION,
        "PAYMENT_METHODS":      PAYMENT_METHODS,
        "POLICY_QUESTION":      PAYMENT_METHODS,
        "FAQ":                  FAQ,
        "GREETING":             ONBOARDING_GUIDE,
        "SMALL_TALK":           ONBOARDING_GUIDE,
        "RECOMMEND_ITEMS":      SALES_COACHING,
        "RECOMMEND_CUSTOMERS":  SALES_COACHING,
        "TRAINING_MODULE":      TRAINING_MODULES.get("TRAINING_MODULE", ""),
        "TRAINING_GUIDE":       TRAINING_MODULES.get("TRAINING_GUIDE", ""),
        "TRAINING_FAQ":         TRAINING_MODULES.get("TRAINING_FAQ", ""),
        "TRAINING_WEBINAR":     TRAINING_MODULES.get("TRAINING_WEBINAR", ""),
        "TRAINING_VIDEO":       TRAINING_MODULES.get("TRAINING_VIDEO", ""),
        "SYSTEM_MODULES":       SYSTEM_MODULES_GUIDE,
        "DASHBOARD_OVERVIEW":   DASHBOARD_GUIDE,
        "PURCHASE_GUIDE":       PURCHASE_GUIDE,
        "BANKING_GUIDE":        BANKING_GUIDE,
        "LOGISTICS_GUIDE":      LOGISTICS_GUIDE,
        "PRODUCTION_GUIDE":     PRODUCTION_GUIDE,
        "GATE_PASS_GUIDE":      GATE_PASS_GUIDE,
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

    if intent in ("FAQ", "TRAINING_GUIDE", "TRAINING_MODULE"):
        query_lower = query.lower()
        if any(w in query_lower for w in ["dashboard", "kpi", "sales trend", "revenue"]):
            return DASHBOARD_GUIDE
        if any(w in query_lower for w in ["gate pass", "gate", "security"]):
            return GATE_PASS_GUIDE
        if any(w in query_lower for w in ["logistics", "delivery", "dispatch", "route"]):
            return LOGISTICS_GUIDE
        if any(w in query_lower for w in ["purchase", "supplier", "vendor", "accounts payable", "a/p"]):
            return PURCHASE_GUIDE
        if any(w in query_lower for w in ["banking", "payment", "bank", "reconcil"]):
            return BANKING_GUIDE
        if any(w in query_lower for w in ["production", "manufacture", "bom", "bill of material"]):
            return PRODUCTION_GUIDE
        if any(w in query_lower for w in ["module", "system", "what can", "help me"]):
            return SYSTEM_MODULES_GUIDE

    content = knowledge_map.get(intent, FAQ)

    followups = SUGGESTED_FOLLOWUPS.get(intent, [])
    if followups:
        content += "\n\n--- YOU MIGHT ALSO WANT TO ---\n"
        content += "\n".join(f"- {f}" for f in followups)

    return content


def get_sales_rep_reference() -> str:
    """Returns the quick reference cheat sheet for sales reps."""
    return SALES_REP_QUICK_REFERENCE


def get_onboarding_guide() -> str:
    """Returns the new user onboarding guide."""
    return ONBOARDING_GUIDE


def get_glossary_term(term: str) -> str:
    """Look up a single glossary term."""
    return GLOSSARY.get(term.upper(), f"Term '{term}' not found in glossary.")


def get_module_guide(module: str) -> str:
    """Look up a specific module guide by name."""
    module_map = {
        "sales":      HOW_TO_ORDER,
        "inventory":  FAQ,
        "logistics":  LOGISTICS_GUIDE,
        "purchase":   PURCHASE_GUIDE,
        "banking":    BANKING_GUIDE,
        "production": PRODUCTION_GUIDE,
        "gate_pass":  GATE_PASS_GUIDE,
        "dashboard":  DASHBOARD_GUIDE,
        "system":     SYSTEM_MODULES_GUIDE,
    }
    return module_map.get(module.lower(), SYSTEM_MODULES_GUIDE)


# ===========================================================================
# NEW FUNCTIONS — called by action_router.py
# These were missing and causing all 7 knowledge-category test failures.
# ===========================================================================

def get_company_info() -> dict:
    """
    Returns structured company info dict.
    Called by action_router for COMPANY_INFO intent.
    """
    return {
        "name":    "Leysco Limited",
        "tagline": "Simply Reliable",
        "about":   (
            "Leysco is a software development and consultancy company specialising in "
            "enterprise-wide Resource Planning and Management Systems that support critical "
            "business processes and decision-making for organisations in Kenya.\n\n"
            "Leysco100 is Leysco's SAP Business One ERP for Demo Company Kenya — an agricultural "
            "inputs business managing seeds, fertilizers, agro-chemicals, and tools across "
            "10 integrated modules."
        ),
        "values": [
            "Safety — ensuring system and data security at all times",
            "Stability — reliable, always-on systems for business continuity",
            "Technical Support — responsive IT support when you need it",
            "Complete Solutions — end-to-end implementation and ongoing service",
        ],
        "phone":   "+254(0) 780 457 591",
        "email":   "info@leysco.com",
        "website": "https://leysco.com",
        "address": "APA Arcade, Hurlingham, Nairobi, Kenya",
    }


def get_brand_info() -> dict:
    """
    Returns structured product brand/category info dict.
    Called by action_router for PRODUCT_INFO intent.
    """
    return {
        "seeds": {
            "name":        "Seeds Division",
            "category":    "Seeds & Planting Material",
            "description": (
                "A comprehensive range of certified vegetable, maize, and field crop seeds "
                "from leading global and regional seed companies. Varieties are selected for "
                "Kenyan growing conditions."
            ),
            "key_products": [
                "Hybrid Cabbage varieties (EaSeed, Agriscope)",
                "Tomato — disease-resistant F1 hybrids",
                "Maize — MH401, KH500 and other hybrids",
                "Watermelon, Pepper, Cauliflower, Onion varieties",
            ],
        },
        "fertilizers": {
            "name":        "Fertilizers Division",
            "category":    "Crop Nutrition",
            "description": (
                "Straight and compound fertilizers for all crop stages, from soil preparation "
                "through to top-dressing and foliar application."
            ),
            "key_products": [
                "DAP (Di-Ammonium Phosphate) — basal application",
                "CAN (Calcium Ammonium Nitrate) — top-dressing",
                "NPK blends — balanced nutrition",
                "Foliar fertilizers — fast-acting leaf feeding",
            ],
        },
        "agro_chemicals": {
            "name":        "Agro-Chemicals Division",
            "category":    "Crop Protection",
            "description": (
                "Licensed pesticides, herbicides, and fungicides for integrated pest management "
                "across a wide range of crops grown in Kenya."
            ),
            "key_products": [
                "VegiMax — vegetable nutrition and growth promoter (10ml, 30ml, 125ml, 250ml)",
                "Fungicides for tomato and brassica crops",
                "Herbicides for maize and cereals",
                "Insecticides for vegetable pest control",
            ],
        },
        "tools_equipment": {
            "name":        "Tools & Equipment Division",
            "category":    "Farm Tools & Equipment",
            "description": (
                "Quality hand tools and equipment for farm operations, including sprayers, "
                "protective equipment, and measuring tools."
            ),
            "key_products": [
                "Agriscope Hand Sprayer — 1LT",
                "Jacto Pumps PJ16 — 16lt",
                "Latex Gloves",
                "Measuring cylinders and mixing equipment",
            ],
        },
    }


def get_ordering_info() -> dict:
    """
    Returns structured ordering and payment info dict.
    Called by action_router for HOW_TO_ORDER and PAYMENT_METHODS intents.
    """
    return {
        "how_to_order": HOW_TO_ORDER,
        "how_to_quote":  HOW_TO_CREATE_QUOTATION,
        "payment_terms": {
            "available_methods": [
                "M-Pesa (Paybill — contact Finance for current number)",
                "Bank Transfer (contact Finance for account details)",
                "Cash (at company offices, receipt issued)",
                "Cheque (3-5 business days clearing before goods released)",
            ],
            "credit_terms":  (
                "Credit customers: payment due within agreed period (30 or 60 days). "
                "New customers: Cash on Delivery until credit account is approved. "
                "Credit limits are set per customer and visible in Leysco100."
            ),
            "mpesa":         "M-Pesa Paybill — get current number from Finance department",
            "bank_transfer": "Bank account details available from Finance department",
        },
        "delivery": (
            "Deliveries are managed through the Logistics Hub. "
            "Ask 'outstanding deliveries' to check pending dispatches, "
            "or 'delivery history for [customer]' for past records."
        ),
    }


def get_contact_info() -> dict:
    """
    Returns structured contact info dict.
    Called by action_router for CONTACT_INFO intent.
    """
    return {
        "customer_support": {
            "phone": "+254(0) 780 457 591",
            "email": "info@leysco.com",
            "hours": "Monday – Friday, 8:00 AM – 5:00 PM EAT",
        },
        "sales_regions": [
            {"name": "Nairobi & Central",      "contact": "Contact head office"},
            {"name": "Rift Valley",             "contact": "Contact head office"},
            {"name": "Western Kenya",           "contact": "Contact head office"},
            {"name": "Coast Region",            "contact": "Contact head office"},
            {"name": "Eastern & Mt. Kenya",     "contact": "Contact head office"},
        ],
        "technical_support": (
            "For SAP / Leysco100 system issues:\n"
            "• Email: info@leysco.com\n"
            "• Phone: +254(0) 780 457 591\n"
            "• EDMS Portal: https://pgtl.xedms.com\n"
            "For urgent stock or pricing queries, use this AI assistant first — it's faster."
        ),
        "address": "APA Arcade, Hurlingham, Nairobi, Kenya",
        "website": "https://leysco.com",
    }


def get_policies() -> dict:
    """
    Returns structured policy info dict.
    Called by action_router for POLICY_QUESTION intent.
    """
    return {
        "returns": (
            "RETURNS & REFUNDS POLICY:\n"
            "• Returns accepted within 7 days with original receipt.\n"
            "• Products must be in original, unopened condition.\n"
            "• Agro-chemicals: No returns once opened (safety policy).\n"
            "• Damaged goods: Report within 24 hours of delivery with photos.\n"
            "• Contact your sales manager to initiate a return."
        ),
        "quality_guarantee": (
            "QUALITY GUARANTEE:\n"
            "• All seeds are certified and tested for germination rates.\n"
            "• Fertilizers and agro-chemicals are sourced from licensed suppliers.\n"
            "• Products failing to meet quality standards will be replaced or refunded.\n"
            "• Keep your purchase receipt — required for all quality claims."
        ),
        "credit_policy": (
            "CREDIT POLICY:\n"
            "• Credit limits are set per customer based on payment history.\n"
            "• Orders exceeding the credit limit require manager approval.\n"
            "• Overdue accounts may be placed on hold until payment is received.\n"
            "• Payment terms: 30 or 60 days depending on customer agreement."
        ),
        "delivery_policy": (
            "DELIVERY POLICY:\n"
            "• All deliveries require a signed gate pass at the warehouse.\n"
            "• Delivery times depend on location and stock availability.\n"
            "• Customer must inspect goods on delivery and sign the delivery note.\n"
            "• Discrepancies must be reported at the time of delivery."
        ),
    }


def get_faq_answer(query: str) -> str:
    """
    Returns the most relevant FAQ answer for a given query string.
    Called by action_router for FAQ intent.
    Falls back to the full FAQ if no specific match is found.
    """
    query_lower = (query or "").lower()

    # Keyword-based routing to specific answers
    if any(w in query_lower for w in ["stock", "inventory", "available"]):
        return (
            "To check stock levels, ask:\n"
            "• 'Stock level for [item name]' — shows quantities per warehouse\n"
            "• 'Stock in [warehouse name]' — shows all items in that warehouse\n"
            "• 'Low stock alerts' — shows items running low across all warehouses"
        )

    if any(w in query_lower for w in ["price", "cost", "how much"]):
        return (
            "To check prices:\n"
            "• 'Price of [item]' — standard price list\n"
            "• 'Price of [item] for [customer]' — customer-specific price (recommended)\n"
            "The system automatically finds the correct price list for each customer."
        )

    if any(w in query_lower for w in ["order", "quotation", "quote", "create"]):
        return HOW_TO_CREATE_QUOTATION

    if any(w in query_lower for w in ["payment", "pay", "mpesa", "bank", "cash"]):
        return PAYMENT_METHODS

    if any(w in query_lower for w in ["deliver", "dispatch", "logistics", "shipping"]):
        return (
            "To track deliveries:\n"
            "• 'Outstanding deliveries' — all pending deliveries\n"
            "• 'Outstanding deliveries for [customer]' — customer-specific\n"
            "• 'Delivery history for [customer]' — past 30 days\n"
            "All deliveries are managed through the Logistics Hub."
        )

    if any(w in query_lower for w in ["customer", "client", "account"]):
        return (
            "To look up customers:\n"
            "• 'Show customer [name]' — find a customer\n"
            "• 'Customer details for [name]' — full profile with credit limit\n"
            "• 'Orders for [customer]' — their order history\n"
            "• 'Invoices for [customer]' — their invoice history"
        )

    if any(w in query_lower for w in ["credit", "limit", "hold"]):
        return (
            "Credit limit information:\n"
            "• Ask 'Customer details for [name]' to see their credit limit.\n"
            "• Orders exceeding the credit limit require manager approval.\n"
            "• New customers are on Cash on Delivery until credit is approved."
        )

    if any(w in query_lower for w in ["return", "refund", "broken", "damaged"]):
        return get_policies()["returns"]

    if any(w in query_lower for w in ["warehouse", "location", "branch"]):
        return (
            "To check warehouses:\n"
            "• 'Show all warehouses' — list all active warehouses\n"
            "• 'Stock in [warehouse name]' — items in a specific warehouse\n"
            "• 'Low stock alerts' — items below threshold across all warehouses"
        )

    # Default: return the full FAQ
    return FAQ