"""
intent_overrides.py
===================
Rule-based intent correction layer that runs AFTER AI classification.

This module fixes common AI misclassifications by detecting entity patterns
that are more reliable than the small LLM's intent predictions.
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


def apply_intent_overrides(intent: str, entities: dict) -> str:
    """
    Rule-based intent correction layer.

    Runs AFTER the AI classifier and BEFORE the action router.
    Uses entity signals that are more reliable than the small model's
    intent classification for ambiguous phrasings.

    Args:
        intent: The current intent from classifier
        entities: Extracted entities (may include '_original_query' from entity extractor)

    Returns:
        The corrected intent string
    """
    original_intent = intent
    item_name = (entities.get("item_name") or "").strip()
    customer_name = (entities.get("customer_name") or "").strip()
    warehouse_name = (entities.get("warehouse") or "").strip()
    detail_mode = entities.get("detail_mode", False)
    
    # Get original query if available (from entity extractor)
    original_query = (entities.get("_original_query") or "").lower()

    # =========================================================
    # 🚫 PROTECTED INTENTS - NEVER OVERRIDE THESE
    # =========================================================
    PROTECTED_INTENTS = {
        "GET_CROSS_SELL",           # Never override cross-sell
        "GET_UPSELL",               # Never override upsell
        "GET_SEASONAL_RECOMMENDATIONS",  # Never override seasonal
        "GET_TRENDING_PRODUCTS",    # Never override trending
        "RECOMMEND_ITEMS",          # Never override recommendations
        "RECOMMEND_CUSTOMERS",      # Never override customer recommendations
        "COMPETITOR_PRICE_CHECK",   # Never override competitor pricing
        "FIND_BEST_PRICE",          # Never override best price
        "MARKET_INTELLIGENCE",      # Never override market intelligence
        "PRICE_ALERT",              # Never override price alerts
    }
    
    if intent in PROTECTED_INTENTS:
        logger.debug(f"🛡️ Protected intent '{intent}' - no override applied")
        return intent

    # =========================================================
    # 🔍 CROSS-SELL DETECTION - Even if intent got misclassified
    # =========================================================
    cross_sell_patterns = [
        "also bought", "with", "together", "bundle", "other customers",
        "customers who bought", "frequently bought", "people also buy",
        "commonly bought", "what else", "buys with", "items customers buys with"
    ]
    
    if item_name and any(pattern in original_query for pattern in cross_sell_patterns):
        logger.info(f"🔄 Cross-sell pattern detected for '{item_name}' - forcing GET_CROSS_SELL")
        return "GET_CROSS_SELL"
    
    # =========================================================
    # 📈 UPSELL DETECTION
    # =========================================================
    upsell_patterns = [
        "better version", "upgrade", "premium", "higher quality",
        "better than", "superior", "deluxe", "professional",
        "commercial grade", "enhanced"
    ]
    
    if item_name and any(pattern in original_query for pattern in upsell_patterns):
        logger.info(f"📈 Upsell pattern detected for '{item_name}' - forcing GET_UPSELL")
        return "GET_UPSELL"
    
    # =========================================================
    # 🌱 SEASONAL DETECTION
    # =========================================================
    seasonal_patterns = [
        "seasonal", "what to plant", "best for", "this season",
        "planting guide", "what grows in", "in season",
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "spring", "summer", "fall", "autumn", "winter"
    ]
    
    if any(pattern in original_query for pattern in seasonal_patterns):
        logger.info(f"🌱 Seasonal pattern detected - forcing GET_SEASONAL_RECOMMENDATIONS")
        return "GET_SEASONAL_RECOMMENDATIONS"
    
    # =========================================================
    # 📊 TRENDING DETECTION
    # =========================================================
    trending_patterns = [
        "trending", "popular now", "hot", "best sellers",
        "most popular", "top selling", "in demand", "what's trending"
    ]
    
    if any(pattern in original_query for pattern in trending_patterns):
        logger.info(f"📊 Trending pattern detected - forcing GET_TRENDING_PRODUCTS")
        return "GET_TRENDING_PRODUCTS"

    # ── RULE 1: item + customer → GET_CUSTOMER_PRICE ──────────────────
    # "price of vegimax for magomano" → both entities extracted
    if item_name and customer_name:
        logger.debug(f"RULE 1: item + customer -> GET_CUSTOMER_PRICE")
        return "GET_CUSTOMER_PRICE"

    # ── RULE 2: customer only, no item, price context → try GET_CUSTOMER_PRICE ──
    # This handles "magomano price" where item_name failed to extract
    if customer_name and not item_name:
        # Only override if original intent suggests pricing
        if intent in ("GET_ITEM_PRICE", "GET_ITEMS_ADVANCED"):
            logger.debug(f"RULE 2: customer only with price context -> GET_CUSTOMER_PRICE")
            return "GET_CUSTOMER_PRICE"

    # ── RULE 3: item only, price keyword context → GET_ITEM_PRICE ─────
    # Protects against GET_ITEMS_ADVANCED when user clearly wants a price.
    if item_name and not customer_name:
        if intent == "GET_ITEMS_ADVANCED" and not warehouse_name:
            logger.debug(f"RULE 3: item only, no warehouse -> GET_ITEM_PRICE")
            return "GET_ITEM_PRICE"

    # ── RULE 4: warehouse queries ──────────────────────────────────────
    # 4a: Explicit warehouse mention with warehouse entity
    if warehouse_name:
        # Stock in specific warehouse
        if any(word in intent for word in ["GET_ITEMS", "GET_ITEMS_ADVANCED"]):
            logger.debug(f"RULE 4a: warehouse entity -> GET_WAREHOUSE_STOCK")
            return "GET_WAREHOUSE_STOCK"
        
        # Low stock alerts for specific warehouse
        if "low stock" in original_intent.lower() or "alert" in original_intent.lower():
            logger.debug(f"RULE 4a: warehouse + low stock -> GET_LOW_STOCK_ALERTS")
            return "GET_LOW_STOCK_ALERTS"
    
    # 4b: No warehouse entity but warehouse keywords in item_name
    # This handles cases where warehouse wasn't extracted but is in the query
    warehouse_keywords = ["warehouse", "store", "branch", "depot", "facility"]
    if not warehouse_name and item_name:
        item_lower = item_name.lower()
        for keyword in warehouse_keywords:
            if keyword in item_lower:
                # Extract the warehouse name from item_name
                # Example: "nairobi warehouse" -> warehouse="nairobi", item_name cleared
                warehouse_candidate = item_lower.replace(keyword, "").strip()
                if warehouse_candidate and len(warehouse_candidate) > 1:
                    entities["warehouse"] = warehouse_candidate
                    warehouse_name = warehouse_candidate
                else:
                    # If only "warehouse" was extracted, use a default
                    entities["warehouse"] = "main"
                    warehouse_name = "main"
                
                entities["item_name"] = None
                item_name = None
                
                if "low stock" in original_intent.lower() or "alert" in original_intent.lower():
                    logger.debug(f"RULE 4b: warehouse from item_name + low stock -> GET_LOW_STOCK_ALERTS")
                    return "GET_LOW_STOCK_ALERTS"
                else:
                    logger.debug(f"RULE 4b: warehouse from item_name -> GET_WAREHOUSE_STOCK")
                    return "GET_WAREHOUSE_STOCK"
    
    # 4c: Generic warehouse queries without specific warehouse name
    warehouse_query_phrases = [
        "warehouse", "stock in", "inventory at", "items in", 
        "available in", "located in", "warehouses"
    ]
    
    if not warehouse_name and not item_name and not customer_name:
        for phrase in warehouse_query_phrases:
            if phrase in original_query:
                if "low stock" in original_query or "alert" in original_query:
                    logger.debug(f"RULE 4c: generic warehouse + low stock -> GET_LOW_STOCK_ALERTS")
                    return "GET_LOW_STOCK_ALERTS"
                elif "warehouses" in original_query or "list" in original_query:
                    logger.debug(f"RULE 4c: list warehouses -> GET_WAREHOUSES")
                    return "GET_WAREHOUSES"
                else:
                    logger.debug(f"RULE 4c: generic warehouse -> GET_WAREHOUSE_STOCK")
                    return "GET_WAREHOUSE_STOCK"

    # ── RULE 5: GET_WAREHOUSES detection ──────────────────────────────
    # "show me all warehouses", "list warehouses"
    warehouse_list_phrases = ["all warehouses", "list warehouses", "show warehouses", "warehouses available"]
    if not warehouse_name and intent in ["GET_ITEMS", "GET_ITEMS_ADVANCED"]:
        for phrase in warehouse_list_phrases:
            if phrase in original_query:
                logger.debug(f"RULE 5: list warehouses -> GET_WAREHOUSES")
                return "GET_WAREHOUSES"

    # ── WAREHOUSE QUERIES: Clear bogus item_name ──────────────────────
    # "show me stock in warehouse" often extracts item_name='show'
    if intent in ("GET_WAREHOUSES", "GET_WAREHOUSE_STOCK", "GET_LOW_STOCK_ALERTS"):
        COMMAND_VERBS = {"show", "list", "get", "find", "display", "tell", "me", "stock", "inventory"}
        if item_name and item_name.lower() in COMMAND_VERBS:
            entities["item_name"] = None
            logger.info(f"🧹 Cleared bogus item_name='{item_name}' from warehouse query")

    # ── RECOMMENDATION QUERIES: Clear bogus customer names ─────────────
    # "recommend a customer to buy vegimax" extracts customer_name='to buy vegimax'
    # "recommend customers who would buy X" extracts customer_name='who would buy X'
    if intent in ("RECOMMEND_CUSTOMERS", "RECOMMEND_ITEMS"):
        if customer_name:
            bogus_patterns = [
                "to buy", "for buying", "who buy", "who would buy",
                "that buy", "who purchase", "to purchase", "who would purchase"
            ]
            if any(p in customer_name.lower() for p in bogus_patterns):
                logger.info(f"🧹 Cleared bogus customer_name='{customer_name}' from recommendation query")
                entities["customer_name"] = None
                customer_name = None  # Update local variable too

    if intent != original_intent:
        logger.info(
            f"Intent overridden: '{original_intent}' -> '{intent}' "
            f"(item='{item_name}', customer='{customer_name}', warehouse='{warehouse_name}')"
        )
    else:
        logger.debug(f"No override applied for intent '{intent}'")

    return intent