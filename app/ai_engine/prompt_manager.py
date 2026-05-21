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
    # Decision Support
    "ANALYZE_INVENTORY_HEALTH",
    "GET_REORDER_DECISIONS",
    "ANALYZE_PRICING_OPPORTUNITIES",
    "ANALYZE_CUSTOMER_BEHAVIOR",
    "FORECAST_DEMAND",
    # Smart Recommendations
    "GET_CROSS_SELL",
    "GET_UPSELL",
    "GET_SEASONAL_RECOMMENDATIONS",
    "GET_TRENDING_PRODUCTS",
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
            "GET_ITEMS": "User wants to see list of products.",
            "GET_ITEM_DETAILS": "User wants detailed specs of a product.",
            "GET_ITEM_PRICE": "User wants standard price of an item.",
            "GET_CUSTOMER_PRICE": "User wants price for a specific customer.",
            "GET_STOCK_LEVELS": "User wants current stock quantity.",
            "GET_LOW_STOCK_ALERTS": "User wants items low in stock.",
            "CREATE_QUOTATION": "User wants to create a sales quotation.",
            "GET_QUOTATIONS": "User wants to view existing quotations.",
            "GET_CUSTOMER_ORDERS": "User wants purchase history of customer.",
            "GET_WAREHOUSES": "User wants list of warehouses.",
            "GET_WAREHOUSE_STOCK": "User wants stock in specific warehouse.",
            "HOW_TO_ORDER": "User asks about ordering process.",
            "PAYMENT_METHODS": "User asks about payment options.",
            "GREETING": "User is saying hello.",
            "THANKS": "User is thanking.",
            "SMALL_TALK": "Casual conversation.",
            "TRAINING_MODULE": "User wants step-by-step tutorial.",
            "TRAINING_VIDEO": "User wants video tutorial.",
            "TRAINING_GUIDE": "User wants documentation or manual.",
            "TRAINING_FAQ": "User asks frequently asked questions.",
            "TRAINING_GLOSSARY": "User wants definitions of terms.",
            "TRAINING_WEBINAR": "User asks about live training.",
            "TRAINING_ONBOARDING": "New user needs help getting started.",
            "ANALYZE_INVENTORY_HEALTH": "User wants inventory health analysis.",
            "GET_REORDER_DECISIONS": "User wants reorder recommendations.",
            "ANALYZE_PRICING_OPPORTUNITIES": "User wants pricing insights.",
            "ANALYZE_CUSTOMER_BEHAVIOR": "User wants customer purchase patterns.",
            "FORECAST_DEMAND": "User wants demand forecast.",
            "GET_CROSS_SELL": "User wants cross-sell recommendations.",
            "GET_UPSELL": "User wants upsell recommendations.",
            "GET_SEASONAL_RECOMMENDATIONS": "User wants seasonal product picks.",
            "GET_TRENDING_PRODUCTS": "User wants trending/popular products.",
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
- quantity: numeric quantity (integer or null)
- unit: unit of measure (string or null)
- warehouse: warehouse name (string or null)
- price_related: true if asking about price (boolean)
- stock_related: true if asking about stock (boolean)

CRITICAL RULES:
- Extract only what is clearly present
- Use null when unsure
- Return ONLY the JSON object
- No spaces before/after values

Message: "{user_message}"

Respond with EXACTLY:
{{"item_name": null, "item_code": null, "customer_name": null, "quantity": null, "unit": null, "warehouse": null, "price_related": false, "stock_related": false}}
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
