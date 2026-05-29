from pathlib import Path
from typing import Dict, Optional


# Single source of truth — all valid intents in one place.
VALID_INTENTS = [
    # Items & Stock
    "GET_ITEMS",
    "GET_SELLABLE_ITEMS",
    "GET_PURCHASABLE_ITEMS",
    "GET_INVENTORY_ITEMS",
    "GET_ITEM_DETAILS",
    "GET_ITEM_PRICE",
    "GET_ITEM_BASE_PRICE",
    "GET_ITEM_DISCOUNTS",
    "GET_ITEMS_ADVANCED",
    "GET_STOCK_LEVELS",
    "CHECK_FINAL_PRICE",
    
    # Customers
    "GET_CUSTOMERS",
    "GET_CUSTOMER_DETAILS",
    "GET_CUSTOMER_ORDERS",
    "GET_CUSTOMER_PRICE",
    "GET_CUSTOMER_HEALTH",           # NEW
    "GET_CUSTOMER_INVOICES",         # NEW
    "GET_OUTSTANDING_INVOICES",      # NEW
    "GET_CUSTOMER_BALANCE",          # NEW
    "FIND_CUSTOMERS_BY_ITEM",        # NEW
    
    # Deliveries
    "GET_OUTSTANDING_DELIVERIES",
    "TRACK_DELIVERY",
    "GET_DELIVERY_HISTORY",
    
    # Quotations
    "GET_QUOTATIONS",
    "CREATE_QUOTATION",
    "FOLLOW_UP_QUOTATIONS",          # NEW
    "CONVERT_QUOTATION_TO_ORDER",    # NEW
    
    # Warehouses
    "GET_WAREHOUSES",
    "GET_WAREHOUSE_STOCK",
    "GET_LOW_STOCK_ALERTS",
    
    # NEW - Invoice Management
    "GET_AR_INVOICES",
    "GET_AP_INVOICES",
    "GET_OVERDUE_INVOICES",
    "GET_CUSTOMER_BALANCE",
    "GET_PAYMENT_STATUS",
    "SEND_PAYMENT_REMINDER",
    "GET_AGING_REPORT",
    "POST_INVOICE",                  # NEW - Delivery to Invoice
    
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
    
    # NEW - Document Lifecycle
    "CANCEL_DOCUMENT",
    "REVERSE_DOCUMENT",
    
    # Conversational / Knowledge
    "COMPANY_INFO",
    "PRODUCT_INFO",
    "HOW_TO_ORDER",
    "PAYMENT_METHODS",
    "CONTACT_INFO",
    "POLICY_QUESTION",
    "FAQ",
    
    # Recommendations
    "RECOMMEND_ITEMS",
    "RECOMMEND_CUSTOMERS",
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
    
    # Analytics
    "GET_TOP_SELLING_ITEMS",
    "GET_SLOW_MOVING_ITEMS",
    "GET_SALES_ANALYTICS",
    
    # Decision Support
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "ANALYZE_CUSTOMER_BEHAVIOR",
    "FORECAST_DEMAND",
    
    # Conversational
    "GREETING",
    "THANKS",
    "SMALL_TALK",
    
    # TRAINING INTENTS
    "TRAINING_MODULE",
    "TRAINING_VIDEO",
    "TRAINING_GUIDE",
    "TRAINING_FAQ",
    "TRAINING_GLOSSARY",
    "TRAINING_WEBINAR",
    "TRAINING_ONBOARDING",
    
    # Fallback
    "UNKNOWN",
]

_VALID_INTENTS_SET = set(VALID_INTENTS)
_VALID_INTENTS_BLOCK = "\n".join(f"- {i}" for i in VALID_INTENTS)


class PromptManager:
    """
    Central manager for AI prompts.
    Optimized for fast, accurate real-time classification + response generation.
    """

    def __init__(self):
        self.base_path = Path(__file__).parent.parent / "prompts"
        self.system_prompt = self._load_prompt_with_rules("system_prompt.md")
        
        self.intent_templates: Dict[str, str] = {
            # Items & Stock
            "GET_ITEMS": "User wants to see list of products.",
            "GET_SELLABLE_ITEMS": "User wants list of sellable products only.",
            "GET_PURCHASABLE_ITEMS": "User wants list of purchasable items.",
            "GET_INVENTORY_ITEMS": "User wants inventory items with stock info.",
            "GET_ITEM_DETAILS": "User wants detailed specs of a product.",
            "GET_ITEM_PRICE": "User wants standard price of an item.",
            "GET_ITEM_BASE_PRICE": "User wants base price before discounts.",
            "GET_ITEM_DISCOUNTS": "User wants available discounts for an item.",
            "GET_ITEMS_ADVANCED": "User wants advanced item search with filters.",
            "GET_STOCK_LEVELS": "User wants current stock quantity.",
            "CHECK_FINAL_PRICE": "User wants final price after all calculations.",
            
            # Customers
            "GET_CUSTOMERS": "User wants list of customers.",
            "GET_CUSTOMER_DETAILS": "User wants detailed customer information.",
            "GET_CUSTOMER_ORDERS": "User wants purchase history of customer.",
            "GET_CUSTOMER_PRICE": "User wants customer-specific pricing.",
            "GET_CUSTOMER_HEALTH": "User wants customer health score and churn risk analysis.",
            "GET_CUSTOMER_INVOICES": "User wants customer invoice history.",
            "GET_OUTSTANDING_INVOICES": "User wants unpaid/overdue invoices.",
            "GET_CUSTOMER_BALANCE": "User wants customer's current outstanding balance.",
            "FIND_CUSTOMERS_BY_ITEM": "User wants customers who bought specific item.",
            
            # Deliveries
            "GET_OUTSTANDING_DELIVERIES": "User wants pending deliveries.",
            "TRACK_DELIVERY": "User wants to track specific delivery.",
            "GET_DELIVERY_HISTORY": "User wants delivery history for customer.",
            
            # Quotations
            "GET_QUOTATIONS": "User wants to view existing quotations.",
            "CREATE_QUOTATION": "User wants to create a sales quotation.",
            "FOLLOW_UP_QUOTATIONS": "User wants stale quote follow-up report.",
            "CONVERT_QUOTATION_TO_ORDER": "User wants to convert quotation to sales order.",
            
            # Warehouses
            "GET_WAREHOUSES": "User wants list of warehouses.",
            "GET_WAREHOUSE_STOCK": "User wants stock in specific warehouse.",
            "GET_LOW_STOCK_ALERTS": "User wants items low in stock.",
            
            # NEW - Invoice Management
            "GET_AR_INVOICES": "User wants accounts receivable invoices.",
            "GET_AP_INVOICES": "User wants accounts payable invoices.",
            "GET_OVERDUE_INVOICES": "User wants invoices past due date.",
            "GET_PAYMENT_STATUS": "User wants payment status of invoices.",
            "SEND_PAYMENT_REMINDER": "User wants to send payment reminder to customer.",
            "GET_AGING_REPORT": "User wants invoice aging report.",
            "POST_INVOICE": "User wants to post invoice from delivery.",
            
            # NEW - Purchase Cycle
            "GET_PURCHASE_ORDERS": "User wants list of purchase orders.",
            "CREATE_PURCHASE_ORDER": "User wants to create purchase order.",
            "GET_PURCHASE_REQUESTS": "User wants purchase requests waiting approval.",
            "GET_GOODS_RECEIPT_PO": "User wants goods receipt for purchase order.",
            "APPROVE_PURCHASE_ORDER": "User wants to approve purchase order.",
            "GET_AP_INVOICES_PURCHASE": "User wants AP invoices from purchase.",
            
            # NEW - Inventory Movements
            "CREATE_GOODS_ISSUE": "User wants to create goods issue (stock out).",
            "CREATE_GOODS_RECEIPT": "User wants to create goods receipt (stock in).",
            "CREATE_STOCK_TRANSFER": "User wants to transfer stock between warehouses.",
            "GET_INVENTORY_VALUATION": "User wants inventory valuation report.",
            "GET_REORDER_REPORT": "User wants report of items needing reorder.",
            "ALLOCATE_STOCK": "User wants to allocate stock for order.",
            
            # NEW - Business Rules
            "CHECK_CREDIT_LIMIT": "User wants to check customer credit limit.",
            "CHECK_STOCK_AVAILABILITY": "User wants to check if items are available.",
            "GET_APPROVAL_STATUS": "User wants approval status of document.",
            
            # NEW - Document Lifecycle
            "CANCEL_DOCUMENT": "User wants to cancel a document.",
            "REVERSE_DOCUMENT": "User wants to reverse a document.",
            
            # Conversational / Knowledge
            "COMPANY_INFO": "User asks about Leysco company information.",
            "PRODUCT_INFO": "User asks about product information.",
            "HOW_TO_ORDER": "User asks about ordering process.",
            "PAYMENT_METHODS": "User asks about payment options.",
            "CONTACT_INFO": "User asks for contact information.",
            "POLICY_QUESTION": "User asks about company policies.",
            "FAQ": "User asks general frequently asked questions.",
            
            # Recommendations
            "RECOMMEND_ITEMS": "User wants product recommendations.",
            "RECOMMEND_CUSTOMERS": "User wants customer recommendations.",
            "GET_CROSS_SELL": "User wants cross-sell recommendations.",
            "GET_UPSELL": "User wants upsell recommendations.",
            "GET_SEASONAL_RECOMMENDATIONS": "User wants seasonal product recommendations.",
            "GET_TRENDING_PRODUCTS": "User wants trending/popular products.",
            
            # Analytics
            "GET_TOP_SELLING_ITEMS": "User wants top selling items report.",
            "GET_SLOW_MOVING_ITEMS": "User wants slow moving items report.",
            "GET_SALES_ANALYTICS": "User wants sales analytics summary.",
            
            # Decision Support
            "ANALYZE_INVENTORY_HEALTH": "User wants inventory health analysis.",
            "GET_REORDER_DECISIONS": "User wants reorder recommendations.",
            "ANALYZE_PRICING_OPPORTUNITIES": "User wants pricing insights.",
            "ANALYZE_CUSTOMER_BEHAVIOR": "User wants customer purchase patterns.",
            "FORECAST_DEMAND": "User wants demand forecast.",
            
            # Conversational
            "GREETING": "User is saying hello.",
            "THANKS": "User is thanking.",
            "SMALL_TALK": "Casual conversation.",
            
            # Training
            "TRAINING_MODULE": "User wants step-by-step tutorial.",
            "TRAINING_VIDEO": "User wants video tutorial.",
            "TRAINING_GUIDE": "User wants documentation or manual.",
            "TRAINING_FAQ": "User asks frequently asked questions.",
            "TRAINING_GLOSSARY": "User wants definitions of terms.",
            "TRAINING_WEBINAR": "User asks about live training.",
            "TRAINING_ONBOARDING": "New user needs help getting started.",
            
            # Fallback
            "UNKNOWN": "Message unclear or no matching intent.",
        }

    def _load_prompt_with_rules(self, filename: str) -> str:
        """Load prompt and append response format rules."""
        path = self.base_path / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {filename}")
        
        content = path.read_text(encoding="utf-8").strip()
        
        rules = """
RESPONSE FORMAT RULES:
- DO NOT repeat yourself
- DO NOT add emojis or symbols
- DO NOT return long paragraphs
- Keep messages short and concise
- Use structured JSON when multiple data points exist
- Be direct and helpful
- Return ONLY the JSON object, no other text
"""
        return content + "\n" + rules

    # ──────────────────────────────────────────────────────────────
    #   INTENT CLASSIFICATION PROMPT
    # ──────────────────────────────────────────────────────────────
    def get_intent_prompt(self, user_message: str) -> str:
        return f"""You are a precise intent classifier for an agricultural inputs sales assistant.

Classify the user message into exactly one intent from this list:

{_VALID_INTENTS_BLOCK}

CRITICAL RULES:
- Return ONLY valid JSON: {{"intent": "EXACT_INTENT_NAME_HERE"}}
- No spaces before or after the intent name
- No explanation, no markdown, no extra text
- Intent name must be copied exactly as shown
- Choose the most specific intent
- When uncertain, choose "UNKNOWN"

EXAMPLES:
Message: "browse items" -> {{"intent": "GET_ITEMS"}}
Message: "show me products" -> {{"intent": "GET_ITEMS"}}
Message: "list all stock" -> {{"intent": "GET_STOCK_LEVELS"}}
Message: "show me overdue invoices" -> {{"intent": "GET_OVERDUE_INVOICES"}}
Message: "customer balance for Mahakali" -> {{"intent": "GET_CUSTOMER_BALANCE"}}
Message: "create purchase order" -> {{"intent": "CREATE_PURCHASE_ORDER"}}
Message: "transfer stock from NRB01 to NAK01" -> {{"intent": "CREATE_STOCK_TRANSFER"}}
Message: "convert quotation 1042 to order" -> {{"intent": "CONVERT_QUOTATION_TO_ORDER"}}
Message: "what needs reordering" -> {{"intent": "GET_REORDER_REPORT"}}
Message: "hello" -> {{"intent": "GREETING"}}
Message: "mambo" -> {{"intent": "GREETING"}}
Message: "habari" -> {{"intent": "GREETING"}}

Message now: "{user_message}"

Respond with EXACTLY this format, nothing else:
{{"intent": "INTENT_NAME"}}
"""

    # ──────────────────────────────────────────────────────────────
    #   ENTITY EXTRACTION PROMPT
    # ──────────────────────────────────────────────────────────────
    def get_entity_prompt(self, user_message: str) -> str:
        return f"""You are an entity extractor for agricultural sales.

Extract fields from message. Return ONLY JSON with no extra text.

Fields:
- item_name: main product name (string or null)
- item_code: product code if mentioned (string or null)
- customer_name: customer name (string or null)
- vendor_name: vendor/supplier name for purchase (string or null)
- quantity: numeric quantity (integer or null)
- unit: unit of measure (string or null)
- warehouse: warehouse name (string or null)
- from_warehouse: source warehouse for transfer (string or null)
- to_warehouse: destination warehouse for transfer (string or null)
- doc_num: document number for quotation/order/invoice (string or null)
- price_related: true if asking about price (boolean)
- stock_related: true if asking about stock (boolean)
- invoice_related: true if asking about invoices (boolean)

CRITICAL RULES:
- Extract only what is clearly present
- Use null when unsure
- Return ONLY the JSON object
- No spaces before/after values

Message: "{user_message}"

Respond with EXACTLY:
{{"item_name": null, "item_code": null, "customer_name": null, "vendor_name": null, "quantity": null, "unit": null, "warehouse": null, "from_warehouse": null, "to_warehouse": null, "doc_num": null, "price_related": false, "stock_related": false, "invoice_related": false}}
"""

    # ──────────────────────────────────────────────────────────────
    #   FINAL RESPONSE GENERATION PROMPT
    # ──────────────────────────────────────────────────────────────
    def get_full_prompt(
        self,
        intent: str,
        user_message: str,
        extra_context: Optional[Dict] = None,
    ) -> str:
        hint = self.intent_templates.get(intent, "Handle as unknown or general query.")

        prompt = f"""User message:
{user_message}

Detected intent: {intent}
Context hint: {hint}"""

        if extra_context and isinstance(extra_context, dict):
            ctx_lines = [f"{k}: {v}" for k, v in extra_context.items() if v]
            if ctx_lines:
                prompt += "\n\nBusiness data / previous results:\n" + "\n".join(ctx_lines)

        return self.system_prompt + "\n\n" + prompt


# Singleton instance
prompt_manager = PromptManager()