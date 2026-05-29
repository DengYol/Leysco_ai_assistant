"""
intent_overrides.py
===================
Rule-based intent correction layer that runs AFTER AI classification.

This module fixes common AI misclassifications by detecting entity patterns
that are more reliable than the small LLM's intent predictions.
"""

import logging
from typing import Dict
import re

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
        "CREATE_QUOTATION",         # CRITICAL: Never override quotation creation
        "GET_TOP_SELLING_ITEMS",    # CRITICAL: Never override top selling items
        "GET_SLOW_MOVING_ITEMS",    # CRITICAL: Never override slow moving items
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
        "GET_WAREHOUSE_STOCK",      # PROTECT: Never override warehouse stock
        "GET_WAREHOUSES",           # PROTECT: Never override warehouse listing
        "GET_LOW_STOCK_ALERTS",     # PROTECT: Never override low stock alerts
    }
    
    if intent in PROTECTED_INTENTS:
        logger.debug(f"🛡️ Protected intent '{intent}' - no override applied")
        return intent
    
    # =========================================================
    # 🚨 CRITICAL FIX: Check for price queries FIRST
    # =========================================================
    # This prevents seasonal override from triggering on "Price of SPRING KICK STARTER"
    # because "spring" would otherwise be detected as a seasonal keyword.
    
    # Check if this is a price query
    price_keywords = ["price", "cost", "how much", "charge", "rate", "bei", "gharama", "thamani"]
    is_price_query = any(keyword in original_query for keyword in price_keywords)
    
    # Also check if intent is already price-related
    is_price_intent = intent in ["GET_ITEM_PRICE", "GET_CUSTOMER_PRICE", "GET_COMPETITOR_PRICE"]
    
    if is_price_query or is_price_intent:
        logger.debug(f"💰 Price query detected - skipping all intent overrides")
        return intent
    
    # =========================================================
    # ⚠️ FIX: Check for same value in item_name and customer_name
    # =========================================================
    # This indicates an extraction error, not a real customer price query
    # Example: "price of Punched Washer" extracts both item_name and customer_name
    if item_name and customer_name and item_name.lower() == customer_name.lower():
        logger.info(f"⚠️ CRITICAL FIX: Same value in item_name and customer_name: '{item_name}'")
        
        # Check if this is a price query (already checked above, but double-check)
        if is_price_query:
            # This is a price query - clear customer_name, keep item_name, fix intent
            logger.info(f"🔧 FIX: Price query detected - clearing customer_name, keeping item_name, setting GET_ITEM_PRICE")
            entities["customer_name"] = None
            customer_name = None
            return "GET_ITEM_PRICE"
        else:
            # Not a price query - might be a warehouse or other query
            # Log warning and let other rules handle it
            logger.warning(f"⚠️ Same value in item_name and customer_name but not a price query: '{item_name}' | Query: '{original_query}'")
    
    # =========================================================
    # 🔍 CHECK FOR WAREHOUSE QUERIES FIRST (high priority)
    # =========================================================
    # This must come BEFORE Rule 1 (item+customer) because warehouse queries
    # often have both item_name and customer_name set incorrectly.
    
    # Check if this is a warehouse-related query
    warehouse_keywords = ["warehouse", "stock in", "inventory at", "dispatch", "store", "branch"]
    is_warehouse_query = any(kw in original_query for kw in warehouse_keywords)
    
    # If intent is already GET_WAREHOUSE_STOCK or GET_WAREHOUSES, preserve it
    if intent in ["GET_WAREHOUSE_STOCK", "GET_WAREHOUSES", "GET_LOW_STOCK_ALERTS"]:
        if warehouse_name or is_warehouse_query:
            logger.debug(f"🏭 Preserving warehouse intent: {intent}")
            return intent
    
    # Warehouse stock query detection (specific warehouse)
    if is_warehouse_query and ("stock" in original_query or "inventory" in original_query):
        logger.info(f"🏭 Warehouse stock query detected - forcing GET_WAREHOUSE_STOCK")
        return "GET_WAREHOUSE_STOCK"
    
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
    # 🌱 SEASONAL DETECTION - WITH PRICE QUERY PROTECTION
    # =========================================================
    # IMPORTANT: We already checked for price queries above, so any seasonal
    # detection here is safe from overriding price queries.
    
    # Seasonal keywords - but only when they appear with seasonal context
    # The word "spring" alone is NOT enough - must have seasonal context
    seasonal_context_patterns = [
        r'\bseasonal\s+(?:items?|products?|recommendations?)\b',
        r'\b(?:summer|winter|fall|autumn)\s+(?:items?|products?|deals?|promotions?)\b',
        r'\b(?:rainy|dry|festive|holiday)\s+season\s+(?:items?|products?)\b',
        r'\bwhat\'?s?\s+(?:in|for)\s+season\b',
        r'\bshow\s+seasonal\s+(?:items?|products?)\b',
        r'\bseasonal\s+recommendations?\b',
        r'\b(?:spring|summer|winter|fall)\s+collection\b',
        r'\b(?:spring|summer|winter|fall)\s+sale\b',
        r'\bplanting\s+guide\b',
        r'\bwhat\s+to\s+plant\b',
        r'\bin\s+season\b',
    ]
    
    # Single word seasonal check (with safeguards)
    seasonal_words = ["spring", "summer", "fall", "autumn", "winter", "seasonal"]
    
    # Check if seasonal word appears but is likely part of an item name
    # Common item name patterns that contain seasonal words
    item_name_patterns = [
        r'spring\s+(?:kick|starter|boot|shock|coil|leaf|washer|bolt|screw)',
        r'summer\s+(?:tire|tyre|oil|promotion|sale)',
        r'winter\s+(?:tire|tyre|oil|coat|jacket)',
    ]
    
    is_item_name_containing_seasonal = False
    for pattern in item_name_patterns:
        if re.search(pattern, original_query, re.IGNORECASE):
            is_item_name_containing_seasonal = True
            logger.debug(f"Seasonal word appears to be part of item name: {pattern}")
            break
    
    # Only apply seasonal override if:
    # 1. We have seasonal context patterns, OR
    # 2. Seasonal word appears but NOT as part of an item name
    seasonal_detected = False
    
    for pattern in seasonal_context_patterns:
        if re.search(pattern, original_query, re.IGNORECASE):
            seasonal_detected = True
            break
    
    # Check for standalone seasonal words (with context)
    if not seasonal_detected and not is_item_name_containing_seasonal:
        for word in seasonal_words:
            if word in original_query.split():
                # Look for seasonal context words nearby
                seasonal_context = ["items", "products", "recommend", "guide", "plant", "crop"]
                if any(ctx in original_query for ctx in seasonal_context):
                    seasonal_detected = True
                    break
    
    if seasonal_detected:
        logger.info(f"🌱 Seasonal pattern detected - forcing GET_SEASONAL_RECOMMENDATIONS")
        return "GET_SEASONAL_RECOMMENDATIONS"

    # =========================================================
    # 📊 TRENDING DETECTION - Don't override top selling/slow moving
    # =========================================================
    trending_patterns = [
        "trending", "popular now", "hot", "best sellers",
        "most popular", "in demand", "what's trending"
    ]
    
    # Only apply trending override if it's not already a protected analytics intent
    if any(pattern in original_query for pattern in trending_patterns):
        if intent not in ["GET_TOP_SELLING_ITEMS", "GET_SLOW_MOVING_ITEMS"]:
            logger.info(f"📊 Trending pattern detected - forcing GET_TRENDING_PRODUCTS")
            return "GET_TRENDING_PRODUCTS"

    # ── RULE 1: item + customer → GET_CUSTOMER_PRICE ──────────────────
    # "price of vegimax for magomano" → both entities extracted
    # BUT skip if this is actually a warehouse query (detected above)
    # AND skip if they're the same value (already handled above as extraction error)
    if item_name and customer_name and not is_warehouse_query:
        # Make sure they're not the same value (extraction error)
        if item_name.lower() != customer_name.lower():
            logger.debug(f"RULE 1: item + customer -> GET_CUSTOMER_PRICE")
            return "GET_CUSTOMER_PRICE"

    # ── RULE 2: customer only, no item, price context → try GET_CUSTOMER_PRICE ──
    # This handles "magomano price" where item_name failed to extract
    if customer_name and not item_name and not is_warehouse_query:
        # Only override if original intent suggests pricing
        if intent in ("GET_ITEM_PRICE", "GET_ITEMS_ADVANCED"):
            logger.debug(f"RULE 2: customer only with price context -> GET_CUSTOMER_PRICE")
            return "GET_CUSTOMER_PRICE"

    # ── RULE 3: item only, price keyword context → GET_ITEM_PRICE ─────
    # Protects against GET_ITEMS_ADVANCED when user clearly wants a price.
    # Also catches GET_PURCHASE_ORDERS misclassification for price queries
    if item_name and not customer_name and not is_warehouse_query:
        # Check if this is a price query
        if is_price_query:
            # Item-only price query should always be GET_ITEM_PRICE
            logger.info(f"RULE 3 (ENHANCED): item only + price query -> GET_ITEM_PRICE")
            return "GET_ITEM_PRICE"
        elif intent == "GET_ITEMS_ADVANCED" and not warehouse_name:
            # Original logic for non-price queries
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
                customer_name = None

    # =========================================================
    # 🚫 BLOCK CROSS-SELL OVERRIDE FOR QUOTATION
    # =========================================================
    # If the query contains quotation keywords, prevent cross-sell override
    quotation_keywords = ["create", "quotation", "quote", "cash sale", "with", "vegimax"]
    if any(keyword in original_query for keyword in quotation_keywords) and len(original_query.split()) > 8:
        if intent == "GET_CROSS_SELL":
            logger.info(f"📝 Quotation pattern detected - overriding GET_CROSS_SELL to CREATE_QUOTATION")
            return "CREATE_QUOTATION"

    if intent != original_intent:
        logger.info(
            f"Intent overridden: '{original_intent}' -> '{intent}' "
            f"(item='{item_name}', customer='{customer_name}', warehouse='{warehouse_name}')"
        )
    else:
        logger.debug(f"No override applied for intent '{intent}'")

    return intent