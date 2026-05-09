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
    # DECISION SUPPORT INTENTS
    # =========================================================
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "ANALYZE_CUSTOMER_BEHAVIOR",
    "FORECAST_DEMAND",
    # =========================================================
    # SMART RECOMMENDATION INTENTS
    # =========================================================
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
    "UNKNOWN",
]

_VALID_INTENTS_BLOCK = "\n".join(f"- {i}" for i in VALID_INTENTS)


class PromptManager:
    """
    Central manager for AI prompts.
    Optimized for fast, accurate real-time classification + response generation.
    
    RULES:
    - Do NOT repeat yourself
    - Do NOT add emojis
    - Do NOT add symbols
    - Do NOT return long paragraphs
    - Return short messages
    - Use structured JSON when needed
    """

    def __init__(self):
        self.base_path = Path(__file__).parent.parent / "prompts"

        # System prompt used ONLY for final natural-language replies
        self.system_prompt = self._load_prompt_with_rules("system_prompt.md")

        # Short context hints used when generating replies
        self.intent_templates: Dict[str, str] = {
            "GET_ITEMS":                "User wants to see list of products.",
            "GET_ITEM_DETAILS":         "User wants detailed specs of a product.",
            "GET_ITEM_PRICE":           "User wants standard price of an item.",
            "GET_CUSTOMER_PRICE":       "User wants price for a specific customer.",
            "GET_STOCK_LEVELS":         "User wants current stock quantity.",
            "GET_LOW_STOCK_ALERTS":     "User wants items low in stock.",
            "CREATE_QUOTATION":         "User wants to create a sales quotation.",
            "GET_QUOTATIONS":           "User wants to view existing quotations.",
            "GET_CUSTOMER_ORDERS":      "User wants purchase history of customer.",
            "GET_WAREHOUSES":           "User wants list of warehouses.",
            "GET_WAREHOUSE_STOCK":      "User wants stock in specific warehouse.",
            "HOW_TO_ORDER":             "User asks about ordering process.",
            "PAYMENT_METHODS":          "User asks about payment options.",
            "GREETING":                 "User is saying hello.",
            "THANKS":                   "User is thanking.",
            "SMALL_TALK":               "Casual conversation.",
            "TRAINING_MODULE":          "User wants step-by-step tutorial.",
            "TRAINING_VIDEO":           "User wants video tutorial.",
            "TRAINING_GUIDE":           "User wants documentation or manual.",
            "TRAINING_FAQ":             "User asks frequently asked questions.",
            "TRAINING_GLOSSARY":        "User wants definitions of terms.",
            "TRAINING_WEBINAR":         "User asks about live training.",
            "TRAINING_ONBOARDING":      "New user needs help getting started.",
            "ANALYZE_INVENTORY_HEALTH": "User wants inventory health analysis.",
            "GET_REORDER_DECISIONS":    "User wants reorder recommendations.",
            "ANALYZE_PRICING_OPPORTUNITIES": "User wants pricing insights.",
            "ANALYZE_CUSTOMER_BEHAVIOR": "User wants customer purchase patterns.",
            "FORECAST_DEMAND":          "User wants demand forecast.",
            "GET_CROSS_SELL":           "User wants cross-sell recommendations.",
            "GET_UPSELL":               "User wants upsell recommendations.",
            "GET_SEASONAL_RECOMMENDATIONS": "User wants seasonal product picks.",
            "GET_TRENDING_PRODUCTS":    "User wants trending/popular products.",
            "UNKNOWN":                  "Message unclear or no matching intent.",
        }

    def _load_prompt_with_rules(self, filename: str) -> str:
        """Load prompt and append response format rules."""
        path = self.base_path / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {filename}")
        
        content = path.read_text(encoding="utf-8").strip()
        
        # Add response format rules
        rules = """
RESPONSE FORMAT RULES:
- DO NOT repeat yourself
- DO NOT add emojis or symbols
- DO NOT return long paragraphs
- Keep messages short and concise
- Use structured JSON when multiple data points exist
- Be direct and helpful
"""
        return content + "\n" + rules

    # ──────────────────────────────────────────────────────────────
    #   INTENT CLASSIFICATION PROMPT
    # ──────────────────────────────────────────────────────────────
    def get_intent_prompt(self, user_message: str) -> str:
        return f"""You are a precise intent classifier for an agricultural inputs sales assistant.

Classify the user message into exactly one intent from this list:

{_VALID_INTENTS_BLOCK}

Rules:
- Return ONLY valid JSON: {{"intent": "EXACT_INTENT_NAME_HERE"}}
- No explanation, no markdown, no extra text.
- Intent name must be copied exactly as shown.
- Choose the most specific intent.
- When uncertain, choose "SMALL_TALK" or "UNKNOWN".

Key decision rules:

Smart Recommendations:
- "customers who bought", "also bought", "frequently bought", "what else goes with" -> GET_CROSS_SELL
- "better version", "upgrade", "premium alternative", "what's better" -> GET_UPSELL
- "seasonal", "what to plant in", "best for this season" -> GET_SEASONAL_RECOMMENDATIONS
- "trending", "popular now", "hot items", "best sellers", "top selling" -> GET_TRENDING_PRODUCTS

Decision Support:
- "inventory health", "stock health", "health check" -> ANALYZE_INVENTORY_HEALTH
- "reorder", "what to order", "order decisions" -> GET_REORDER_DECISIONS
- "pricing opportunities", "price opportunities", "best prices" -> ANALYZE_PRICING_OPPORTUNITIES
- "customer behavior", "customer analysis", "analyze customer" -> ANALYZE_CUSTOMER_BEHAVIOR
- "forecast", "demand forecast", "sales forecast", "predict demand" -> FORECAST_DEMAND

Training:
- "how to", "learn", "tutorial", "teach me" -> TRAINING_MODULE
- "video", "watch tutorial" -> TRAINING_VIDEO
- "pdf", "document", "manual" -> TRAINING_GUIDE
- "faq", "frequently asked" -> TRAINING_FAQ
- "what does X mean", "define", "glossary" -> TRAINING_GLOSSARY
- "webinar", "live training" -> TRAINING_WEBINAR
- "new user", "getting started", "beginner" -> TRAINING_ONBOARDING

Business:
- "how to order", "place an order" -> HOW_TO_ORDER
- "payment method", "how to pay", "mpesa" -> PAYMENT_METHODS
- Price + customer name -> GET_CUSTOMER_PRICE
- Price without customer -> GET_ITEM_PRICE
- "show me items", "list products" -> GET_ITEMS
- "stock", "how many", "available" -> GET_STOCK_LEVELS
- "low stock", "running low" -> GET_LOW_STOCK_ALERTS
- "create quotation", "make quote" -> CREATE_QUOTATION
- "show quotations" -> GET_QUOTATIONS
- "orders for" -> GET_CUSTOMER_ORDERS

Conversational:
- "hello", "hi" -> GREETING
- "thank you", "thanks" -> THANKS
- "okay", "bye", random chat -> SMALL_TALK

Examples:
Message: "show me 5 items" -> {"intent": "GET_ITEMS"}
Message: "price of vegimax" -> {"intent": "GET_ITEM_PRICE"}
Message: "vegimax price for Lumarx" -> {"intent": "GET_CUSTOMER_PRICE"}
Message: "low stock items" -> {"intent": "GET_LOW_STOCK_ALERTS"}
Message: "create a quotation for Lumarx with 5 vegimax" -> {"intent": "CREATE_QUOTATION"}
Message: "hello" -> {"intent": "GREETING"}
Message: "how do I check stock?" -> {"intent": "TRAINING_MODULE"}
Message: "what does SKU mean?" -> {"intent": "TRAINING_GLOSSARY"}
Message: "forecast demand for VegiMax" -> {"intent": "FORECAST_DEMAND"}
Message: "customers who bought vegimax also bought what?" -> {"intent": "GET_CROSS_SELL"}

Message now: "{user_message}"

Respond with JSON only:
{{"intent": "GET_ITEMS"}}
"""

    # ──────────────────────────────────────────────────────────────
    #   ENTITY EXTRACTION PROMPT
    # ──────────────────────────────────────────────────────────────
    def get_entity_prompt(self, user_message: str) -> str:
        return f"""You are an entity extractor for agricultural sales.

Extract fields from message. Return ONLY JSON.

Fields:
- item_name: main product name (string or null)
- item_code: product code if mentioned (string or null)
- customer_name: customer name (string or null)
- quantity: numeric quantity (integer or null)
- unit: unit of measure (string or null)
- warehouse: warehouse name (string or null)
- price_related: true if asking about price (boolean)
- stock_related: true if asking about stock (boolean)
- training_topic: what user wants to learn (string or null)
- training_type: video, guide, faq, glossary (string or null)
- analysis_type: inventory, reorder, pricing, customer, forecast (string or null)
- forecast_period: days for forecast (integer or null)
- recommendation_type: cross_sell, upsell, seasonal, trending (string or null)
- month: month mentioned (string or null)

Rules:
- Extract only what is clearly present.
- Use null when unsure.
- Normalize names slightly (e.g., "lumarx" -> "Lumarx").

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


# Singleton instance
prompt_manager = PromptManager()