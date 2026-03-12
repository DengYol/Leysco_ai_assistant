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
"""

import logging
import random
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict, Counter

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
        
        # Seasonal product mapping - can be enhanced with API data
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
        
        # Actual item codes for seasonal recommendations (can be populated from API)
        self.seasonal_item_codes = {
            "january": [],
            "february": [],
            "march": [],
            "april": [],
            "may": [],
            "june": [],
            "july": [],
            "august": [],
            "september": [],
            "october": [],
            "november": [],
            "december": [],
        }
        
        # Upsell opportunities (higher margin alternatives)
        self.upsell_map = {
            "vegimax-10ml": {"upsell": "vegimax-30ml", "margin_increase": 25, "reason": "Better value per ml"},
            "vegimax-30ml": {"upsell": "vegimax-125ml", "margin_increase": 30, "reason": "Economic pack - 20% savings"},
            "vegimax-125ml": {"upsell": "vegimax-250ml", "margin_increase": 35, "reason": "Commercial size - best value"},
            "vegimax": {"upsell": "vegimax-250ml", "margin_increase": 40, "reason": "Professional grade"},
            "basic_fertilizer": {"upsell": "premium_fertilizer", "margin_increase": 40, "reason": "Higher NPK ratio"},
            "standard_seeds": {"upsell": "hybrid_seeds", "margin_increase": 50, "reason": "Better yield, disease resistant"},
            "tomato": {"upsell": "hybrid_tomato", "margin_increase": 35, "reason": "Higher yield per acre"},
            "cabbage": {"upsell": "hybrid_cabbage", "margin_increase": 30, "reason": "Larger heads, disease resistant"},
        }
        
        # Cross-sell associations (what goes well together)
        self.cross_sell_map = {
            "vegimax": [
                {"item": "sprayer", "confidence": 0.95, "reason": "For proper application"},
                {"item": "gloves", "confidence": 0.85, "reason": "Safety gear"},
                {"item": "measuring cylinder", "confidence": 0.80, "reason": "Accurate measurement"},
            ],
            "seeds": [
                {"item": "fertilizer", "confidence": 0.90, "reason": "For optimal growth"},
                {"item": "planting tools", "confidence": 0.85, "reason": "Makes planting easier"},
                {"item": "watering can", "confidence": 0.75, "reason": "Essential for germination"},
            ],
            "fertilizer": [
                {"item": "soil test kit", "confidence": 0.88, "reason": "Know your soil needs"},
                {"item": "spreader", "confidence": 0.82, "reason": "Even application"},
                {"item": "compost", "confidence": 0.78, "reason": "Organic matter boost"},
            ],
            "tools": [
                {"item": "gloves", "confidence": 0.95, "reason": "Protect your hands"},
                {"item": "tool set", "confidence": 0.85, "reason": "Complete your collection"},
                {"item": "sharpener", "confidence": 0.70, "reason": "Maintain your tools"},
            ],
        }
    
    # =========================================================
    # ENHANCED ITEM RECOMMENDATIONS
    # =========================================================
    
    def get_recommended_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top recommended items based on popularity and availability.
        
        Criteria:
        1. High stock turnover (OnHand vs Committed ratio)
        2. Sellable items only
        3. Active stock (not zero inventory)
        4. Exclude packing materials
        """
        try:
            # Get inventory report to analyze stock movement
            inventory = self.api.get_inventory_report(limit=200)
            
            if not inventory:
                # Fallback to regular items
                return self._get_sellable_items(limit)
            
            # Score items based on activity
            scored_items = []
            seen_codes = set()
            
            for record in inventory:
                item_code = record.get("ItemCode")
                if item_code in seen_codes:
                    continue
                seen_codes.add(item_code)
                
                on_hand = float(record.get("CurrentOnHand") or 0)
                committed = float(record.get("CurrentIsCommited") or 0)
                
                # Skip items with no stock
                if on_hand <= 0:
                    continue
                
                # Score: higher committed = more popular
                # But penalize if over-committed (out of stock)
                if on_hand > committed:
                    score = committed  # Good: available and in demand
                else:
                    score = on_hand * 0.5  # Penalized: over-committed
                
                scored_items.append({
                    "ItemCode": item_code,
                    "ItemName": record.get("ItemName"),
                    "score": score,
                    "OnHand": on_hand,
                    "Committed": committed,
                })
            
            # Sort by score and get top items
            scored_items.sort(key=lambda x: x["score"], reverse=True)
            top_items = scored_items[:limit * 2]  # Get extra for filtering
            
            # Fetch full item details and filter
            recommendations = []
            for item in top_items:
                full_item = self.api.get_item_by_code(item["ItemCode"])
                if full_item and self._is_sellable(full_item):
                    # Add price info
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
    
    # =========================================================
    # CROSS-SELL RECOMMENDATIONS
    # =========================================================
    
    def get_cross_sell_suggestions(self, item_name: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Get "Customers who bought X also bought Y" suggestions.
        
        Args:
            item_name: The item to find cross-sells for
            limit: Maximum number of suggestions
        
        Returns:
            List of related items with reasons
        """
        logger.info(f"🔄 Getting cross-sell suggestions for: {item_name}")
        
        item_lower = item_name.lower()
        suggestions = []
        
        # First try to get cross-sell data from API
        try:
            # Get item code first
            items = self.api.get_items(search=item_name, limit=1)
            if items:
                item_code = items[0].get("ItemCode")
                # Try to get cross-sell data from API
                api_suggestions = self.api.get_cross_sell_data(item_code, limit=limit * 2)
                
                if api_suggestions:
                    for api_item in api_suggestions[:limit]:
                        if self._is_sellable(api_item):
                            price_info = self._get_price_info(api_item["ItemCode"])
                            suggestions.append({
                                "ItemCode": api_item["ItemCode"],
                                "ItemName": api_item["ItemName"],
                                "Price": price_info.get("price"),
                                "Currency": price_info.get("currency", "KES"),
                                "Confidence": 0.85,
                                "Reason": "Frequently bought together with your item",
                                "StockStatus": self._check_stock_status(api_item["ItemCode"]),
                                "Action": "Add to cart",
                                "Type": "cross_sell",
                                "Source": "api"
                            })
                    if suggestions:
                        return suggestions
        except Exception as e:
            logger.debug(f"Could not get cross-sell data from API: {e}")
        
        # Fallback to cross-sell map
        for key, related_items in self.cross_sell_map.items():
            if key in item_lower:
                for rel in related_items[:limit]:
                    # Search for the actual item
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
                            "Type": "cross_sell",
                            "Source": "map"
                        })
                break
        
        # If no map match, try category-based
        if not suggestions:
            suggestions = self._get_category_based_cross_sell(item_lower, limit)
        
        return suggestions
    
    # =========================================================
    # UPSELL SUGGESTIONS - FIXED NoneType Error
    # =========================================================
    
    def get_upsell_suggestions(self, item_name: str, limit: int = 2) -> List[Dict[str, Any]]:
        """
        Get upsell suggestions (better/premium alternatives).
        
        Args:
            item_name: The item to find upsells for
            limit: Maximum number of suggestions
        
        Returns:
            List of premium alternatives with reasons
        """
        logger.info(f"📈 Getting upsell suggestions for: {item_name}")
        
        item_lower = item_name.lower()
        suggestions = []
        
        # First try to get upsell data from API
        try:
            items = self.api.get_items(search=item_name, limit=1)
            if items:
                item_code = items[0].get("ItemCode")
                api_suggestions = self.api.get_upsell_data(item_code, limit=limit)
                
                if api_suggestions:
                    for api_item in api_suggestions[:limit]:
                        if self._is_sellable(api_item):
                            price_info = self._get_price_info(api_item["ItemCode"])
                            suggestions.append({
                                "ItemCode": api_item["ItemCode"],
                                "ItemName": api_item["ItemName"],
                                "Price": price_info.get("price"),
                                "Currency": price_info.get("currency", "KES"),
                                "PriceDifference": api_item.get("PriceDifference", 0),
                                "MarginIncrease": 25,  # Default
                                "Reason": "Premium alternative in same category",
                                "Savings": self._calculate_volume_savings(api_item["ItemCode"]),
                                "StockStatus": self._check_stock_status(api_item["ItemCode"]),
                                "Action": "View details",
                                "Type": "upsell",
                                "Source": "api"
                            })
                    if suggestions:
                        return suggestions
        except Exception as e:
            logger.debug(f"Could not get upsell data from API: {e}")
        
        # Fallback to upsell map
        for key, upsell_info in self.upsell_map.items():
            if key in item_lower:
                items = self.api.get_items(search=upsell_info["upsell"], limit=1)
                if items:
                    item = items[0]
                    price_info = self._get_price_info(item["ItemCode"])
                    
                    # Get original item price for comparison
                    original_items = self.api.get_items(search=item_name, limit=1)
                    original_price = None
                    if original_items:
                        orig_price_info = self._get_price_info(original_items[0]["ItemCode"])
                        original_price = orig_price_info.get("price")
                    
                    # FIX: Safely calculate price difference with None checks
                    price_diff = None
                    if price_info.get("price") is not None and original_price is not None:
                        price_diff = price_info.get("price") - original_price
                    
                    suggestions.append({
                        "ItemCode": item["ItemCode"],
                        "ItemName": item["ItemName"],
                        "Price": price_info.get("price"),
                        "Currency": price_info.get("currency", "KES"),
                        "OriginalPrice": original_price,
                        "PriceDifference": price_diff,
                        "MarginIncrease": upsell_info["margin_increase"],
                        "Reason": upsell_info["reason"],
                        "Savings": self._calculate_volume_savings(item["ItemCode"]),
                        "StockStatus": self._check_stock_status(item["ItemCode"]),
                        "Action": "View details",
                        "Type": "upsell",
                        "Source": "map"
                    })
                break
        
        # If no specific upsell found, suggest premium alternatives
        if not suggestions:
            suggestions = self._find_premium_alternatives(item_lower, limit)
        
        return suggestions
    
    # =========================================================
    # SEASONAL RECOMMENDATIONS
    # =========================================================
    
    def get_seasonal_recommendations(self, month: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get seasonal product recommendations based on current month.
        
        Args:
            month: Month name (e.g., "march"), defaults to current month
            limit: Maximum number of recommendations
        
        Returns:
            List of seasonal items with planting tips
        """
        if not month:
            month = datetime.now().strftime("%B").lower()
        
        logger.info(f"🌱 Getting seasonal recommendations for: {month}")
        
        recommendations = []
        
        # First try to get seasonal items from API
        try:
            api_items = self.api.get_seasonal_items(month=month, limit=limit)
            if api_items:
                for item in api_items[:limit]:
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
                            "Type": "seasonal",
                            "Source": "api"
                        })
                if recommendations:
                    return recommendations[:limit]
        except Exception as e:
            logger.debug(f"Could not get seasonal items from API: {e}")
        
        # Fallback to category-based search
        categories = self.seasonal_products.get(month, ["general crops"])
        
        for category in categories:
            items = self.api.get_items(search=category, limit=3)
            for item in items[:2]:  # Take top 2 from each category
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
                        "Type": "seasonal",
                        "Source": "category"
                    })
                    if len(recommendations) >= limit:
                        return recommendations
        
        return recommendations[:limit]
    
    # =========================================================
    # TRENDING PRODUCTS
    # =========================================================
    
    def get_trending_products(self, days: int = 30, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get trending/popular products based on sales velocity.
        
        Args:
            days: Number of days to analyze
            limit: Maximum number of products
        
        Returns:
            List of trending products with sales data
        """
        logger.info(f"📊 Getting trending products from last {days} days")
        
        trending = self.api.get_top_selling_items(limit=limit * 2, days=days)
        
        enhanced = []
        for item in trending[:limit]:
            if self._is_sellable(item):
                price_info = self._get_price_info(item["ItemCode"])
                enhanced.append({
                    "ItemCode": item["ItemCode"],
                    "ItemName": item["ItemName"],
                    "Price": price_info.get("price"),
                    "Currency": price_info.get("currency", "KES"),
                    "SalesVolume": item.get("TotalQty", 0),
                    "Trend": "🔥 Hot" if item.get("TotalQty", 0) > 100 else "📈 Popular",
                    "Reason": f"{item.get('TotalQty', 0)} units sold in last {days} days",
                    "StockStatus": self._check_stock_status(item["ItemCode"]),
                    "Action": "Check stock",
                    "Type": "trending",
                    "Source": "api"
                })
        
        # If no trending items, use fallback
        if not enhanced:
            enhanced = self._get_trending_fallback(limit)
        
        return enhanced
    
    # =========================================================
    # ENHANCED CUSTOMER RECOMMENDATIONS
    # =========================================================
    
    def get_items_for_customer(self, customer_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Recommend items for a specific customer based on:
        1. Their previous purchases
        2. Items their customer segment buys
        3. Popular items they haven't bought
        """
        try:
            # Get customer's order history
            purchase_history = self.api.get_customer_purchase_history(customer_code=customer_code, limit=50)
            
            if not purchase_history:
                # No history, return popular items
                return self.get_recommended_items(limit)
            
            # Get items they've bought
            purchased_items = set()
            for order in purchase_history:
                # Extract item codes from order lines if available
                lines = order.get("DocumentLines", [])
                for line in lines:
                    item_code = line.get("ItemCode")
                    if item_code:
                        purchased_items.add(item_code)
            
            # Get popular items in their categories
            popular = self.get_recommended_items(limit * 2)
            
            # Filter out items they've already bought and add personalization
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
    
    def get_related_items(self, item_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get items related to a specific item.
        
        Criteria:
        1. Same item group
        2. Similar price range
        3. Frequently bought together (if order data available)
        """
        try:
            # Get the source item
            source_item = self.api.get_item_by_code(item_code)
            if not source_item:
                return []
            
            source_group = (source_item.get("item_group") or {}).get("ItmsGrpNam", "")
            
            # Get items in same group
            all_items = self.api.get_items(limit=100)
            
            related = []
            for item in all_items:
                if item.get("ItemCode") == item_code:
                    continue  # Skip the source item itself
                
                item_group = (item.get("item_group") or {}).get("ItmsGrpNam", "")
                
                if item_group == source_group and self._is_sellable(item):
                    price_info = self._get_price_info(item["ItemCode"])
                    item["Price"] = price_info.get("price")
                    item["Currency"] = price_info.get("currency", "KES")
                    item["Reason"] = f"Same category as your item"
                    related.append(item)
                    if len(related) >= limit:
                        break
            
            return related
            
        except Exception as e:
            logger.error(f"Error getting related items for {item_code}: {e}")
            return []
    
    # =========================================================
    # SMART BUNDLE SUGGESTIONS
    # =========================================================
    
    def get_bundle_suggestions(self, items: List[str], limit: int = 3) -> List[Dict[str, Any]]:
        """
        Suggest items to complete a bundle/purchase.
        
        Args:
            items: List of items already in cart
            limit: Maximum number of suggestions
        
        Returns:
            List of complementary items
        """
        if not items:
            return self.get_recommended_items(limit)
        
        # Analyze what's missing from common bundles
        suggestions = []
        all_suggestions = []
        
        for item in items:
            cross_sell = self.get_cross_sell_suggestions(item, limit=2)
            all_suggestions.extend(cross_sell)
        
        # Deduplicate and score
        seen = set()
        for suggestion in all_suggestions:
            code = suggestion["ItemCode"]
            if code not in seen and code not in items:
                seen.add(code)
                suggestion["BundleScore"] = len([s for s in all_suggestions if s["ItemCode"] == code])
                suggestions.append(suggestion)
        
        # Sort by bundle score
        suggestions.sort(key=lambda x: x.get("BundleScore", 0), reverse=True)
        
        return suggestions[:limit]
    
    # =========================================================
    # NEW: RECOMMENDED CUSTOMERS METHODS
    # =========================================================
    
    def get_recommended_customers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top recommended customers based on purchase frequency and value.
        
        Args:
            limit: Maximum number of customers to return
        
        Returns:
            List of recommended customers
        """
        try:
            logger.info(f"👥 Getting recommended customers (limit: {limit})")
            
            # Get all customers
            customers = self.api.get_customers(limit=100)
            
            if not customers:
                return []
            
            # Score customers based on available data
            scored_customers = []
            for customer in customers[:limit * 2]:
                # Basic scoring - can be enhanced with RFM data when available
                score = 1.0
                
                # Try to get order count
                try:
                    orders = self.api.get_orders(customer_code=customer.get("CardCode"), limit=1)
                    if orders and isinstance(orders, dict):
                        order_data = orders.get("ResponseData", [])
                        if order_data:
                            score += len(order_data) * 0.1
                except:
                    pass
                
                scored_customers.append({
                    "customer": customer,
                    "score": score
                })
            
            # Sort by score and return top customers
            scored_customers.sort(key=lambda x: x["score"], reverse=True)
            
            return [item["customer"] for item in scored_customers[:limit]]
            
        except Exception as e:
            logger.error(f"Error getting recommended customers: {e}")
            return []

    def get_customers_for_item(self, item_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get customers who frequently buy a specific item.
        
        Args:
            item_code: The item code to find customers for
            limit: Maximum number of customers to return
        
        Returns:
            List of customers who buy this item
        """
        try:
            logger.info(f"👥 Getting customers for item: {item_code} (limit: {limit})")
            
            # This would ideally query order history
            # For now, return top customers as fallback
            return self.get_recommended_customers(limit)
            
        except Exception as e:
            logger.error(f"Error getting customers for item {item_code}: {e}")
            return []
    
    def get_similar_customers(self, customer_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get customers similar to the given customer.
        
        Args:
            customer_code: The customer code to find similar customers for
            limit: Maximum number of customers to return
        
        Returns:
            List of similar customers
        """
        try:
            logger.info(f"👥 Getting similar customers for: {customer_code} (limit: {limit})")
            
            # Get the source customer
            source_customer = self.api.get_customer_by_code(customer_code)
            if not source_customer:
                return []
            
            source_territory = (source_customer.get("territory") or {}).get("descript", "")
            
            # Get all customers
            all_customers = self.api.get_customers(limit=100)
            
            # Score customers by similarity
            similar = []
            for customer in all_customers:
                if customer.get("CardCode") == customer_code:
                    continue  # Skip source customer
                
                score = 0
                
                # Same territory boosts score
                territory = (customer.get("territory") or {}).get("descript", "")
                if territory and territory == source_territory:
                    score += 5
                
                # Same group boosts score
                if customer.get("GroupCode") and customer.get("GroupCode") == source_customer.get("GroupCode"):
                    score += 3
                
                similar.append({
                    "customer": customer,
                    "score": score
                })
            
            # Sort by score and return top customers
            similar.sort(key=lambda x: x["score"], reverse=True)
            
            return [item["customer"] for item in similar[:limit]]
            
        except Exception as e:
            logger.error(f"Error getting similar customers: {e}")
            return []

    # =========================================================
    # HELPER METHODS
    # =========================================================
    
    def _is_sellable(self, item: Dict[str, Any]) -> bool:
        """Check if an item is sellable (not packing material, etc.)"""
        if item.get("SellItem") != "Y":
            return False
        
        group = (item.get("item_group") or {}).get("ItmsGrpNam", "").upper()
        SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL", "INTERNAL"}
        
        if group in SKIP_GROUPS:
            return False
        
        code = item.get("ItemCode", "").upper()
        SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA")
        
        if code.startswith(SKIP_PREFIXES):
            return False
        
        return True
    
    def _get_sellable_items(self, limit: int) -> List[Dict[str, Any]]:
        """Fallback method to get sellable items"""
        items = self.api.get_items(limit=limit * 3)
        
        sellable = []
        for item in items:
            if self._is_sellable(item):
                price_info = self._get_price_info(item["ItemCode"])
                item["Price"] = price_info.get("price")
                item["Currency"] = price_info.get("currency", "KES")
                sellable.append(item)
                if len(sellable) >= limit:
                    break
        
        return sellable
    
    def _get_trending_fallback(self, limit: int) -> List[Dict[str, Any]]:
        """Fallback for trending products when API fails"""
        items = self.api.get_items(limit=limit * 2)
        enhanced = []
        
        for item in items[:limit]:
            if self._is_sellable(item):
                price_info = self._get_price_info(item["ItemCode"])
                enhanced.append({
                    "ItemCode": item["ItemCode"],
                    "ItemName": item["ItemName"],
                    "Price": price_info.get("price"),
                    "Currency": price_info.get("currency", "KES"),
                    "SalesVolume": 0,
                    "Trend": "📈 Popular",
                    "Reason": "Popular item in our catalog",
                    "StockStatus": self._check_stock_status(item["ItemCode"]),
                    "Action": "Check stock",
                    "Type": "trending",
                    "Source": "fallback"
                })
        
        return enhanced
    
    def _get_price_info(self, item_code: str) -> Dict:
        """Get price information for an item"""
        if not self.pricing:
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
        """Check if item is in stock"""
        inventory = self.api.get_inventory_by_item(item_code)
        if inventory:
            total = sum(float(i.get("OnHand", 0)) for i in inventory)
            if total > 100:
                return "✅ In Stock"
            elif total > 10:
                return "⚠️ Low Stock"
            elif total > 0:
                return "🔴 Very Low"
        return "❌ Out of Stock"
    
    def _calculate_volume_savings(self, item_code: str) -> str:
        """Calculate savings for volume purchase"""
        # This would check bulk pricing tiers
        return "10% off on 10+ units"
    
    def _get_seasonal_tip(self, item_name: str, month: str) -> str:
        """Get seasonal planting/care tips"""
        tips = {
            "tomato": "Plant in well-drained soil, stake for support",
            "cabbage": "Space plants 45cm apart, water consistently",
            "maize": "Apply fertilizer at knee-high stage",
            "vegimax": "Apply early morning for best results",
            "fertilizer": "Apply before planting or during active growth",
            "onion": "Plant in raised beds, keep soil moist",
            "carrot": "Thin seedlings to 5cm apart",
        }
        
        for key, tip in tips.items():
            if key in item_name.lower():
                return tip
        
        return f"Best planting time: {month.title()}"
    
    def _get_category_based_cross_sell(self, item_lower: str, limit: int) -> List[Dict]:
        """Fallback method for cross-sell based on category"""
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
                price_info = self._get_price_info(item["ItemCode"])
                suggestions.append({
                    "ItemCode": item["ItemCode"],
                    "ItemName": item["ItemName"],
                    "Price": price_info.get("price"),
                    "Currency": price_info.get("currency", "KES"),
                    "Confidence": 0.7,
                    "Reason": f"Commonly purchased with {item_lower}",
                    "StockStatus": self._check_stock_status(item["ItemCode"]),
                    "Action": "Add to cart",
                    "Type": "cross_sell",
                    "Source": "category"
                })
        
        return suggestions
    
    def _find_premium_alternatives(self, item_lower: str, limit: int) -> List[Dict]:
        """Find premium alternatives when no direct upsell mapping exists"""
        suggestions = []
        
        # Try to find premium versions by adding "premium", "pro", etc. to search
        premium_terms = ["premium", "pro", "professional", "commercial", "hybrid"]
        
        for term in premium_terms[:limit]:
            search_term = f"{term} {item_lower}"
            items = self.api.get_items(search=search_term, limit=1)
            if items:
                item = items[0]
                price_info = self._get_price_info(item["ItemCode"])
                suggestions.append({
                    "ItemCode": item["ItemCode"],
                    "ItemName": item["ItemName"],
                    "Price": price_info.get("price"),
                    "Currency": price_info.get("currency", "KES"),
                    "Reason": "Premium alternative with better features",
                    "StockStatus": self._check_stock_status(item["ItemCode"]),
                    "Action": "View details",
                    "Type": "upsell",
                    "Source": "premium_search"
                })
        
        return suggestions
    
    def refresh_patterns(self):
        """Refresh purchase pattern cache (would analyze recent orders in production)"""
        logger.info("🔄 Refreshing recommendation patterns")
        self._frequently_bought_cache = {}
        self._last_cache_refresh = datetime.now()