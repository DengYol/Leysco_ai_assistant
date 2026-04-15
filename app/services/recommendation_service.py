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
        self._customers_for_item_cache = {}  # Cache for customers_by_item results
        self._similar_customers_cache = {}   # Cache for similar customers
        self._cache_ttl = timedelta(minutes=5)  # Cache timeout
        
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
    # ENHANCED: RECOMMENDED CUSTOMERS METHODS (OPTIMIZED)
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

    def get_customers_for_item(self, item_code: str, limit: int = 10, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get customers who frequently buy a specific item.
        Queries order history to find actual customers who purchased this item.
        
        Args:
            item_code: The item code to find customers for
            limit: Maximum number of customers to return
            use_cache: Whether to use cached results (default True)
        
        Returns:
            List of customers who buy this item with purchase statistics
        """
        try:
            logger.info(f"👥 Getting customers for item: {item_code} (limit: {limit})")
            
            # Check cache first
            if use_cache and item_code in self._customers_for_item_cache:
                cache_entry = self._customers_for_item_cache[item_code]
                if datetime.now() - cache_entry["timestamp"] < self._cache_ttl:
                    logger.info(f"📦 Returning cached customers for item {item_code} ({len(cache_entry['customers'])} customers)")
                    return cache_entry["customers"][:limit]
            
            # Get all customers first
            all_customers = self.api.get_all_customers(limit=2000)
            
            if not all_customers:
                logger.warning("No customers found in system")
                return []
            
            # Track customers who bought this item
            customers_with_purchases = []
            processed_count = 0
            
            # Process customers in batches to avoid overwhelming the API
            batch_size = 50
            total_batches = (len(all_customers) + batch_size - 1) // batch_size
            
            for i in range(0, len(all_customers), batch_size):
                batch = all_customers[i:i+batch_size]
                processed_count += len(batch)
                
                for customer in batch:
                    customer_code = customer.get("CardCode")
                    customer_name = customer.get("CardName")
                    
                    if not customer_code:
                        continue
                    
                    try:
                        # Get customer's order history
                        orders_result = self.api.get_orders(customer_code=customer_code, limit=20)
                        
                        # Extract the actual orders from the response
                        if isinstance(orders_result, dict):
                            orders = orders_result.get("ResponseData", [])
                        else:
                            orders = orders_result if isinstance(orders_result, list) else []
                        
                        if not orders:
                            continue
                        
                        # Check if any order contains this item
                        total_quantity = 0
                        last_purchase_date = None
                        order_count = 0
                        
                        for order in orders:
                            document_lines = order.get("DocumentLines", [])
                            
                            for line in document_lines:
                                line_item_code = line.get("ItemCode")
                                if line_item_code == item_code:
                                    quantity = float(line.get("Quantity", 0))
                                    total_quantity += quantity
                                    order_count += 1
                                    
                                    # Track last purchase date
                                    order_date = order.get("DocDate")
                                    if order_date and (not last_purchase_date or order_date > last_purchase_date):
                                        last_purchase_date = order_date
                        
                        if total_quantity > 0:
                            # Get full customer details
                            full_customer = self.api.get_customer_by_code(customer_code)
                            if full_customer:
                                full_customer["PurchaseQuantity"] = total_quantity
                                full_customer["LastPurchaseDate"] = last_purchase_date
                                full_customer["OrderCount"] = order_count
                                full_customer["ItemCode"] = item_code
                                customers_with_purchases.append(full_customer)
                                
                    except Exception as e:
                        logger.debug(f"Error checking customer {customer_code}: {e}")
                        continue
                
                # Log progress every 5 batches
                if (i // batch_size) % 5 == 0:
                    logger.info(f"Processed {processed_count}/{len(all_customers)} customers, found {len(customers_with_purchases)} so far")
            
            # Sort by purchase quantity (highest first)
            customers_with_purchases.sort(
                key=lambda x: x.get("PurchaseQuantity", 0), 
                reverse=True
            )
            
            logger.info(f"✅ Found {len(customers_with_purchases)} customers who bought {item_code}")
            
            # Add recommendation reasons based on purchase behavior
            for i, customer in enumerate(customers_with_purchases):
                qty = customer.get("PurchaseQuantity", 0)
                order_count = customer.get("OrderCount", 0)
                
                if i == 0 and qty > 10:
                    customer["RecommendationReason"] = "🏆 Top buyer - highest volume customer"
                    customer["RecommendationPriority"] = "high"
                elif qty > 5:
                    customer["RecommendationReason"] = "⭐ Regular purchaser - frequent buyer"
                    customer["RecommendationPriority"] = "high"
                elif order_count > 1:
                    customer["RecommendationReason"] = "📦 Repeat customer - bought multiple times"
                    customer["RecommendationPriority"] = "medium"
                else:
                    customer["RecommendationReason"] = "✓ Previous buyer - has purchased this product"
                    customer["RecommendationPriority"] = "low"
                
                # Add human-readable date
                if customer.get("LastPurchaseDate"):
                    try:
                        last_date = datetime.strptime(customer["LastPurchaseDate"][:10], "%Y-%m-%d")
                        days_ago = (datetime.now() - last_date).days
                        customer["DaysSinceLastPurchase"] = days_ago
                        if days_ago <= 30:
                            customer["RecommendationReason"] += " (recent purchase)"
                    except:
                        pass
            
            # Cache the results
            if use_cache:
                self._customers_for_item_cache[item_code] = {
                    "customers": customers_with_purchases,
                    "timestamp": datetime.now()
                }
                logger.info(f"💾 Cached {len(customers_with_purchases)} customers for item {item_code}")
            
            return customers_with_purchases[:limit]
            
        except Exception as e:
            logger.error(f"Error getting customers for item {item_code}: {e}", exc_info=True)
            # Fallback to recommended customers if something goes wrong
            logger.info("Falling back to recommended customers")
            return self.get_recommended_customers(limit)
    
    def get_customers_for_item_fast(self, item_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Faster version of get_customers_for_item using sales analysis data.
        More efficient for large customer bases.
        
        Args:
            item_code: The item code to find customers for
            limit: Maximum number of customers to return
        
        Returns:
            List of customers who buy this item with purchase statistics
        """
        try:
            logger.info(f"🚀 Fast lookup: Getting customers for item {item_code}")
            
            # Get sales analysis for the last 6 months
            end_date = datetime.now()
            start_date = end_date - timedelta(days=180)
            
            sales_data = self.api.get_sales_analysis(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                limit=500
            )
            
            if not sales_data:
                logger.warning("No sales data available, falling back to standard method")
                return self.get_customers_for_item(item_code, limit, use_cache=False)
            
            # Filter for our item and aggregate by customer
            customer_purchases = {}
            
            for sale in sales_data:
                sale_item_code = sale.get("ItemCode")
                if sale_item_code == item_code:
                    customer_code = sale.get("CardCode")
                    customer_name = sale.get("CardName")
                    quantity = float(sale.get("Quantity", 0))
                    
                    if customer_code:
                        if customer_code not in customer_purchases:
                            customer_purchases[customer_code] = {
                                "customer_code": customer_code,
                                "customer_name": customer_name,
                                "total_quantity": 0,
                                "last_purchase": sale.get("DocDate"),
                                "order_count": 0
                            }
                        customer_purchases[customer_code]["total_quantity"] += quantity
                        customer_purchases[customer_code]["order_count"] += 1
                        
                        # Update last purchase date if newer
                        sale_date = sale.get("DocDate")
                        if sale_date and (not customer_purchases[customer_code]["last_purchase"] or 
                                          sale_date > customer_purchases[customer_code]["last_purchase"]):
                            customer_purchases[customer_code]["last_purchase"] = sale_date
            
            if not customer_purchases:
                logger.info(f"No customers found for item {item_code} in sales analysis")
                return self.get_customers_for_item(item_code, limit, use_cache=False)
            
            # Convert to list and get full customer details
            customers_list = []
            for cust_code, cust_data in customer_purchases.items():
                # Try to get full customer details
                customer = self.api.get_customer_by_code(cust_code)
                if customer:
                    customer["PurchaseQuantity"] = cust_data["total_quantity"]
                    customer["LastPurchaseDate"] = cust_data["last_purchase"]
                    customer["OrderCount"] = cust_data["order_count"]
                    customers_list.append(customer)
                else:
                    # Fallback to basic info
                    customers_list.append({
                        "CardCode": cust_code,
                        "CardName": cust_data["customer_name"] or cust_code,
                        "PurchaseQuantity": cust_data["total_quantity"],
                        "LastPurchaseDate": cust_data["last_purchase"],
                        "OrderCount": cust_data["order_count"]
                    })
            
            # Sort by purchase quantity
            customers_list.sort(key=lambda x: x.get("PurchaseQuantity", 0), reverse=True)
            
            # Add recommendation reasons
            for i, customer in enumerate(customers_list):
                qty = customer.get("PurchaseQuantity", 0)
                if i == 0 and qty > 10:
                    customer["RecommendationReason"] = "🏆 Top buyer - highest volume customer"
                elif qty > 5:
                    customer["RecommendationReason"] = "⭐ Regular purchaser - frequent buyer"
                else:
                    customer["RecommendationReason"] = "✓ Previous buyer - has purchased this product"
            
            logger.info(f"✅ Fast lookup found {len(customers_list)} customers for {item_code}")
            return customers_list[:limit]
            
        except Exception as e:
            logger.error(f"Error in fast customer lookup: {e}")
            return self.get_customers_for_item(item_code, limit, use_cache=False)
    
    def get_similar_customers(self, customer_code: str, limit: int = 10, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get customers similar to the given customer.
        
        Args:
            customer_code: The customer code to find similar customers for
            limit: Maximum number of customers to return
            use_cache: Whether to use cached results
        
        Returns:
            List of similar customers
        """
        try:
            logger.info(f"👥 Getting similar customers for: {customer_code} (limit: {limit})")
            
            # Check cache
            if use_cache and customer_code in self._similar_customers_cache:
                cache_entry = self._similar_customers_cache[customer_code]
                if datetime.now() - cache_entry["timestamp"] < self._cache_ttl:
                    logger.info(f"📦 Returning cached similar customers for {customer_code}")
                    return cache_entry["customers"][:limit]
            
            # Get the source customer
            source_customer = self.api.get_customer_by_code(customer_code)
            if not source_customer:
                return []
            
            source_territory = (source_customer.get("territory") or {}).get("descript", "")
            source_group = source_customer.get("GroupCode")
            
            # Get all customers
            all_customers = self.api.get_customers(limit=200)
            
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
                if source_group and customer.get("GroupCode") == source_group:
                    score += 3
                
                # Same city/region
                city = customer.get("City", "")
                source_city = source_customer.get("City", "")
                if city and city == source_city:
                    score += 2
                
                similar.append({
                    "customer": customer,
                    "score": score
                })
            
            # Sort by score and return top customers
            similar.sort(key=lambda x: x["score"], reverse=True)
            result = [item["customer"] for item in similar[:limit]]
            
            # Cache the result
            if use_cache:
                self._similar_customers_cache[customer_code] = {
                    "customers": result,
                    "timestamp": datetime.now()
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting similar customers: {e}")
            return []
    
    def get_customer_purchase_summary(self, customer_code: str) -> Dict[str, Any]:
        """
        Get a summary of a customer's purchase behavior.
        
        Args:
            customer_code: The customer code to analyze
        
        Returns:
            Dictionary with purchase summary statistics
        """
        try:
            logger.info(f"📊 Getting purchase summary for customer: {customer_code}")
            
            orders_result = self.api.get_orders(customer_code=customer_code, limit=100)
            
            if isinstance(orders_result, dict):
                orders = orders_result.get("ResponseData", [])
            else:
                orders = orders_result if isinstance(orders_result, list) else []
            
            if not orders:
                return {
                    "customer_code": customer_code,
                    "total_orders": 0,
                    "total_value": 0,
                    "unique_items": 0,
                    "last_order_date": None,
                    "first_order_date": None,
                    "average_order_value": 0
                }
            
            total_value = 0
            unique_items = set()
            last_order_date = None
            first_order_date = None
            product_counts = defaultdict(int)
            
            for order in orders:
                doc_total = float(order.get("DocTotal", 0))
                total_value += doc_total
                
                doc_date = order.get("DocDate")
                if doc_date:
                    if not first_order_date or doc_date < first_order_date:
                        first_order_date = doc_date
                    if not last_order_date or doc_date > last_order_date:
                        last_order_date = doc_date
                
                lines = order.get("DocumentLines", [])
                for line in lines:
                    item_code = line.get("ItemCode")
                    if item_code:
                        unique_items.add(item_code)
                        product_counts[item_code] += float(line.get("Quantity", 0))
            
            # Get top products
            top_products = sorted(product_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            
            return {
                "customer_code": customer_code,
                "total_orders": len(orders),
                "total_value": round(total_value, 2),
                "unique_items": len(unique_items),
                "last_order_date": last_order_date,
                "first_order_date": first_order_date,
                "average_order_value": round(total_value / len(orders), 2) if orders else 0,
                "top_products": [{"code": code, "quantity": qty} for code, qty in top_products]
            }
            
        except Exception as e:
            logger.error(f"Error getting purchase summary for {customer_code}: {e}")
            return {}
    
    def clear_cache(self):
        """Clear the recommendation cache"""
        self._customers_for_item_cache = {}
        self._frequently_bought_cache = {}
        self._similar_customers_cache = {}
        logger.info("🧹 Recommendation cache cleared")

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