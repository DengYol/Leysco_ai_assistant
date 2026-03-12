import json
import logging
import re
from app.services.llm_service import LLMService
from app.ai_engine.prompt_manager import PromptManager, VALID_INTENTS
# ADD THIS IMPORT
from app.ai_engine.swahili_support import SwahiliSupport

logger = logging.getLogger(__name__)

# All valid intents as a set for fast lookup
_VALID_INTENTS_SET = set(VALID_INTENTS)

# ---------------------------------------------------------------------------
# SMALL TALK / ACKNOWLEDGEMENT WORDS
# Shared between fast-path and rule-based so both catch the same words
# ---------------------------------------------------------------------------
_ACKNOWLEDGEMENT_WORDS = {
    "okay", "ok", "alright", "sure", "got it", "i see", "understood",
    "noted", "cool", "great", "nice", "sounds good", "makes sense",
    "no problem", "no worries", "fine", "yep", "yup", "yeah", "yes",
    "nope", "no", "k", "kk", "hmm", "hm", "interesting", "wow",
    "oh", "ah", "lol", "haha", "good", "nice one", "perfect",
}

_FAREWELL_WORDS = {
    "bye", "goodbye", "see you", "see ya", "later", "talk later",
    "good night", "take care", "ttyl", "cya",
}

# Cross-sell and recommendation phrases to protect from override
_CROSS_SELL_PHRASES = {
    "customers who bought", "also bought", "frequently bought",
    "people also buy", "others bought", "similar customers bought",
    "what else do customers buy with", "commonly bought with",
    "bundle with", "frequently purchased together", "who bougth",
    "who bought", "customers who buy", "people who buy",
    "customers who buys", "people who buys", "who buys"
}


class IntentClassifier:
    def __init__(self):
        self.llm = LLMService()
        self.prompt_manager = PromptManager()
        # ADD THIS LINE
        self.swahili = SwahiliSupport()

    # -------------------------------------------------------------------------
    # RULE-BASED INTENT ENGINE
    # -------------------------------------------------------------------------
    def _rule_based_intent(self, text: str) -> str:
        text = text.lower().strip()

        # ── CONVERSATIONAL ────────────────────────────────────────────────────
        if any(w in text for w in ["hi", "hello", "hey", "greetings",
                                    "good morning", "good afternoon", "good evening"]):
            return "GREETING"

        if any(w in text for w in ["thanks", "thank you", "appreciate", "cheers"]):
            return "THANKS"

        # ✅ FIX: Acknowledgements & farewells → SMALL_TALK
        stripped = text.rstrip("!?.,")
        if stripped in _ACKNOWLEDGEMENT_WORDS or stripped in _FAREWELL_WORDS:
            return "SMALL_TALK"
        for phrase in _ACKNOWLEDGEMENT_WORDS | _FAREWELL_WORDS:
            if stripped.startswith(phrase + " "):
                return "SMALL_TALK"

        # ── TRAINING & ONBOARDING ─────────────────────────────────────────────
        if any(p in text for p in [
            "how to", "learn", "training", "tutorial", "guide",
            "teach me", "walk me through", "show me how",
            "getting started", "beginner", "new user", "onboarding",
            "help me understand", "how do i", "how can i"
        ]):
            if any(w in text for w in ["video", "watch", "screencast", "demo"]):
                return "TRAINING_VIDEO"
            elif any(w in text for w in ["pdf", "document", "manual", "handbook"]):
                return "TRAINING_GUIDE"
            elif any(w in text for w in ["faq", "questions", "answers", "common issues"]):
                return "TRAINING_FAQ"
            elif any(w in text for w in ["webinar", "live", "session", "class", "workshop"]):
                return "TRAINING_WEBINAR"
            elif any(w in text for w in ["glossary", "term", "definition", "meaning",
                                          "what does", "what is", "sku", "moq", "uom",
                                          "eta", "grn", "dn"]):
                return "TRAINING_GLOSSARY"
            else:
                return "TRAINING_MODULE"

        # =========================================================
        # 🎯 SMART RECOMMENDATION INTENTS - ADDED HERE
        # =========================================================
        
        # Cross-sell suggestions
        if any(p in text for p in _CROSS_SELL_PHRASES):
            logger.info(f"Rule-based: GET_CROSS_SELL detected")
            return "GET_CROSS_SELL"

        # Upsell suggestions
        if any(p in text for p in [
            "better version", "upgrade", "premium alternative",
            "higher quality", "better value", "more expensive",
            "what's better than", "superior to", "upgrade to",
            "deluxe version", "professional grade", "commercial grade",
            "premium version", "enhanced version"
        ]):
            logger.info(f"Rule-based: GET_UPSELL detected")
            return "GET_UPSELL"

        # Seasonal recommendations
        if any(p in text for p in [
            "seasonal", "what to plant in", "best for this season",
            "recommend for", "good for planting", "seasonal crops",
            "what grows in", "planting guide for", "seasonal recommendations",
            "what should i plant in", "what to grow in"
        ]):
            logger.info(f"Rule-based: GET_SEASONAL_RECOMMENDATIONS detected")
            return "GET_SEASONAL_RECOMMENDATIONS"

        # Trending products
        if any(p in text for p in [
            "trending", "popular now", "hot items", "best sellers",
            "most popular", "top selling", "what's trending",
            "customers are buying", "in demand", "high demand",
            "what is trending", "what's popular"
        ]):
            logger.info(f"Rule-based: GET_TRENDING_PRODUCTS detected")
            return "GET_TRENDING_PRODUCTS"

        # =========================================================
        # 🆕 COMPETITOR PRICING INTENTS - HIGHEST PRIORITY
        # =========================================================
        
        # PRICE ALERT - Check first (highest priority)
        if any(p in text for p in [
            "price alert", "notify when price drops", "alert me when price",
            "track price", "price monitoring", "price change alert",
            "alert me when.*price drops", "notify me when.*price drops"
        ]):
            logger.info(f"Rule-based: PRICE_ALERT detected")
            return "PRICE_ALERT"

        # MARKET INTELLIGENCE
        if any(p in text for p in [
            "market intelligence", "market analysis", "price trends",
            "market insights", "market overview", "industry prices",
            "sector pricing", "agricultural prices", "farm prices"
        ]):
            logger.info(f"Rule-based: MARKET_INTELLIGENCE detected")
            return "MARKET_INTELLIGENCE"

        # COMPETITOR PRICE CHECK (including comparison)
        if any(p in text for p in [
            "competitor price", "competitor prices", "price at", "prices at",
            "how much is.*at", "what does.*charge", "market price", "market prices",
            "other sellers", "other vendors", "compare price", "price comparison",
            "compare with", "how does.*compare", "compare prices for",
            "comparison between", "vs", "versus"
        ]):
            logger.info(f"Rule-based: COMPETITOR_PRICE_CHECK detected")
            return "COMPETITOR_PRICE_CHECK"

        # FIND BEST PRICE
        if any(p in text for p in [
            "best price", "cheapest", "lowest price", "where to buy",
            "who sells cheapest", "best deal", "best value", "most affordable",
            "who sells.*at the lowest", "who sells.*cheapest",
            "where can i buy.*cheapest", "who has the best price",
            "where to get.*cheap", "who sells.*for less",
            "who has the lowest price", "where can i find.*cheap",
            "where is.*cheapest",
        ]):
            logger.info(f"Rule-based: FIND_BEST_PRICE detected")
            return "FIND_BEST_PRICE"

        # =========================================================
        # 🧠 DECISION SUPPORT INTENTS
        # =========================================================
        if any(p in text for p in [
            "inventory health", "stock health", "inventory analysis", "health check",
            "inventory status report", "stock status report"
        ]):
            return "ANALYZE_INVENTORY_HEALTH"

        if any(p in text for p in [
            "reorder", "what to order", "order decisions", "what should i order",
            "reorder recommendations", "reorder decisions", "what to reorder",
            "order recommendations", "suggest reorder"
        ]):
            return "GET_REORDER_DECISIONS"

        if any(p in text for p in [
            "pricing opportunities", "price opportunities", "best prices",
            "price analysis", "price trends", "price drops", "price hikes",
            "good deals", "best value", "cheapest items"
        ]):
            return "ANALYZE_PRICING_OPPORTUNITIES"

        if any(p in text for p in [
            "customer behavior", "customer analysis", "customer insights",
            "analyze customer", "customer patterns", "purchase patterns",
            "customer trends", "customer profiling"
        ]):
            return "ANALYZE_CUSTOMER_BEHAVIOR"

        if any(p in text for p in [
            "forecast", "demand forecast", "sales forecast", "predict demand",
            "future demand", "demand prediction", "sales prediction",
            "how much will i sell", "expected sales"
        ]):
            return "FORECAST_DEMAND"

        # ── CUSTOMERS (before items) ──────────────────────────────────────────
        if any(p in text for p in [
            "customers", "clients", "buyers",
            "show me customers", "list customers", "list clients",
            "customer list", "client list", "all customers"
        ]):
            # Make sure this isn't a cross-sell query
            if not any(phrase in text for phrase in _CROSS_SELL_PHRASES):
                return "GET_CUSTOMERS"

        # ── CONTACT INFO ──────────────────────────────────────────────────────
        if any(p in text for p in [
            "phone", "phone number", "contact", "email", "support",
            "reach you", "call", "whatsapp", "telephone", "mobile"
        ]):
            return "CONTACT_INFO"

        # ── COMPANY INFO ──────────────────────────────────────────────────────
        if any(p in text for p in ["about leysco", "tell me about", "what is leysco",
                                    "who is leysco"]):
            return "COMPANY_INFO"

        if any(p in text for p in ["easeed", "agriscope", "product line", "brands"]):
            if "price" not in text and "stock" not in text:
                return "PRODUCT_INFO"

        # ── PAYMENT METHODS ───────────────────────────────────────────────────
        if any(p in text for p in [
            "payment method", "payment methods", "payment option", "payment options",
            "how to pay", "accepted payment", "do you accept", "pay with",
            "mpesa", "bank transfer", "cash", "card", "credit card",
            "paybill", "till number"
        ]):
            return "PAYMENT_METHODS"

        # ── ORDERING PROCESS ──────────────────────────────────────────────────
        if any(p in text for p in [
            "how to order", "place an order", "how do i order", "ordering process",
            "how to place order", "how can i order", "order procedure"
        ]):
            return "HOW_TO_ORDER"

        # ── QUOTATIONS ────────────────────────────────────────────────────────
        if any(p in text for p in [
            "make a quote", "make quote", "create quote", "create quotation",
            "generate quote", "prepare quote", "new quote", "new quotation"
        ]):
            return "CREATE_QUOTATION"

        if any(p in text for p in [
            "show quotes", "show quotations", "list quotes", "view quotes",
            "my quotes", "my quotations"
        ]):
            return "GET_QUOTATIONS"

        if "quote" in text or "quotation" in text:
            if any(w in text for w in ["make", "create", "generate", "prepare", "new"]):
                return "CREATE_QUOTATION"
            return "GET_QUOTATIONS"

        # ── PRICING ───────────────────────────────────────────────────────────
        has_price_word = bool(re.search(
            r"\b(price|cost|how\s+much|what'?s?\s*(the)?\s*price|pricing|how\s+expensive|charge|rate)\b",
            text, re.IGNORECASE
        ))

        if has_price_word:
            has_for = "for" in text and any(
                c in text for c in ["customer", "client", "lumarx", "smd", "cti", "blockies"]
            )
            if has_for or "for" in text[-15:]:
                return "GET_CUSTOMER_PRICE"
            return "GET_ITEM_PRICE"

        # ── RECOMMENDATIONS (before generic items) ────────────────────────────
        if any(w in text for w in ["recommend", "suggest", "best selling",
                                    "top selling", "popular", "good for"]):
            return "RECOMMEND_ITEMS"

        # ── STOCK & INVENTORY ─────────────────────────────────────────────────
        if any(p in text for p in [
            "stock level", "stock levels", "current stock", "stock status",
            "how much stock", "stock report", "inventory status"
        ]):
            return "GET_STOCK_LEVELS"

        if any(p in text for p in ["low stock", "low inventory", "stock alert",
                                    "running low", "alert"]):
            return "GET_LOW_STOCK_ALERTS"

        if any(p in text for p in ["stock in", "stock at", "inventory in",
                                    "inventory at", "which warehouse has"]):
            return "GET_WAREHOUSE_STOCK"

        # ── PRODUCT-SPECIFIC SEARCH ───────────────────────────────────────────
        common_products = [
            "cabbage", "tomato", "maize", "pepper", "cauliflower", "onion",
            "vegimax", "easeed", "tosheka", "kh500", "mh401", "snowball",
            "yolo wonder", "seed", "seeds", "fertilizer", "pesticide"
        ]

        # ✅ FIX: Better product detection - check if text contains ANY product
        has_product = False
        product_mentioned = None
        for prod in common_products:
            if prod in text:
                has_product = True
                product_mentioned = prod
                break

        if has_product:
            # If the query is just the product name or simple phrase, return GET_ITEMS
            if len(text.split()) <= 3 or product_mentioned == text.strip():
                return "GET_ITEMS"
            
            if has_price_word:
                return "GET_ITEM_PRICE"
            if "stock" in text or "available" in text or "in stock" in text:
                return "GET_STOCK_LEVELS"
            if any(w in text for w in ["low", "alert", "running low"]):
                return "GET_LOW_STOCK_ALERTS"
            if "warehouse" in text:
                return "GET_WAREHOUSE_STOCK"
            return "GET_ITEMS"

        # ── ORDERS / INVOICES / DELIVERIES ────────────────────────────────────
        if re.search(r"\border(s)?\s+(for|from)\b|\binvoice(s)?\s+(for|from)\b", text):
            return "GET_CUSTOMER_ORDERS"

        if any(p in text for p in [
            "track delivery", "delivery status", "where is delivery", "track order"
        ]):
            return "TRACK_DELIVERY"

        if any(p in text for p in ["delivery history", "past deliveries",
                                    "previous deliveries"]):
            return "GET_DELIVERY_HISTORY"

        if any(p in text for p in ["outstanding deliver", "pending deliver", "undelivered"]):
            return "GET_OUTSTANDING_DELIVERIES"

        # ── WAREHOUSES ────────────────────────────────────────────────────────
        if any(w in text for w in ["warehouse", "warehouses", "storage location"]):
            if "stock" in text or "item" in text or "has" in text:
                return "GET_WAREHOUSE_STOCK"
            return "GET_WAREHOUSES"

        # ── GENERIC LISTS (last resort) ───────────────────────────────────────
        if any(w in text for w in ["sellable", "for sale", "saleable", "selling items"]):
            return "GET_SELLABLE_ITEMS"
        if any(w in text for w in ["purchasable", "to purchase", "buying items"]):
            return "GET_PURCHASABLE_ITEMS"
        if any(w in text for w in ["inventory items", "in inventory", "stock items"]):
            return "GET_INVENTORY_ITEMS"

        if any(w in text for w in ["show me items", "list items", "items", "products",
                                    "what items"]):
            return "GET_ITEMS"

        # If we get here and text contains a product name, return GET_ITEMS
        if has_product:
            return "GET_ITEMS"

        return "UNKNOWN"

    # -------------------------------------------------------------------------
    # SAFE JSON PARSER
    # -------------------------------------------------------------------------
    def _extract_json(self, text: str) -> dict | None:
        try:
            match = re.search(r"\{.*?\}", text, re.DOTALL | re.MULTILINE)
            if not match:
                return None
            return json.loads(match.group(0))
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # MAIN CLASSIFIER
    # -------------------------------------------------------------------------
    def classify(self, user_message: str) -> dict:
        text_lower = user_message.lower().strip()

        # 🌍 STEP 1: Check if query is in Swahili
        swahili_result = self.swahili.process_swahili_query(user_message)
        
        if swahili_result["detected_language"] != "en":
            logger.info(f"🇰🇪 Swahili query detected: {swahili_result['detected_language']}")
            logger.info(f"   Intent: {swahili_result['intent']}")
            logger.info(f"   Entities: {swahili_result['entities']}")
            
            # If Swahili processor found an intent, use it
            if swahili_result["intent"] != "UNKNOWN":
                return {
                    "intent": swahili_result["intent"],
                    "language": swahili_result["detected_language"],
                    "entities": swahili_result["entities"],
                    "original_text": user_message,
                    "normalized_text": swahili_result["normalized_text"]
                }
            
            # Otherwise, continue with normal classification
            # But use the cleaned text for better matching
            if swahili_result.get("normalized_text"):
                text_lower = swahili_result["normalized_text"].lower()

        # ── Fast path: short queries ──────────────────────────────────────────
        if len(text_lower) < 35:

            if any(w in text_lower for w in ["hi", "hello", "hey"]):
                logger.info("Fast-path: GREETING")
                return {"intent": "GREETING", "language": "en"}

            if any(w in text_lower for w in ["thanks", "thank you"]):
                logger.info("Fast-path: THANKS")
                return {"intent": "THANKS", "language": "en"}

            # ✅ FIX: Catch "okay", "sure", "got it", etc. BEFORE AI call
            stripped = text_lower.rstrip("!?.,")
            if stripped in _ACKNOWLEDGEMENT_WORDS or stripped in _FAREWELL_WORDS:
                logger.info(f"Fast-path: SMALL_TALK (ack word: '{stripped}')")
                return {"intent": "SMALL_TALK", "language": "en"}

            if any(w in text_lower for w in ["bye", "goodbye"]):
                logger.info("Fast-path: SMALL_TALK")
                return {"intent": "SMALL_TALK", "language": "en"}

            # Check for cross-sell in fast path
            if any(phrase in text_lower for phrase in _CROSS_SELL_PHRASES):
                logger.info("Fast-path: GET_CROSS_SELL")
                return {"intent": "GET_CROSS_SELL", "language": "en"}

            if "customers" in text_lower or "clients" in text_lower:
                # Make sure it's not a cross-sell query
                if not any(phrase in text_lower for phrase in _CROSS_SELL_PHRASES):
                    logger.info("Fast-path: GET_CUSTOMERS")
                    return {"intent": "GET_CUSTOMERS", "language": "en"}

            if any(w in text_lower for w in ["phone", "contact", "email"]):
                logger.info("Fast-path: CONTACT_INFO")
                return {"intent": "CONTACT_INFO", "language": "en"}

            if any(w in text_lower for w in ["how to", "learn", "tutorial", "guide"]):
                logger.info("Fast-path: TRAINING_MODULE")
                return {"intent": "TRAINING_MODULE", "language": "en"}

            # 🧠 Fast path for decision support short queries
            if any(w in text_lower for w in ["reorder", "forecast", "inventory health"]):
                logger.info("Fast-path: DECISION_SUPPORT")
                if "reorder" in text_lower:
                    return {"intent": "GET_REORDER_DECISIONS", "language": "en"}
                elif "forecast" in text_lower:
                    return {"intent": "FORECAST_DEMAND", "language": "en"}
                elif "inventory health" in text_lower:
                    return {"intent": "ANALYZE_INVENTORY_HEALTH", "language": "en"}

            # 🆕 Fast path for competitor pricing short queries
            if any(w in text_lower for w in ["price alert", "alert me", "notify when"]):
                logger.info("Fast-path: PRICE_ALERT")
                return {"intent": "PRICE_ALERT", "language": "en"}
            elif any(w in text_lower for w in ["market intelligence", "market analysis"]):
                logger.info("Fast-path: MARKET_INTELLIGENCE")
                return {"intent": "MARKET_INTELLIGENCE", "language": "en"}
            elif any(w in text_lower for w in ["competitor price", "market price"]):
                logger.info("Fast-path: COMPETITOR_PRICE_CHECK")
                return {"intent": "COMPETITOR_PRICE_CHECK", "language": "en"}
            elif any(w in text_lower for w in ["best price", "cheapest", "who sells"]):
                logger.info("Fast-path: FIND_BEST_PRICE")
                return {"intent": "FIND_BEST_PRICE", "language": "en"}

            # 🎯 Fast path for recommendation short queries - ADDED
            if any(w in text_lower for w in ["trending", "popular", "best sellers"]):
                logger.info("Fast-path: GET_TRENDING_PRODUCTS")
                return {"intent": "GET_TRENDING_PRODUCTS", "language": "en"}
            elif any(w in text_lower for w in ["customers who bought", "also bought"]):
                logger.info("Fast-path: GET_CROSS_SELL")
                return {"intent": "GET_CROSS_SELL", "language": "en"}
            elif any(w in text_lower for w in ["seasonal", "what to plant"]):
                logger.info("Fast-path: GET_SEASONAL_RECOMMENDATIONS")
                return {"intent": "GET_SEASONAL_RECOMMENDATIONS", "language": "en"}

        # ── Fast path: filtered item views ────────────────────────────────────
        if "sellable" in text_lower or "items for sale" in text_lower:
            return {"intent": "GET_SELLABLE_ITEMS", "language": "en"}
        if "inventory items" in text_lower or "items in inventory" in text_lower:
            return {"intent": "GET_INVENTORY_ITEMS", "language": "en"}
        if "purchasable" in text_lower or "items to purchase" in text_lower:
            return {"intent": "GET_PURCHASABLE_ITEMS", "language": "en"}

        # ── Check for simple product name queries (like "vegimax") ────────────
        common_products = [
            "cabbage", "tomato", "maize", "pepper", "cauliflower", "onion",
            "vegimax", "easeed", "tosheka", "kh500", "mh401", "snowball",
            "yolo wonder", "seed", "seeds", "fertilizer", "pesticide"
        ]
        
        # If the query is just a product name (1-2 words and matches a product)
        words = text_lower.split()
        if len(words) <= 2:
            for prod in common_products:
                if prod in text_lower:
                    logger.info(f"Fast-path: Simple product query '{prod}' → GET_ITEMS")
                    return {"intent": "GET_ITEMS", "language": "en"}

        # ── AI classification (primary) ───────────────────────────────────────
        try:
            prompt = self.prompt_manager.get_intent_prompt(user_message)
            response = self.llm.generate(prompt)

            if response and response.strip():
                data = self._extract_json(response)
                if data:
                    intent = data.get("intent", "").strip().upper()
                    if intent in _VALID_INTENTS_SET:
                        logger.info(f"AI detected: {intent}")

                        # Post-AI overrides
                        if any(p in text_lower for p in ["about leysco", "tell me about leysco"]):
                            intent = "COMPANY_INFO"
                        elif any(p in text_lower for p in [
                            "how to order", "place an order", "ordering process", "how do i order"
                        ]):
                            intent = "HOW_TO_ORDER"
                        elif any(p in text_lower for p in [
                            "payment method", "payment methods", "how to pay", "payment option"
                        ]):
                            intent = "PAYMENT_METHODS"
                        elif "customer" in text_lower and "price" in text_lower:
                            intent = "GET_CUSTOMER_PRICE"
                        elif "low stock" in text_lower or "stock alert" in text_lower:
                            intent = "GET_LOW_STOCK_ALERTS"
                        elif "stock level" in text_lower or "stock status" in text_lower:
                            intent = "GET_STOCK_LEVELS"
                        elif "warehouse" in text_lower and intent == "GET_ITEMS":
                            intent = "GET_WAREHOUSES"
                        
                        # ✅ FIXED: Only override to GET_CUSTOMERS if it's NOT a cross-sell query
                        elif "customers" in text_lower and intent not in ["GET_CROSS_SELL", "GET_UPSELL"]:
                            # Double-check it's not a cross-sell query
                            if not any(phrase in text_lower for phrase in _CROSS_SELL_PHRASES):
                                intent = "GET_CUSTOMERS"
                                logger.info(f"Override to GET_CUSTOMERS based on 'customers' keyword")
                        
                        elif any(w in text_lower for w in ["phone", "contact", "email"]) \
                                and intent not in ["CONTACT_INFO", "COMPANY_INFO"]:
                            intent = "CONTACT_INFO"

                        # ✅ FIX: Override even if AI misclassified an ack word
                        stripped = text_lower.rstrip("!?.,")
                        if stripped in _ACKNOWLEDGEMENT_WORDS or stripped in _FAREWELL_WORDS:
                            intent = "SMALL_TALK"

                        # Training overrides
                        elif any(p in text_lower for p in ["how to", "learn", "tutorial", "guide"]) \
                                and intent not in {
                                    "TRAINING_MODULE", "TRAINING_VIDEO", "TRAINING_GUIDE",
                                    "TRAINING_FAQ", "TRAINING_GLOSSARY", "TRAINING_WEBINAR"
                                }:
                            if "video" in text_lower or "watch" in text_lower:
                                intent = "TRAINING_VIDEO"
                            elif "faq" in text_lower or "question" in text_lower:
                                intent = "TRAINING_FAQ"
                            elif "webinar" in text_lower or "live" in text_lower:
                                intent = "TRAINING_WEBINAR"
                            elif any(t in text_lower for t in [
                                "sku", "moq", "uom", "eta", "definition", "meaning"
                            ]):
                                intent = "TRAINING_GLOSSARY"
                            else:
                                intent = "TRAINING_MODULE"

                        # 🧠 Decision Support overrides
                        elif any(p in text_lower for p in [
                            "inventory health", "stock health", "health check"
                        ]) and intent not in ["ANALYZE_INVENTORY_HEALTH"]:
                            intent = "ANALYZE_INVENTORY_HEALTH"

                        elif any(p in text_lower for p in [
                            "reorder", "what to order", "order decisions"
                        ]) and intent not in ["GET_REORDER_DECISIONS"]:
                            intent = "GET_REORDER_DECISIONS"

                        elif any(p in text_lower for p in [
                            "price opportunities", "best prices", "price drops"
                        ]) and intent not in ["ANALYZE_PRICING_OPPORTUNITIES"]:
                            intent = "ANALYZE_PRICING_OPPORTUNITIES"

                        elif any(p in text_lower for p in [
                            "customer behavior", "customer analysis", "customer insights"
                        ]) and intent not in ["ANALYZE_CUSTOMER_BEHAVIOR"]:
                            intent = "ANALYZE_CUSTOMER_BEHAVIOR"

                        elif any(p in text_lower for p in [
                            "forecast", "demand forecast", "predict demand"
                        ]) and intent not in ["FORECAST_DEMAND"]:
                            intent = "FORECAST_DEMAND"

                        # 🆕 Competitor Pricing overrides
                        elif any(p in text_lower for p in [
                            "price alert", "alert me when", "notify when", "track price"
                        ]):
                            intent = "PRICE_ALERT"
                            logger.info(f"Override to PRICE_ALERT based on keywords")
                            
                        elif any(p in text_lower for p in [
                            "market intelligence", "market analysis", "price trends"
                        ]):
                            intent = "MARKET_INTELLIGENCE"
                            logger.info(f"Override to MARKET_INTELLIGENCE based on keywords")
                            
                        elif any(p in text_lower for p in [
                            "compare", "comparison", "vs", "versus"
                        ]) and any(prod in text_lower for prod in common_products):
                            intent = "COMPETITOR_PRICE_CHECK"
                            logger.info(f"Override to COMPETITOR_PRICE_CHECK based on keywords")
                            
                        elif any(p in text_lower for p in [
                            "best price", "cheapest", "lowest price", "who sells", "where to buy"
                        ]):
                            intent = "FIND_BEST_PRICE"
                            logger.info(f"Override to FIND_BEST_PRICE based on keywords")

                        # 🎯 Recommendation overrides - ADDED
                        elif any(p in text_lower for p in _CROSS_SELL_PHRASES):
                            intent = "GET_CROSS_SELL"
                            logger.info(f"Override to GET_CROSS_SELL based on keywords")
                            
                        elif any(p in text_lower for p in [
                            "upgrade", "better version", "premium alternative"
                        ]):
                            intent = "GET_UPSELL"
                            logger.info(f"Override to GET_UPSELL based on keywords")
                            
                        elif any(p in text_lower for p in [
                            "seasonal", "what to plant", "planting guide"
                        ]):
                            intent = "GET_SEASONAL_RECOMMENDATIONS"
                            logger.info(f"Override to GET_SEASONAL_RECOMMENDATIONS based on keywords")
                            
                        elif any(p in text_lower for p in [
                            "trending", "popular", "best sellers", "top selling"
                        ]):
                            intent = "GET_TRENDING_PRODUCTS"
                            logger.info(f"Override to GET_TRENDING_PRODUCTS based on keywords")

                        # If AI returned UNKNOWN but we have a product name, override
                        if intent == "UNKNOWN":
                            for prod in common_products:
                                if prod in text_lower:
                                    logger.info(f"AI returned UNKNOWN but product '{prod}' detected → GET_ITEMS")
                                    intent = "GET_ITEMS"
                                    break

                        return {"intent": intent, "language": "en"}

        except Exception as e:
            logger.warning(f"LLM intent failed: {e}. Falling back to rules.")

        # ── Rule-based fallback ───────────────────────────────────────────────
        rule_intent = self._rule_based_intent(user_message)
        logger.info(f"Rule-based intent: {rule_intent}")
        return {"intent": rule_intent, "language": "en"}