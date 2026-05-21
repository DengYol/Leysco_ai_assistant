"""
recommendation_service.py
=========================
Intelligent recommendations for items and customers based on:
- Purchase history
- Item popularity (stock movement)
- Customer buying patterns
- Cross-sell opportunities
- Upsell suggestions
- Seasonal recommendations
- Trending products
- Customer segmentation (who buys what)

FIXED: Removed dependency on non-existent get_customer_purchase_history
FIXED: Use get_customer_orders instead
FIXED: Improved error handling with proper fallbacks
"""

import logging
import random
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from functools import lru_cache

logger = logging.getLogger(__name__)


class RecommendationService:
    """
    Provides intelligent recommendations for items and customers.
    
    Uses SAP data to suggest:
    - Popular items (based on stock turnover)
    - Items frequently bought together
    - Best customers for specific items
    - Similar customers (based on purchase patterns)
    - Cross-sell opportunities ("Customers who bought X also bought Y")
    - Upsell suggestions (better/premium alternatives)
    - Seasonal recommendations
    - Trending products
    """
    
    def __init__(self, api_service, pricing_service=None):
        self.api = api_service
        self.pricing = pricing_service
        
        # Cache for frequently bought together patterns
        self._frequently_bought_cache = {}
        self._last_cache_refresh = None
        self._customers_for_item_cache = {}
        self._similar_customers_cache = {}
        self._cache_ttl = timedelta(minutes=5)
        
        # Seasonal product mapping
        self.seasonal_products = {
            "january": ["summer crops", "tomato seeds", "cabbage seeds"],
            "february": ["planting season", "maize seeds", "fertilizer"],
            "march": ["long rain crops", "bean seeds", "pesticides"],
            "april": ["vegetable seeds", "onion sets", "potato seedlings"],
            "may": ["herbicides", "fungicides", "plant nutrients"],
            "june": ["harvesting tools", "storage bags", "drying sheets"],
            "july": ["post-harvest", "storage chemicals", "packaging"],
            "august": ["winter crops", "cabbage", "carrot seeds"],
            "september": ["planting season", "wheat seeds", "barley"],
            "october": ["short rain crops", "pea seeds", "green grams"],
            "november": ["irrigation", "greenhouse supplies", "mulch"],
            "december": ["festive season", "fresh produce", "value packs"],
        }
        
        # Upsell opportunities
        self.upsell_map = {
            "vegimax-10ml": {"upsell": "vegimax-30ml", "margin_increase": 25, "reason": "Better value per ml"},
            "vegimax-30ml": {"upsell": "vegimax-125ml", "margin_increase": 30, "reason": "Economic pack - 20% savings"},
            "vegimax-125ml": {"upsell": "vegimax-250ml", "margin_increase": 35, "reason": "Commercial size - best value"},
        }
        
        # Cross-sell associations
        self.cross_sell_map = {
            "vegimax": [
                {"item": "sprayer", "confidence": 0.95, "reason": "For proper application"},
                {"item": "gloves", "confidence": 0.85, "reason": "Safety gear"},
            ],
            "seeds": [
                {"item": "fertilizer", "confidence": 0.90, "reason": "For optimal growth"},
                {"item": "planting tools", "confidence": 0.85, "reason": "Makes planting easier"},
            ],
            "fertilizer": [
                {"item": "soil test kit", "confidence": 0.88, "reason": "Know your soil needs"},
                {"item": "spreader", "confidence": 0.82, "reason": "Even application"},
            ],
        }
    
    # =========================================================
    # ITEM RECOMMENDATIONS
    # =========================================================
    
    def get_recommended_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top recommended items based on popularity and availability."""
        try:
            inventory = self.api.get_inventory_report(limit=200)
            
            if not inventory:
                return self._get_sellable_items(limit)
            
            scored_items = []
            seen_codes = set()
            
            for record in inventory:
                item_code = record.get("ItemCode")
                if item_code in seen_codes:
                    continue
                seen_codes.add(item_code)
                
                on_hand = float(record.get("CurrentOnHand") or 0)
                committed = float(record.get("CurrentIsCommited") or 0)
                
                if on_hand <= 0:
                    continue
                
                if on_hand > committed:
                    score = committed
                else:
                    score = on_hand * 0.5
                
                scored_items.append({
                    "ItemCode": item_code,
                    "ItemName": record.get("ItemName"),
                    "score": score,
                    "OnHand": on_hand,
                    "Committed": committed,
                })
            
            scored_items.sort(key=lambda x: x["score"], reverse=True)
            top_items = scored_items[:limit * 2]
            
            recommendations = []
            for item in top_items:
                full_item = self.api.get_item_by_code(item["ItemCode"])
                if full_item and self._is_sellable(full_item):
                    price_info = self._get_price_info(item["ItemCode"])
                    full_item["Price"] = price_info.get("price")
                    full_item["Currency"] = price_info.get("currency", "KES")
                    full_item["RecommendationScore"] = item["score"]
                    full_item["Reason"] = "Popular choice based on sales velocity"
                    recommendations.append(full_item)
                    if len(recommendations) >= limit:
                        break
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error getting recommended items: {e}")
            return self._get_sellable_items(limit)
    
    def get_items_for_customer(self, customer_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Recommend items for a specific customer based on their purchase history."""
        try:
            # FIXED: Use get_customer_orders instead of get_customer_purchase_history
            orders = self.api.get_customer_orders(customer_code=customer_code, limit=50)
            
            if not orders:
                return self.get_recommended_items(limit)
            
            # Get items they've bought
            purchased_items = set()
            for order in orders:
                items = order.get("document_lines", []) or order.get("DocumentLines", [])
                for line in items:
                    item_code = line.get("ItemCode")
                    if item_code:
                        purchased_items.add(item_code)
            
            # Get popular items
            popular = self.get_recommended_items(limit * 2)
            
            # Filter out items they've already bought
            personalized = []
            for item in popular:
                item_code = item.get("ItemCode")
                if item_code not in purchased_items:
                    item["Reason"] = "Popular in your category"
                    item["Personalized"] = True
                    personalized.append(item)
                    if len(personalized) >= limit:
                        break
            
            return personalized
            
        except Exception as e:
            logger.error(f"Error getting items for customer {customer_code}: {e}")
            return self.get_recommended_items(limit)
    
    # =========================================================
    # CROSS-SELL & UPSELL
    # =========================================================
    
    def get_cross_sell_suggestions(self, item_name: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Get "Customers who bought X also bought Y" suggestions."""
        logger.info(f"🔄 Getting cross-sell suggestions for: {item_name}")
        
        item_lower = item_name.lower()
        suggestions = []
        
        for key, related_items in self.cross_sell_map.items():
            if key in item_lower:
                for rel in related_items[:limit]:
                    items = self.api.get_items(search=rel["item"], limit=1)
                    if items:
                        item = items[0]
                        price_info = self._get_price_info(item["ItemCode"])
                        suggestions.append({
                            "ItemCode": item["ItemCode"],
                            "ItemName": item["ItemName"],
                            "Price": price_info.get("price"),
                            "Currency": price_info.get("currency", "KES"),
                            "Confidence": rel["confidence"],
                            "Reason": rel["reason"],
                            "StockStatus": self._check_stock_status(item["ItemCode"]),
                            "Action": "Add to cart",
                            "Type": "cross_sell"
                        })
                break
        
        if not suggestions:
            suggestions = self._get_category_based_cross_sell(item_lower, limit)
        
        return suggestions
    
    def get_upsell_suggestions(self, item_name: str, limit: int = 2) -> List[Dict[str, Any]]:
        """Get upsell suggestions (better/premium alternatives)."""
        logger.info(f"📈 Getting upsell suggestions for: {item_name}")
        
        item_lower = item_name.lower()
        suggestions = []
        
        for key, upsell_info in self.upsell_map.items():
            if key in item_lower:
                items = self.api.get_items(search=upsell_info["upsell"], limit=1)
                if items:
                    item = items[0]
                    price_info = self._get_price_info(item["ItemCode"])
                    suggestions.append({
                        "ItemCode": item["ItemCode"],
                        "ItemName": item["ItemName"],
                        "Price": price_info.get("price"),
                        "Currency": price_info.get("currency", "KES"),
                        "MarginIncrease": upsell_info["margin_increase"],
                        "Reason": upsell_info["reason"],
                        "StockStatus": self._check_stock_status(item["ItemCode"]),
                        "Action": "View details",
                        "Type": "upsell"
                    })
                break
        
        if not suggestions:
            suggestions = self._find_premium_alternatives(item_lower, limit)
        
        return suggestions
    
    # =========================================================
    # CUSTOMER RECOMMENDATIONS - FIXED
    # =========================================================
    
    def get_customers_for_item(self, item_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get customers who frequently buy a specific item.
        
        FIXED: Uses get_customer_orders to find customers who purchased the item.
        """
        try:
            logger.info(f"👥 Getting customers for item: {item_code} (limit: {limit})")
            
            # Get item details first
            item = self.api.get_item_by_code(item_code)
            if not item:
                logger.warning(f"Item {item_code} not found")
                return []
            
            # Get all customers
            customers = self.api.get_customers(limit=50)
            
            if not customers:
                return []
            
            # For each customer, check if they bought this item
            customers_who_bought = []
            
            for customer in customers:
                customer_code = customer.get("CardCode")
                if not customer_code:
                    continue
                
                try:
                    # Get customer's orders
                    orders = self.api.get_customer_orders(customer_code=customer_code, limit=20)
                    
                    if not orders:
                        continue
                    
                    # Check if any order contains this item
                    for order in orders:
                        items = order.get("document_lines", []) or order.get("DocumentLines", [])
                        for order_item in items:
                            if order_item.get("ItemCode") == item_code:
                                quantity = float(order_item.get("Quantity", 0) or 0)
                                customers_who_bought.append({
                                    "CardCode": customer_code,
                                    "CardName": customer.get("CardName", customer_code),
                                    "PurchaseQuantity": quantity,
                                    "LastPurchaseDate": order.get("DocDate"),
                                    "RecommendationReason": "Previous buyer - has purchased this product"
                                })
                                break
                        else:
                            continue
                        break
                        
                except Exception as e:
                    logger.debug(f"Error checking customer {customer_code}: {e}")
                    continue
            
            # Sort by purchase quantity
            customers_who_bought.sort(key=lambda x: x.get("PurchaseQuantity", 0), reverse=True)
            
            logger.info(f"✅ Found {len(customers_who_bought)} customers for item {item.get('ItemName', item_code)}")
            return customers_who_bought[:limit]
            
        except Exception as e:
            logger.error(f"Error getting customers for item {item_code}: {e}", exc_info=True)
            return []
    
    def get_similar_customers(self, customer_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get customers similar to the given customer."""
        try:
            logger.info(f"👥 Getting similar customers for: {customer_code}")
            
            # Get the source customer
            customers = self.api.get_customers(limit=100)
            source_customer = None
            
            for customer in customers:
                if customer.get("CardCode") == customer_code:
                    source_customer = customer
                    break
            
            if not source_customer:
                return []
            
            source_group = source_customer.get("GroupCode")
            source_city = source_customer.get("City", "")
            
            # Score customers by similarity
            similar = []
            for customer in customers:
                if customer.get("CardCode") == customer_code:
                    continue
                
                score = 0
                
                if source_group and customer.get("GroupCode") == source_group:
                    score += 3
                
                if source_city and customer.get("City") == source_city:
                    score += 2
                
                if score > 0:
                    similar.append({
                        "customer": customer,
                        "score": score
                    })
            
            similar.sort(key=lambda x: x["score"], reverse=True)
            result = [item["customer"] for item in similar[:limit]]
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting similar customers: {e}")
            return []
    
    # =========================================================
    # SEASONAL & TRENDING
    # =========================================================
    
    def get_seasonal_recommendations(self, month: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Get seasonal product recommendations."""
        if not month:
            month = datetime.now().strftime("%B").lower()
        
        logger.info(f"🌱 Getting seasonal recommendations for: {month}")
        
        recommendations = []
        categories = self.seasonal_products.get(month, ["general crops"])
        
        for category in categories:
            items = self.api.get_items(search=category, limit=3)
            for item in items[:2]:
                if self._is_sellable(item):
                    price_info = self._get_price_info(item["ItemCode"])
                    recommendations.append({
                        "ItemCode": item["ItemCode"],
                        "ItemName": item["ItemName"],
                        "Price": price_info.get("price"),
                        "Currency": price_info.get("currency", "KES"),
                        "Season": month.title(),
                        "Reason": f"Perfect for {month} planting season",
                        "Tip": self._get_seasonal_tip(item["ItemName"], month),
                        "StockStatus": self._check_stock_status(item["ItemCode"]),
                        "Action": "View details",
                        "Type": "seasonal"
                    })
                    if len(recommendations) >= limit:
                        return recommendations
        
        return recommendations[:limit]
    
    def get_trending_products(self, days: int = 30, limit: int = 5) -> List[Dict[str, Any]]:
        """Get trending/popular products."""
        logger.info(f"📊 Getting trending products from last {days} days")
        
        # Try to get top selling items
        try:
            if hasattr(self.api, 'analytics') and self.api.analytics:
                items = self.api.analytics.get_top_selling_items(limit=limit, days=days)
                if items:
                    enhanced = []
                    for item in items:
                        price_info = self._get_price_info(item.get("ItemCode"))
                        enhanced.append({
                            "ItemCode": item.get("ItemCode"),
                            "ItemName": item.get("ItemName"),
                            "Price": price_info.get("price"),
                            "Currency": price_info.get("currency", "KES"),
                            "SalesVolume": item.get("quantity", 0),
                            "Trend": "🔥 Hot" if item.get("quantity", 0) > 100 else "📈 Popular",
                            "Reason": f"{item.get('quantity', 0)} units sold recently",
                            "StockStatus": self._check_stock_status(item.get("ItemCode")),
                            "Action": "Check stock",
                            "Type": "trending"
                        })
                    return enhanced
        except Exception as e:
            logger.debug(f"Could not get trending from analytics: {e}")
        
        return self._get_trending_fallback(limit)
    
    # =========================================================
    # BUNDLE SUGGESTIONS
    # =========================================================
    
    def get_bundle_suggestions(self, items: List[str], limit: int = 3) -> List[Dict[str, Any]]:
        """Suggest items to complete a bundle/purchase."""
        if not items:
            return self.get_recommended_items(limit)
        
        suggestions = []
        all_suggestions = []
        
        for item in items:
            cross_sell = self.get_cross_sell_suggestions(item, limit=2)
            all_suggestions.extend(cross_sell)
        
        seen = set()
        for suggestion in all_suggestions:
            code = suggestion.get("ItemCode")
            if code and code not in seen and code not in items:
                seen.add(code)
                suggestion["BundleScore"] = len([s for s in all_suggestions if s.get("ItemCode") == code])
                suggestions.append(suggestion)
        
        suggestions.sort(key=lambda x: x.get("BundleScore", 0), reverse=True)
        return suggestions[:limit]
    
    def clear_cache(self):
        """Clear the recommendation cache."""
        self._customers_for_item_cache = {}
        self._frequently_bought_cache = {}
        self._similar_customers_cache = {}
        logger.info("🧹 Recommendation cache cleared")
    
    # =========================================================
    # HELPER METHODS
    # =========================================================
    
    def _is_sellable(self, item: Dict[str, Any]) -> bool:
        """Check if an item is sellable."""
        if not item:
            return False
        
        if item.get("SellItem") != "Y":
            return False
        
        group = (item.get("item_group") or {}).get("ItmsGrpNam", "")
        SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL", "INTERNAL", "PACKAGING"}
        
        if group.upper() in SKIP_GROUPS:
            return False
        
        code = item.get("ItemCode", "").upper()
        SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK", "PACK", "BAG", "BOX", "LABEL")
        
        if code.startswith(SKIP_PREFIXES):
            return False
        
        return True
    
    def _get_sellable_items(self, limit: int) -> List[Dict[str, Any]]:
        """Fallback method to get sellable items."""
        items = self.api.get_items(limit=limit * 3)
        
        sellable = []
        for item in items:
            if self._is_sellable(item):
                price_info = self._get_price_info(item.get("ItemCode"))
                item["Price"] = price_info.get("price")
                item["Currency"] = price_info.get("currency", "KES")
                sellable.append(item)
                if len(sellable) >= limit:
                    break
        
        return sellable
    
    def _get_trending_fallback(self, limit: int) -> List[Dict[str, Any]]:
        """Fallback for trending products."""
        items = self.api.get_items(limit=limit * 2)
        enhanced = []
        
        for item in items[:limit]:
            if self._is_sellable(item):
                price_info = self._get_price_info(item.get("ItemCode"))
                enhanced.append({
                    "ItemCode": item.get("ItemCode"),
                    "ItemName": item.get("ItemName"),
                    "Price": price_info.get("price"),
                    "Currency": price_info.get("currency", "KES"),
                    "SalesVolume": 0,
                    "Trend": "📈 Popular",
                    "Reason": "Popular item in our catalog",
                    "StockStatus": self._check_stock_status(item.get("ItemCode")),
                    "Action": "Check stock",
                    "Type": "trending"
                })
        
        return enhanced
    
    def _get_price_info(self, item_code: str) -> Dict:
        """Get price information for an item."""
        if not item_code or not self.pricing:
            return {"price": None, "currency": "KES"}
        
        try:
            price_result = self.pricing.get_price(item_code)
            if price_result and price_result.get("found"):
                return {
                    "price": price_result.get("price"),
                    "currency": price_result.get("currency", "KES"),
                }
        except Exception as e:
            logger.debug(f"Could not get price for {item_code}: {e}")
        
        return {"price": None, "currency": "KES"}
    
    def _check_stock_status(self, item_code: str) -> str:
        """Check if item is in stock."""
        if not item_code:
            return "❌ Unknown"
        
        try:
            inventory = self.api.get_inventory_by_item(item_code)
            if inventory:
                total = sum(float(i.get("OnHand", 0)) for i in inventory if isinstance(i, dict))
                if total > 100:
                    return "✅ In Stock"
                elif total > 10:
                    return "⚠️ Low Stock"
                elif total > 0:
                    return "🔴 Very Low"
            return "❌ Out of Stock"
        except Exception as e:
            logger.debug(f"Could not check stock for {item_code}: {e}")
            return "❌ Unknown"
    
    def _get_seasonal_tip(self, item_name: str, month: str) -> str:
        """Get seasonal planting/care tips."""
        item_lower = item_name.lower() if item_name else ""
        tips = {
            "tomato": "Plant in well-drained soil, stake for support",
            "cabbage": "Space plants 45cm apart, water consistently",
            "maize": "Apply fertilizer at knee-high stage",
            "vegimax": "Apply early morning for best results",
            "fertilizer": "Apply before planting or during active growth",
        }
        
        for key, tip in tips.items():
            if key in item_lower:
                return tip
        
        return f"Best planting time: {month.title()}"
    
    def _get_category_based_cross_sell(self, item_lower: str, limit: int) -> List[Dict]:
        """Fallback method for cross-sell based on category."""
        suggestions = []
        
        if "seed" in item_lower:
            search_terms = ["fertilizer", "tool", "watering"]
        elif "fertilizer" in item_lower:
            search_terms = ["spreader", "test kit", "compost"]
        elif "tool" in item_lower:
            search_terms = ["glove", "sharpener", "set"]
        else:
            search_terms = ["fertilizer", "tool", "seed"]
        
        for term in search_terms[:limit]:
            items = self.api.get_items(search=term, limit=1)
            if items:
                item = items[0]
                price_info = self._get_price_info(item.get("ItemCode"))
                suggestions.append({
                    "ItemCode": item.get("ItemCode"),
                    "ItemName": item.get("ItemName"),
                    "Price": price_info.get("price"),
                    "Currency": price_info.get("currency", "KES"),
                    "Confidence": 0.7,
                    "Reason": f"Commonly purchased with {item_lower}",
                    "StockStatus": self._check_stock_status(item.get("ItemCode")),
                    "Action": "Add to cart",
                    "Type": "cross_sell"
                })
        
        return suggestions
    
    def _find_premium_alternatives(self, item_lower: str, limit: int) -> List[Dict]:
        """Find premium alternatives when no direct upsell mapping exists."""
        suggestions = []
        premium_terms = ["premium", "pro", "professional", "commercial", "hybrid"]
        
        for term in premium_terms[:limit]:
            search_term = f"{term} {item_lower}"
            items = self.api.get_items(search=search_term, limit=1)
            if items:
                item = items[0]
                price_info = self._get_price_info(item.get("ItemCode"))
                suggestions.append({
                    "ItemCode": item.get("ItemCode"),
                    "ItemName": item.get("ItemName"),
                    "Price": price_info.get("price"),
                    "Currency": price_info.get("currency", "KES"),
                    "Reason": "Premium alternative with better features",
                    "StockStatus": self._check_stock_status(item.get("ItemCode")),
                    "Action": "View details",
                    "Type": "upsell"
                })
        
        return suggestions