from pathlib import Path
from typing import Dict, Optional


# Single source of truth — all valid intents in one place.
VALID_INTENTS = [
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
    "GET_CUSTOMERS",
    "GET_CUSTOMER_DETAILS",
    "GET_CUSTOMER_ORDERS",
    "GET_CUSTOMER_PRICE",
    "GET_OUTSTANDING_DELIVERIES",
    "GET_QUOTATIONS",
    "CREATE_QUOTATION",
    "GET_WAREHOUSES",
    "GET_WAREHOUSE_STOCK",
    "GET_LOW_STOCK_ALERTS",
    # Conversational / Knowledge
    "COMPANY_INFO",
    "PRODUCT_INFO",
    "HOW_TO_ORDER",
    "PAYMENT_METHODS",
    "CONTACT_INFO",
    "POLICY_QUESTION",
    "FAQ",
    "TRACK_DELIVERY",
    "GET_DELIVERY_HISTORY",
    "RECOMMEND_ITEMS",
    "RECOMMEND_CUSTOMERS",
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
    # =========================================================
    # 🧠 DECISION SUPPORT INTENTS
    # =========================================================
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "ANALYZE_CUSTOMER_BEHAVIOR",
    "FORECAST_DEMAND",
    # =========================================================
    # 🎯 SMART RECOMMENDATION INTENTS - NEW
    # =========================================================
    "GET_CROSS_SELL",               # Customers who bought X also bought Y
    "GET_UPSELL",                   # Premium/upgrade suggestions
    "GET_SEASONAL_RECOMMENDATIONS",  # Seasonal product recommendations
    "GET_TRENDING_PRODUCTS",        # Trending/popular products
    "UNKNOWN",           # Keep as fallback
]

_VALID_INTENTS_BLOCK = "\n".join(f"- {i}" for i in VALID_INTENTS)


class PromptManager:
    """
    Central manager for AI prompts.
    Optimized for fast, accurate real-time classification + response generation.
    """

    def __init__(self):
        self.base_path = Path(__file__).parent.parent / "prompts"

        # System prompt used ONLY for final natural-language replies
        self.system_prompt = self._load_prompt("system_prompt.md")

        # Short context hints used when generating replies
        self.intent_templates: Dict[str, str] = {
            "GET_ITEMS":                "User is asking to see or list products/items (possibly filtered).",
            "GET_ITEM_DETAILS":         "User wants detailed specs or information about one specific product.",
            "GET_ITEM_PRICE":           "User is asking for the general / standard price of an item (no customer specified).",
            "GET_CUSTOMER_PRICE":       "User wants the specific price an item has for a particular customer.",
            "GET_STOCK_LEVELS":         "User is asking about current stock quantity / availability of items.",
            "GET_LOW_STOCK_ALERTS":     "User wants to see items that are low in stock or near reorder point.",
            "CREATE_QUOTATION":         "User wants to create / prepare a new sales quotation with items & quantities.",
            "GET_QUOTATIONS":           "User is asking to view existing quotations (for a customer or in general).",
            "GET_CUSTOMER_ORDERS":      "User wants to see sales orders / purchase history of a customer.",
            "GET_WAREHOUSES":           "User is asking for list of warehouses / branches.",
            "GET_WAREHOUSE_STOCK":      "User wants stock information in a specific warehouse.",
            "HOW_TO_ORDER":             "User is asking about the ordering process, how to place an order, or steps to buy.",
            "PAYMENT_METHODS":          "User is asking about accepted payment methods, payment options, how to pay, M-Pesa, bank transfer, etc.",
            "GREETING":                 "User is saying hello or starting conversation.",
            "THANKS":                   "User is thanking or closing politely.",
            "SMALL_TALK":               "Casual / chit-chat message.",
            # TRAINING INTENT TEMPLATES
            "TRAINING_MODULE":          "User wants a step-by-step tutorial or guide on how to use a specific feature (ordering, stock, quotations, etc.).",
            "TRAINING_VIDEO":           "User is asking for video tutorials or visual demonstrations of how to use the system.",
            "TRAINING_GUIDE":           "User wants PDF documentation, manuals, or written guides about using the system.",
            "TRAINING_FAQ":             "User is asking frequently asked questions about using the system or specific features.",
            "TRAINING_GLOSSARY":        "User wants definitions of business terms, acronyms, or jargon (SKU, MOQ, UOM, etc.).",
            "TRAINING_WEBINAR":         "User is asking about live training sessions, webinars, or upcoming training events.",
            "TRAINING_ONBOARDING":      "New user asking for help getting started, orientation, or beginner guide.",
            # =========================================================
            # 🧠 DECISION SUPPORT INTENT TEMPLATES
            # =========================================================
            "ANALYZE_INVENTORY_HEALTH": "User wants a comprehensive inventory health analysis including critical stock, overstock, slow movers, and reorder recommendations.",
            "GET_REORDER_DECISIONS":    "User wants recommendations on what items to reorder, with optimal quantities and urgency levels.",
            "ANALYZE_PRICING_OPPORTUNITIES": "User wants to identify pricing opportunities like price drops, price hikes, and best value items.",
            "ANALYZE_CUSTOMER_BEHAVIOR": "User wants deep insights into customer purchasing patterns, preferences, and risk factors.",
            "FORECAST_DEMAND":          "User wants demand forecasts for specific items based on historical sales data and trends.",
            # =========================================================
            # 🎯 SMART RECOMMENDATION INTENT TEMPLATES - NEW
            # =========================================================
            "GET_CROSS_SELL":           "User wants to know what other items customers frequently buy together with a specific product (cross-sell recommendations).",
            "GET_UPSELL":               "User wants to know about premium, better, or upgraded versions of a product (upsell recommendations).",
            "GET_SEASONAL_RECOMMENDATIONS": "User wants recommendations for products that are in season or best for the current time of year.",
            "GET_TRENDING_PRODUCTS":    "User wants to know what products are currently popular, trending, or selling well.",
            "UNKNOWN":                  "Message is unclear or does not match any business intent.",
        }

    def _load_prompt(self, filename: str) -> str:
        path = self.base_path / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {filename}")
        return path.read_text(encoding="utf-8").strip()

    # ──────────────────────────────────────────────────────────────
    #   INTENT CLASSIFICATION PROMPT — improved & battle-tested
    # ──────────────────────────────────────────────────────────────
    def get_intent_prompt(self, user_message: str) -> str:
        return f"""You are a precise intent classifier for an agricultural inputs sales assistant (Leysco).

Classify the user message into **exactly one** intent from this list:

{_VALID_INTENTS_BLOCK}

Rules — follow strictly:
- Return ONLY valid JSON: {{"intent": "EXACT_INTENT_NAME_HERE"}}
- No explanation, no markdown, no extra text whatsoever.
- Intent name must be copied exactly as shown above (case-sensitive).
- Choose the MOST SPECIFIC intent that matches.
- When in doubt → choose "SMALL_TALK" or "UNKNOWN" (prefer SMALL_TALK for greetings/vague chat).

Key decision rules:

**🎯 Smart Recommendations (NEW):**
- "customers who bought", "also bought", "frequently bought", "people also buy", "commonly bought with", "bundle with", "what else goes with" → GET_CROSS_SELL
- "better version", "upgrade", "premium alternative", "higher quality", "what's better than", "deluxe version", "professional grade" → GET_UPSELL
- "seasonal", "what to plant in", "best for this season", "what grows in", "planting guide for", "seasonal picks" → GET_SEASONAL_RECOMMENDATIONS
- "trending", "popular now", "hot items", "best sellers", "most popular", "top selling", "what's trending", "in demand" → GET_TRENDING_PRODUCTS

**🧠 Decision Support:**
- "inventory health", "stock health", "inventory analysis", "health check" → ANALYZE_INVENTORY_HEALTH
- "reorder", "what to order", "order decisions", "reorder recommendations" → GET_REORDER_DECISIONS
- "pricing opportunities", "price opportunities", "best prices", "price analysis", "price trends" → ANALYZE_PRICING_OPPORTUNITIES
- "customer behavior", "customer analysis", "customer insights", "analyze customer" → ANALYZE_CUSTOMER_BEHAVIOR
- "forecast", "demand forecast", "sales forecast", "predict demand", "future demand" → FORECAST_DEMAND

**🎓 Training & Onboarding:**
- "how to", "learn", "tutorial", "guide", "teach me", "walk me through" → TRAINING_MODULE
- "video", "watch tutorial", "show me video" → TRAINING_VIDEO
- "pdf", "document", "manual", "handbook" → TRAINING_GUIDE
- "faq", "frequently asked", "common questions" → TRAINING_FAQ
- "what does X mean", "define", "glossary", "meaning of", "term" → TRAINING_GLOSSARY
- "webinar", "live training", "workshop", "training session" → TRAINING_WEBINAR
- "new user", "getting started", "beginner", "onboarding", "first time" → TRAINING_ONBOARDING

**📦 Business Operations:**
- "how to order", "place an order", "ordering process", "how do I buy" → HOW_TO_ORDER
- "payment method", "payment methods", "how to pay", "accepted payments", "do you accept", "pay with", "mpesa", "bank transfer" → PAYMENT_METHODS
- Any price question + customer name ("for X", "Lumarx pays", "SMD price") → GET_CUSTOMER_PRICE
- Price question without customer → GET_ITEM_PRICE
- "show me items", "list products", "cabbage items", "vegimax" (no price/stock keyword) → GET_ITEMS
- "stock", "in stock", "how many", "available", "stock level" → GET_STOCK_LEVELS or GET_ITEMS_ADVANCED
- "low stock", "running low", "stock alert" → GET_LOW_STOCK_ALERTS
- "make quote", "create quotation", "quote for … with 10 cabbage" → CREATE_QUOTATION
- "show quotations", "quotations for Lumarx" → GET_QUOTATIONS
- "orders for …", "what did … buy" → GET_CUSTOMER_ORDERS

**💬 Conversational:**
- "hello", "hi", "good morning" → GREETING
- "thank you", "thanks" → THANKS
- "okay", "sure", "got it", "bye" → SMALL_TALK
- Random chat, jokes, weather → SMALL_TALK

Examples — learn from these:

**Business Examples:**
Message: "show me 5 items"                            → {{"intent": "GET_ITEMS"}}
Message: "Show me cabbage items"                      → {{"intent": "GET_ITEMS"}}
Message: "price of vegimax"                           → {{"intent": "GET_ITEM_PRICE"}}
Message: "vegimax price for Lumarx"                   → {{"intent": "GET_CUSTOMER_PRICE"}}
Message: "show me stock levels"                       → {{"intent": "GET_STOCK_LEVELS"}}
Message: "low stock items"                            → {{"intent": "GET_LOW_STOCK_ALERTS"}}
Message: "create a quotation for Lumarx with 5 vegimax" → {{"intent": "CREATE_QUOTATION"}}
Message: "hello there"                                → {{"intent": "GREETING"}}
Message: "tell me about Leysco"                       → {{"intent": "COMPANY_INFO"}}
Message: "how do I place an order?"                   → {{"intent": "HOW_TO_ORDER"}}
Message: "what are the payment methods?"              → {{"intent": "PAYMENT_METHODS"}}
Message: "do you accept mpesa?"                        → {{"intent": "PAYMENT_METHODS"}}

**Training Examples:**
Message: "how do I check stock?"                       → {{"intent": "TRAINING_MODULE"}}
Message: "show me ordering videos"                     → {{"intent": "TRAINING_VIDEO"}}
Message: "what does SKU mean?"                         → {{"intent": "TRAINING_GLOSSARY"}}
Message: "stock management FAQ"                        → {{"intent": "TRAINING_FAQ"}}
Message: "I need the user manual"                      → {{"intent": "TRAINING_GUIDE"}}
Message: "are there any upcoming webinars?"            → {{"intent": "TRAINING_WEBINAR"}}
Message: "I'm new here, help me get started"           → {{"intent": "TRAINING_ONBOARDING"}}

**🧠 Decision Support Examples:**
Message: "show me inventory health report"             → {{"intent": "ANALYZE_INVENTORY_HEALTH"}}
Message: "what should I reorder today?"                → {{"intent": "GET_REORDER_DECISIONS"}}
Message: "any pricing opportunities?"                  → {{"intent": "ANALYZE_PRICING_OPPORTUNITIES"}}
Message: "analyze customer ABC Company"                → {{"intent": "ANALYZE_CUSTOMER_BEHAVIOR"}}
Message: "forecast demand for VegiMax"                 → {{"intent": "FORECAST_DEMAND"}}

**🎯 Smart Recommendation Examples (NEW):**
Message: "customers who bought vegimax also bought what?"  → {{"intent": "GET_CROSS_SELL"}}
Message: "what else do people buy with cabbage seeds?"     → {{"intent": "GET_CROSS_SELL"}}
Message: "frequently bought with tomato fertilizer"        → {{"intent": "GET_CROSS_SELL"}}
Message: "is there a better version of vegimax?"           → {{"intent": "GET_UPSELL"}}
Message: "upgrade options for basic fertilizer"            → {{"intent": "GET_UPSELL"}}
Message: "what should I plant in March?"                   → {{"intent": "GET_SEASONAL_RECOMMENDATIONS"}}
Message: "seasonal recommendations for vegetables"         → {{"intent": "GET_SEASONAL_RECOMMENDATIONS"}}
Message: "what's trending right now?"                      → {{"intent": "GET_TRENDING_PRODUCTS"}}
Message: "most popular products this month"                → {{"intent": "GET_TRENDING_PRODUCTS"}}

Message now: "{user_message}"

Respond with JSON only:
{{"intent": "GET_ITEMS"}}
"""

    # ──────────────────────────────────────────────────────────────
    #   ENTITY EXTRACTION — made more useful for downstream logic
    # ──────────────────────────────────────────────────────────────
    def get_entity_prompt(self, user_message: str) -> str:
        return f"""You are an entity extractor for a Kenyan agricultural inputs sales assistant.

Extract the following from the message — return ONLY JSON.

Fields:
- item_name: main product name or crop (string or null)
- item_code: product code if mentioned (e.g. KAVGX002) (string or null)
- customer_name: customer / business name (string or null)
- quantity: requested quantity (integer or null)
- unit: unit of measure if specified (string or null, e.g. "bags", "ml")
- warehouse: warehouse / location name (string or null)
- price_related: true if message is asking about price/cost (boolean)
- stock_related: true if asking about stock/availability (boolean)
- training_topic: specific topic user wants to learn about (string or null, e.g. "ordering", "stock", "quotations")
- training_type: type of training requested (string or null, e.g. "video", "guide", "faq", "glossary")
- analysis_type: type of analysis requested (string or null, e.g. "inventory", "reorder", "pricing", "customer", "forecast")
- forecast_period: days for forecast if specified (integer or null)
- recommendation_type: type of recommendation requested (string or null, e.g. "cross_sell", "upsell", "seasonal", "trending")

Rules:
- Be conservative — only extract what is clearly present.
- Use null when unsure or absent.
- Normalize names slightly (e.g. "lumarx" → "Lumarx")
- For cross-sell queries, extract the main product (e.g., from "customers who bought vegimax" → item_name = "vegimax")
- For seasonal queries, extract month if mentioned

Message: "{user_message}"

Return ONLY:
{{
  "item_name": null,
  "item_code": null,
  "customer_name": null,
  "quantity": null,
  "unit": null,
  "warehouse": null,
  "price_related": false,
  "stock_related": false,
  "training_topic": null,
  "training_type": null,
  "analysis_type": null,
  "forecast_period": null,
  "recommendation_type": null,
  "month": null
}}
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