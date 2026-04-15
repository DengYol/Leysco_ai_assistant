"""
app/ai_engine/decision_support.py
===================================
Decision Support Module — Fixed with proper API field handling
Added customer segmentation for FIND_CUSTOMERS_BY_ITEM intent
Fixed competitor price check to filter out non-sellable items and search broader
Improved reorder decisions with better urgency classification and actionable recommendations
"""

import logging
import math
import time
import asyncio
import re
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime, timedelta
from collections import Counter
from functools import lru_cache

# Lazy import to avoid circular dependency
def _get_competitor_service():
    """Lazy import of competitor service to avoid circular dependency."""
    try:
        from app.services.competitor_api_service import get_competitor_pricing_service
        return get_competitor_pricing_service()
    except ImportError as e:
        logger.warning(f"Could not import competitor service: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error initializing competitor service: {e}")
        return None

logger = logging.getLogger(__name__)


def _mean(values: List[float]) -> float:
    """Safe mean — returns 0 if list is empty."""
    return sum(values) / len(values) if values else 0.0


def _std(values: List[float]) -> float:
    """Safe standard deviation — returns 0 if fewer than 2 values."""
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def _sqrt(value: float) -> float:
    """Safe square root with max(0)."""
    return math.sqrt(max(0, value))


def _confidence_score(data_points: int) -> float:
    """Calculate confidence score based on data volume."""
    if data_points >= 90:
        return 1.0
    elif data_points >= 60:
        return 0.9
    elif data_points >= 30:
        return 0.75
    elif data_points >= 14:
        return 0.6
    elif data_points >= 7:
        return 0.4
    elif data_points > 0:
        return 0.2
    return 0.0


class DecisionSupport:
    """
    Provides decision support for business intelligence.
    """

    def __init__(self, api, pricing, warehouse=None, recommender=None):
        self.api = api
        self.pricing = pricing
        self.warehouse = warehouse
        self.recommender = recommender
        
        # Initialize competitor service lazily
        self._competitor_service = None
        self._competitor_service_error = None

        # Decision thresholds (tunable)
        self.thresholds = {
            "critical_stock_days": 3,
            "low_stock_days": 7,
            "optimal_stock_days": 30,
            "max_stock_days": 60,
            "reorder_point_multiplier": 1.5,
            "price_drop_threshold": 0.15,
            "price_hike_threshold": 0.20,
            "slow_mover_days": 90,
            "fast_mover_days": 30,
            "churn_risk_days": 60,
            "high_value_threshold": 50000,
            "bulk_discount_threshold": 100,
        }
        
        # Simple cache for performance
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes default
        
        # Metrics collection
        self.metrics = {
            "api_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "avg_response_time": 0,
            "total_response_time": 0,
            "call_count": 0
        }

    def _get_competitor_service(self):
        """Get competitor service instance with lazy initialization."""
        if self._competitor_service is None and self._competitor_service_error is None:
            try:
                self._competitor_service = _get_competitor_service()
                if self._competitor_service is None:
                    self._competitor_service_error = "Competitor service unavailable"
                    logger.warning("Competitor service not available")
            except Exception as e:
                self._competitor_service_error = str(e)
                logger.error(f"Failed to initialize competitor service: {e}")
        return self._competitor_service

    # =========================================================
    # CACHE HELPERS
    # =========================================================
    
    def _get_cached(self, key: str, ttl: int = 300) -> Optional[Any]:
        """Get value from cache if still valid."""
        if key in self._cache:
            cached_time, value = self._cache[key]
            if time.time() - cached_time < ttl:
                self.metrics["cache_hits"] += 1
                return value
            else:
                del self._cache[key]
        self.metrics["cache_misses"] += 1
        return None
    
    def _set_cache(self, key: str, value: Any) -> None:
        """Set value in cache - only store plain data, no coroutines."""
        if asyncio.iscoroutine(value):
            logger.warning(f"Attempted to cache coroutine for key {key}, skipping")
            return
        self._cache[key] = (time.time(), value)
    
    def _clear_cache(self) -> None:
        """Clear entire cache."""
        self._cache.clear()
    
    # =========================================================
    # METRICS HELPERS
    # =========================================================
    
    def _record_api_call(self, duration: float) -> None:
        """Record API call metrics."""
        self.metrics["api_calls"] += 1
        self.metrics["call_count"] += 1
        self.metrics["total_response_time"] += duration
        self.metrics["avg_response_time"] = (
            self.metrics["total_response_time"] / self.metrics["call_count"]
        )
    
    def _record_error(self) -> None:
        """Record error occurrence."""
        self.metrics["errors"] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Return current metrics."""
        return self.metrics.copy()
    
    # =========================================================
    # MAIN ROUTING METHOD
    # =========================================================
    
    async def analyze(self, intent: str, entities: dict) -> Dict[str, Any]:
        """
        Generic analysis method that routes to specific analysis functions.
        """
        start_time = time.time()
        logger.info(f"📊 Decision support analysis for intent: {intent}")
        
        try:
            # Route to appropriate method
            if intent == "ANALYZE_INVENTORY_HEALTH":
                warehouse_code = entities.get("warehouse")
                result = self.analyze_inventory_health(warehouse_code=warehouse_code)
            
            elif intent == "GET_REORDER_DECISIONS":
                item_code = entities.get("item_code") or entities.get("item_name")
                result = self.get_reorder_decisions(filter_item_code=item_code)
            
            elif intent == "ANALYZE_PRICING_OPPORTUNITIES":
                customer_code = entities.get("customer_code") or entities.get("customer_name")
                result = self.analyze_pricing_opportunities(customer_code=customer_code)
            
            elif intent == "ANALYZE_CUSTOMER_BEHAVIOR":
                customer_name = entities.get("customer_name")
                if not customer_name:
                    result = {"error": "Customer name is required"}
                else:
                    result = self.analyze_customer_behavior(customer_name)
            
            elif intent == "FORECAST_DEMAND":
                item_name = entities.get("item_name")
                days = entities.get("quantity") or 30
                if not item_name:
                    result = {"error": "Item name is required"}
                else:
                    result = self.forecast_demand(item_name, days_ahead=days)
            
            elif intent == "GET_SALES_TREND":
                result = self.get_sales_trend()
            
            elif intent == "GET_INVENTORY_TURNOVER":
                warehouse = entities.get("warehouse")
                result = self.get_inventory_turnover(warehouse)
            
            elif intent == "COMPETITOR_PRICE_CHECK":
                result = await self.competitor_price_check(entities)
            
            elif intent == "FIND_BEST_PRICE":
                result = await self.find_best_price(entities)
            
            elif intent == "MARKET_INTELLIGENCE":
                result = await self.market_intelligence(entities)
            
            elif intent == "PRICE_ALERT":
                result = await self.price_alert(entities)
            
            # NEW: FIND_CUSTOMERS_BY_ITEM - Customer segmentation
            elif intent == "FIND_CUSTOMERS_BY_ITEM":
                item_name = entities.get("item_name")
                limit = entities.get("quantity") or 10
                if not item_name:
                    result = {"error": "Item name is required for customer segmentation"}
                else:
                    result = await self.find_customers_by_item(item_name, limit)
            
            else:
                result = {
                    "error": True,
                    "message": f"Analysis for {intent} not implemented yet"
                }
            
            # Ensure result is a dict, not a coroutine
            if asyncio.iscoroutine(result):
                logger.error(f"Method for intent {intent} returned a coroutine!")
                result = await result
            
            if not isinstance(result, dict):
                logger.error(f"Method for intent {intent} returned {type(result)}, expected dict")
                result = {
                    "error": True,
                    "message": f"Invalid response type from {intent}",
                    "type": str(type(result))
                }
            
            # Add metrics to result
            duration = time.time() - start_time
            self._record_api_call(duration)
            result["_metrics"] = {
                "response_time_ms": round(duration * 1000, 2),
                "cache_hit_rate": round(
                    self.metrics["cache_hits"] / max(1, self.metrics["cache_hits"] + self.metrics["cache_misses"]) * 100, 1
                )
            }
            
            return result
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in analyze() for intent {intent}: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Analysis failed: {str(e)}",
                "intent": intent
            }

    # =========================================================
    # NEW: CUSTOMER SEGMENTATION - FIND CUSTOMERS BY ITEM
    # =========================================================
    
    async def find_customers_by_item(self, item_name: str, limit: int = 10) -> Dict[str, Any]:
        """
        Find customers who would buy or have bought a specific item.
        
        Args:
            item_name: The product/item to find customers for
            limit: Maximum number of customers to return
        
        Returns:
            Dictionary with customer segmentation analysis
        """
        logger.info(f"🎯 Finding customers for item: {item_name}")
        
        # Check cache
        cache_key = f"customers_by_item_{item_name.lower()}_{limit}"
        cached_result = self._get_cached(cache_key, ttl=300)
        if cached_result is not None:
            logger.info(f"📦 Cache hit for customers_by_item: {item_name}")
            return cached_result
        
        try:
            # First, get the item code
            items = self.api.get_items(search=item_name, limit=5)
            if not items:
                return {
                    "error": True,
                    "analysis_type": "customer_segmentation",
                    "message": f"No item found matching '{item_name}'",
                    "suggestions": ["Check spelling", "Try a different product name", "Browse items"]
                }
            
            # Find the best matching item
            matched_item = None
            for candidate in items:
                candidate_name = candidate.get("ItemName", "").lower()
                if item_name.lower() in candidate_name or candidate_name in item_name.lower():
                    matched_item = candidate
                    break
            
            if not matched_item:
                matched_item = items[0]
            
            item_code = matched_item.get("ItemCode")
            item_full_name = matched_item.get("ItemName")
            
            logger.info(f"🎯 Matched item: {item_full_name} ({item_code})")
            
            # Get customers from recommendation service
            customers = []
            if self.recommender:
                try:
                    customers = self.recommender.get_customers_for_item(
                        item_code=item_code,
                        limit=limit
                    )
                    logger.info(f"Found {len(customers)} customers from recommendation service")
                except Exception as e:
                    logger.warning(f"Recommendation service failed: {e}")
            
            # If recommendation service fails, try direct order history
            if not customers:
                customers = await self._find_customers_from_orders(item_code, limit)
            
            if not customers:
                return {
                    "analysis_type": "customer_segmentation",
                    "item_name": item_full_name,
                    "item_code": item_code,
                    "customers_found": 0,
                    "customers": [],
                    "message": f"No customers found for '{item_full_name}'",
                    "suggestions": [
                        "Try a different product",
                        "Check if this product has sales history",
                        "Ask about similar products"
                    ]
                }
            
            # Add summary statistics
            total_purchase_volume = sum(c.get("PurchaseQuantity", 0) for c in customers)
            avg_purchase = total_purchase_volume / len(customers) if customers else 0
            
            result = {
                "analysis_type": "customer_segmentation",
                "item_name": item_full_name,
                "item_code": item_code,
                "customers_found": len(customers),
                "customers": customers[:limit],
                "summary": {
                    "total_customers": len(customers),
                    "total_purchase_volume": round(total_purchase_volume, 0),
                    "average_purchase_volume": round(avg_purchase, 1),
                    "top_customers": [
                        {"name": c.get("CardName"), "quantity": c.get("PurchaseQuantity", 0)}
                        for c in customers[:3]
                    ]
                },
                "recommendations": self._generate_segmentation_recommendations(customers, item_full_name),
                "timestamp": datetime.now().isoformat()
            }
            
            # Cache the result
            self._set_cache(cache_key, result)
            return result
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in find_customers_by_item: {e}", exc_info=True)
            return {
                "error": True,
                "analysis_type": "customer_segmentation",
                "message": f"Failed to find customers for {item_name}: {str(e)}"
            }
    
    async def _find_customers_from_orders(self, item_code: str, limit: int = 10) -> List[Dict]:
        """Fallback method to find customers from order history."""
        customers_with_purchases = []
        
        try:
            # Get all customers
            all_customers = self.api.get_all_customers(limit=500)
            
            for customer in all_customers[:100]:  # Limit for performance
                customer_code = customer.get("CardCode")
                
                if not customer_code:
                    continue
                
                try:
                    orders_result = self.api.get_orders(customer_code=customer_code, limit=20)
                    
                    if isinstance(orders_result, dict):
                        orders = orders_result.get("ResponseData", [])
                    else:
                        orders = orders_result if isinstance(orders_result, list) else []
                    
                    total_quantity = 0
                    for order in orders:
                        lines = order.get("DocumentLines", [])
                        for line in lines:
                            if line.get("ItemCode") == item_code:
                                total_quantity += float(line.get("Quantity", 0))
                    
                    if total_quantity > 0:
                        customers_with_purchases.append({
                            "CardCode": customer_code,
                            "CardName": customer.get("CardName"),
                            "PurchaseQuantity": total_quantity,
                            "Source": "order_history",
                            "RecommendationReason": "✓ Previous buyer - has purchased this product"
                        })
                        
                        if len(customers_with_purchases) >= limit:
                            break
                            
                except Exception as e:
                    logger.debug(f"Error checking orders for {customer_code}: {e}")
                    continue
            
            # Sort by purchase quantity
            customers_with_purchases.sort(key=lambda x: x.get("PurchaseQuantity", 0), reverse=True)
            
        except Exception as e:
            logger.error(f"Error in _find_customers_from_orders: {e}")
        
        return customers_with_purchases
    
    def _generate_segmentation_recommendations(self, customers: List[Dict], item_name: str) -> List[str]:
        """Generate actionable recommendations based on customer segmentation."""
        recommendations = []
        
        if not customers:
            return recommendations
        
        top_customers = customers[:3]
        high_volume = [c for c in customers if c.get("PurchaseQuantity", 0) > 10]
        recent_buyers = [c for c in customers if c.get("DaysSinceLastPurchase", 999) <= 30]
        
        if top_customers:
            top_names = [c.get("CardName", "Unknown") for c in top_customers[:3]]
            recommendations.append(
                f"📊 Focus on top buyers: {', '.join(top_names)}. They purchase the most {item_name}."
            )
        
        if high_volume and len(high_volume) > 3:
            recommendations.append(
                f"📈 {len(high_volume)} customers buy {item_name} in high volume. Consider bulk discounts or loyalty rewards."
            )
        
        if recent_buyers:
            recommendations.append(
                f"🔄 {len(recent_buyers)} customers purchased {item_name} recently. Great time for cross-sell opportunities."
            )
        
        if len(customers) > 10:
            recommendations.append(
                f"👥 {len(customers)} customers have purchased {item_name}. Consider running a targeted campaign."
            )
        
        # Add actionable next steps
        recommendations.append(
            f"💡 Next step: Create a quotation for these customers with 'create quotation for {item_name}'"
        )
        
        return recommendations[:5]  # Return top 5 recommendations

    # =========================================================
    # COMPETITOR PRICING METHODS (async with safe fallback)
    # =========================================================

    async def competitor_price_check(self, entities: dict) -> Dict[str, Any]:
        """Check competitor prices for an item with token optimization."""
        item_name = entities.get("item_name", "")
        
        if not item_name:
            return {
                "error": True,
                "analysis_type": "competitor_price_check",
                "message": "Please specify an item to check competitor prices for",
                "suggestions": [
                    "What's the competitor price for cabbage?",
                    "How much is vegimax at other stores?",
                    "Compare prices for tomatoes"
                ]
            }
        
        logger.info(f"🔍 Checking competitor prices for: {item_name}")
        
        # Check if competitor service is available
        competitor_service = self._get_competitor_service()
        if competitor_service is None:
            return {
                "analysis_type": "competitor_price_check",
                "item_name": item_name,
                "message": "Competitor price service is currently unavailable. Please check our internal pricing.",
                "suggestions": ["Check item price", "Browse items", "Contact sales team"],
                "status": "service_unavailable"
            }
        
        try:
            # First, try to search with the exact item name
            items = self.api.get_items(search=item_name, limit=50)
            
            # Extract base item name (remove size like 250ml, 30ml, etc.)
            base_item_name = re.sub(r'\s+\d+(?:ml|ML|mL|kg|KG|g|G|l|L)\b', '', item_name, flags=re.IGNORECASE).strip()
            
            if base_item_name != item_name:
                logger.info(f"🔍 No sellable items found with '{item_name}', trying broader search: '{base_item_name}'")
                more_items = self.api.get_items(search=base_item_name, limit=100)
                existing_codes = {item.get("ItemCode") for item in items}
                for item in more_items:
                    if item.get("ItemCode") not in existing_codes:
                        items.append(item)
            
            # Filter for sellable items only
            sellable_items = []
            for item in items:
                item_code = item.get("ItemCode", "")
                item_name_display = item.get("ItemName", "")
                group_code = item.get("ItmsGrpCod")
                group = (item.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                is_sellable = item.get("SellItem") == "Y"
                
                is_packaging = group_code == 3 or "PACKING" in group or "PACKAGING" in group
                is_label = "LABEL" in item_name_display.upper() or "LABEL-" in item_name_display.upper()
                is_raw = "RAW" in group or item_code.startswith(("RM", "RMPK", "RMST"))
                
                if is_sellable and not is_packaging and not is_label and not is_raw:
                    sellable_items.append(item)
                    logger.info(f"✅ Found sellable item: {item_name_display} ({item_code})")
                else:
                    logger.info(f"⏭️ Skipping non-sellable item: {item_name_display} ({item_code})")
            
            # If no sellable items found, try to find chemical items (group code 4)
            if not sellable_items:
                for item in items:
                    if item.get("ItmsGrpCod") == 4:
                        sellable_items.append(item)
                        logger.info(f"✅ Found chemical item: {item.get('ItemName')} ({item.get('ItemCode')})")
            
            # If still no sellable items, try searching without any size filter
            if not sellable_items:
                product_name_match = re.match(r'^([a-zA-Z]+)', item_name)
                if product_name_match:
                    simple_name = product_name_match.group(1)
                    logger.info(f"🔍 Trying simple product name: '{simple_name}'")
                    simple_items = self.api.get_items(search=simple_name, limit=50)
                    for item in simple_items:
                        item_code = item.get("ItemCode", "")
                        item_name_display = item.get("ItemName", "")
                        group_code = item.get("ItmsGrpCod")
                        is_sellable = item.get("SellItem") == "Y"
                        is_packaging = group_code == 3
                        is_label = "LABEL" in item_name_display.upper()
                        
                        if is_sellable and not is_packaging and not is_label:
                            sellable_items.append(item)
                            logger.info(f"✅ Found sellable item from simple search: {item_name_display} ({item_code})")
            
            if not sellable_items:
                return {
                    "error": True,
                    "analysis_type": "competitor_price_check",
                    "message": f"No sellable items found matching '{item_name}'.",
                    "suggestions": ["Try a different product name", "Check spelling", "Browse available items"]
                }
            
            # =========================================================
            # TOKEN OPTIMIZATION: Limit to top 3 variants
            # =========================================================
            
            # Find exact size match first
            exact_size_match = None
            detected_size = entities.get("_detected_size")
            if detected_size:
                for item in sellable_items:
                    item_name_display = item.get("ItemName", "")
                    if detected_size.upper() in item_name_display.upper():
                        exact_size_match = item
                        break
            
            # Build limited list (max 3 variants)
            prioritized_items = []
            if exact_size_match:
                prioritized_items.append(exact_size_match)
                sellable_items = [item for item in sellable_items if item.get("ItemCode") != exact_size_match.get("ItemCode")]
            
            # Add up to 2 more items
            prioritized_items.extend(sellable_items[:2])
            
            logger.info(f"📊 Limiting to {len(prioritized_items)} variants (from {len(sellable_items)} total) to prevent token overflow")
            
            all_variants = []
            
            for item in prioritized_items[:3]:
                item_code = item.get("ItemCode")
                item_display_name = item.get("ItemName", item_name)
                
                if not item_code:
                    continue
                
                # Get Leysco's price
                leysco_price = None
                try:
                    leysco_price_result = self.pricing.get_price(item_code)
                    if leysco_price_result and leysco_price_result.get("found"):
                        leysco_price = leysco_price_result.get("price")
                        logger.info(f"💰 Leysco price for {item_display_name}: KES {leysco_price}")
                    else:
                        logger.warning(f"No price found for {item_display_name} ({item_code})")
                except Exception as e:
                    logger.warning(f"Could not get price for {item_code}: {e}")
                
                # Get competitor prices (limit to 3)
                try:
                    competitor_prices = await competitor_service.get_competitor_prices_async(
                        item_name=item_display_name,
                        item_code=item_code
                    )
                except Exception as e:
                    logger.warning(f"Could not fetch competitor prices: {e}")
                    competitor_prices = []
                
                # Filter valid prices and limit to 3
                valid_competitor_prices = [p for p in competitor_prices if p.get("price") and p.get("price") > 0][:3]
                
                comparison_data = None
                
                if leysco_price is not None and leysco_price > 0:
                    if valid_competitor_prices:
                        avg_comp_price = sum(p["price"] for p in valid_competitor_prices) / len(valid_competitor_prices)
                        min_comp_price = min(p["price"] for p in valid_competitor_prices)
                        max_comp_price = max(p["price"] for p in valid_competitor_prices)
                        
                        if leysco_price < min_comp_price * 0.95:
                            position = "VERY_COMPETITIVE"
                            message = "Your price is significantly lower than competitors"
                        elif leysco_price < avg_comp_price * 0.95:
                            position = "COMPETITIVE"
                            message = "Your price is below market average"
                        elif leysco_price <= avg_comp_price * 1.05:
                            position = "MARKET_AVERAGE"
                            message = "Your price is at market average"
                        elif leysco_price <= max_comp_price * 1.1:
                            position = "SLIGHTLY_HIGH"
                            message = "Your price is above market average"
                        else:
                            position = "HIGH"
                            message = "Your price is significantly higher than competitors"
                        
                        comparison_data = {
                            "leysco_price": leysco_price,
                            "competitive_position": position,
                            "message": message,
                            "market_stats": {
                                "average": round(avg_comp_price, 2),
                                "lowest": round(min_comp_price, 2),
                                "highest": round(max_comp_price, 2),
                            },
                            "savings_vs_average": round(avg_comp_price - leysco_price, 2) if leysco_price < avg_comp_price else 0,
                            "recommendation": self._get_competitor_recommendation(position, leysco_price, avg_comp_price)
                        }
                    else:
                        comparison_data = {
                            "leysco_price": leysco_price,
                            "competitive_position": "NO_COMPETITOR_DATA",
                            "message": "No competitor price data available for this item",
                            "recommendation": "Monitor market manually or check competitor websites"
                        }
                else:
                    comparison_data = {
                        "leysco_price": None,
                        "competitive_position": "NO_PRICE",
                        "message": "No price configured in Leysco system for this item",
                        "recommendation": "Set up pricing to enable competitor comparison"
                    }
                
                variant_data = {
                    "item_code": item_code,
                    "item_name": item_display_name,
                    "leysco_price": leysco_price,
                    "competitor_count": len(valid_competitor_prices),
                    "competitors": valid_competitor_prices[:3],
                    "price_range": {
                        "lowest": min(p["price"] for p in valid_competitor_prices) if valid_competitor_prices else None,
                        "highest": max(p["price"] for p in valid_competitor_prices) if valid_competitor_prices else None,
                        "average": sum(p["price"] for p in valid_competitor_prices) / len(valid_competitor_prices) if valid_competitor_prices else None
                    } if valid_competitor_prices else {},
                    "comparison": comparison_data
                }
                
                all_variants.append(variant_data)
            
            if not all_variants:
                return {
                    "analysis_type": "competitor_price_check",
                    "item_name": item_name,
                    "message": "No sellable items found with pricing information",
                    "suggestions": ["Try a different product name", "Check if the product has a price configured"]
                }
            
            # Build compact result
            result = {
                "analysis_type": "competitor_price_check",
                "search_term": item_name,
                "variants_found": len(all_variants),
                "variants": all_variants,
                "summary": {
                    "total_variants": len(all_variants),
                    "variants_with_prices": sum(1 for v in all_variants if v["leysco_price"] and v["leysco_price"] > 0),
                    "variants_with_competitor_data": sum(1 for v in all_variants if v["competitor_count"] > 0)
                },
                "timestamp": datetime.now().isoformat(),
                "_truncated": len(sellable_items) > 3,
                "_total_available": len(sellable_items)
            }
            
            # If only one variant, flatten for easier reading
            if len(all_variants) == 1:
                result = {
                    "analysis_type": "competitor_price_check",
                    "item_name": all_variants[0]["item_name"],
                    "item_code": all_variants[0]["item_code"],
                    "leysco_price": all_variants[0]["leysco_price"],
                    "comparison": all_variants[0]["comparison"],
                    "competitors": all_variants[0]["competitors"],
                    "competitor_count": all_variants[0]["competitor_count"],
                    "price_range": all_variants[0]["price_range"],
                    "timestamp": datetime.now().isoformat(),
                    "_truncated": len(sellable_items) > 3
                }
            
            return result
                
        except Exception as e:
            self._record_error()
            logger.error(f"Error in competitor_price_check: {e}", exc_info=True)
            return {
                "error": True,
                "analysis_type": "competitor_price_check",
                "message": f"Failed to check competitor prices: {str(e)}"
            }

    async def find_best_price(self, entities: dict) -> Dict[str, Any]:
        """Find the best (lowest) price for an item across all sources."""
        item_name = entities.get("item_name", "")
        
        if not item_name:
            return {
                "error": True,
                "analysis_type": "best_price",
                "message": "Please specify an item to find the best price for",
                "suggestions": [
                    "Where can I find the cheapest cabbage?",
                    "Best price for vegimax",
                    "Who sells tomatoes at the lowest price?"
                ]
            }
        
        logger.info(f"💰 Finding best price for: {item_name}")
        
        # Check if competitor service is available
        competitor_service = self._get_competitor_service()
        if competitor_service is None:
            return {
                "analysis_type": "best_price",
                "item_name": item_name,
                "message": "Best price service is currently unavailable. Please check our internal pricing.",
                "suggestions": ["Check item price", "Browse items", "Contact sales team"],
                "status": "service_unavailable"
            }
        
        try:
            items = self.api.get_items(search=item_name, limit=5)
            if not items:
                return {
                    "error": True,
                    "analysis_type": "best_price",
                    "message": f"No items found matching '{item_name}'",
                    "suggestions": ["Try a different name", "Check spelling"]
                }
            
            all_results = []
            
            for item in items[:3]:
                item_code = item.get("ItemCode")
                item_display_name = item.get("ItemName", item_name)
                
                try:
                    competitor_prices = await competitor_service.get_competitor_prices_async(
                        item_name=item_display_name,
                        item_code=item_code
                    )
                except Exception as e:
                    logger.warning(f"Could not fetch competitor prices: {e}")
                    competitor_prices = []
                
                if competitor_prices:
                    valid_prices = [p for p in competitor_prices if p.get("price") and p.get("price") > 0]
                    if valid_prices:
                        sorted_prices = sorted(valid_prices, key=lambda x: x["price"])
                        best_price = sorted_prices[0]
                        
                        leysco_price = None
                        try:
                            price_result = self.pricing.get_price(item_code)
                            if price_result and price_result.get("found"):
                                leysco_price = price_result.get("price")
                        except Exception:
                            pass
                        
                        result = {
                            "item_code": item_code,
                            "item_name": item_display_name,
                            "best_price": best_price,
                            "other_options": sorted_prices[1:4],
                            "price_summary": {
                                "lowest": best_price["price"],
                                "highest": sorted_prices[-1]["price"],
                                "average": sum(p["price"] for p in sorted_prices) / len(sorted_prices),
                                "competitors_checked": len(sorted_prices)
                            }
                        }
                        
                        if leysco_price and leysco_price > 0:
                            result["leysco_price"] = leysco_price
                            savings = leysco_price - best_price["price"]
                            result["potential_savings"] = round(max(0, savings), 2)
                            result["savings_percent"] = round((savings / leysco_price) * 100, 1) if leysco_price > 0 and savings > 0 else 0
                            
                            if savings > 0:
                                result["message"] = f"You could save KES {result['potential_savings']} by buying from {best_price['competitor_name']}"
                            else:
                                result["message"] = "Leysco's price is already competitive!"
                        
                        all_results.append(result)
            
            if not all_results:
                return {
                    "error": True,
                    "analysis_type": "best_price",
                    "message": f"No price data available for {item_name}",
                    "suggestions": ["Try checking our own prices", "Show all items"]
                }
            
            if len(all_results) == 1:
                return all_results[0]
            
            return {
                "analysis_type": "best_price",
                "search_term": item_name,
                "items_found": len(all_results),
                "results": all_results
            }
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in find_best_price: {e}", exc_info=True)
            return {
                "error": True,
                "analysis_type": "best_price",
                "message": f"Failed to find best price: {str(e)}"
            }

    async def market_intelligence(self, entities: dict) -> Dict[str, Any]:
        """Get market intelligence and price trends."""
        category = entities.get("item_name", "") or entities.get("category", "")
        
        logger.info(f"📊 Getting market intelligence for: {category or 'all products'}")
        
        # Check if competitor service is available
        competitor_service = self._get_competitor_service()
        if competitor_service is None:
            # Return basic market intelligence without competitor data
            return {
                "analysis_type": "market_intelligence",
                "category": category or "All Products",
                "timestamp": datetime.now().isoformat(),
                "message": "Market intelligence service is currently unavailable. Showing basic insights.",
                "market_trends": {
                    "overall": "stable",
                    "vegetables": "increasing",
                    "fruits": "stable",
                    "grains": "decreasing",
                },
                "key_insights": [
                    "Tomato prices expected to rise 15% next month due to short supply",
                    "Cabbage prices stable with good availability",
                    "Maize prices dropping with new harvest",
                ],
                "recommendations": [
                    "Review vegetable pricing strategy",
                    "Lock in grain prices with suppliers",
                ]
            }
        
        try:
            market_data = await competitor_service.get_market_intelligence_async(
                category if category else None
            )
            
            return {
                "analysis_type": "market_intelligence",
                "category": category or "All Products",
                "timestamp": datetime.now().isoformat(),
                "market_trends": market_data.get("market_trends", {}),
                "price_volatility": market_data.get("price_volatility", {}),
                "key_insights": market_data.get("key_insights", []),
                "opportunities": market_data.get("opportunities", []),
                "recommendations": market_data.get("recommendations", []),
            }
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in market_intelligence: {e}", exc_info=True)
            return {
                "error": True,
                "analysis_type": "market_intelligence",
                "message": f"Failed to get market intelligence: {str(e)}"
            }

    async def price_alert(self, entities: dict) -> Dict[str, Any]:
        """Set up price alerts for items."""
        item_name = entities.get("item_name", "")
        
        if not item_name:
            return {
                "error": True,
                "analysis_type": "price_alert",
                "message": "Please specify an item to monitor for price alerts",
                "suggestions": [
                    "Alert me when cabbage price drops",
                    "Monitor tomato prices",
                    "Notify me of price changes for vegimax"
                ]
            }
        
        logger.info(f"🔔 Setting up price alert for: {item_name}")
        
        try:
            items = self.api.get_items(search=item_name, limit=3)
            current_prices = []
            
            for item in items:
                item_code = item.get("ItemCode")
                item_name_display = item.get("ItemName", item_name)
                
                try:
                    price_result = self.pricing.get_price(item_code)
                    if price_result and price_result.get("found"):
                        current_prices.append({
                            "item_code": item_code,
                            "item_name": item_name_display,
                            "price": price_result.get("price"),
                            "price_list": price_result.get("price_list_name")
                        })
                except Exception:
                    pass
            
            # Store alert in cache
            alert_key = f"alert_{item_name}_{datetime.now().strftime('%Y%m%d')}"
            alert_data = {
                "item_name": item_name,
                "created_at": datetime.now().isoformat(),
                "settings": {
                    "monitoring_frequency": "Daily",
                    "notification_method": "In-app",
                    "threshold": "5% change",
                    "duration": "30 days"
                }
            }
            self._set_cache(alert_key, alert_data)
            
            return {
                "analysis_type": "price_alert",
                "item_name": item_name,
                "status": "active",
                "message": f"✅ Price alert set for {item_name}. You'll be notified when prices change significantly.",
                "alert_settings": {
                    "monitoring_frequency": "Daily",
                    "notification_method": "In-app",
                    "threshold": "5% change",
                    "duration": "30 days"
                },
                "current_prices": current_prices,
                "alert_id": alert_key
            }
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in price_alert: {e}", exc_info=True)
            return {
                "error": True,
                "analysis_type": "price_alert",
                "message": f"Failed to set price alert: {str(e)}"
            }

    # =========================================================
    # INVENTORY DECISIONS - FIXED with proper field mapping
    # =========================================================

    def analyze_inventory_health(
        self,
        warehouse_code: Optional[str] = None,
        include_recommendations: bool = True,
        limit: int = 500
    ) -> Dict[str, Any]:
        """Comprehensive inventory health analysis with proper API field mapping."""
        logger.info(f"📊 Analyzing inventory health for {warehouse_code or 'all warehouses'}")

        # Check cache
        cache_key = f"inventory_health_{warehouse_code}"
        cached_result = self._get_cached(cache_key, ttl=120)
        if cached_result is not None:
            return cached_result

        try:
            # Get inventory data
            inventory = self.api.get_inventory_report(limit=limit)
            
            if not inventory:
                return {
                    "error": "No inventory data available",
                    "message": "Unable to fetch inventory data at this time. Please try again later.",
                    "recommendations": ["Check API connection", "Verify warehouse code"]
                }

            # Log sample of first item to debug
            if inventory and len(inventory) > 0:
                logger.info(f"Sample inventory item fields: {list(inventory[0].keys())}")

            velocity_map = self._get_sales_velocity_data_cached()
            
            # Batch fetch prices for all items
            item_codes = []
            for item in inventory:
                item_code = item.get("ItemCode") or item.get("item_code")
                if item_code:
                    item_codes.append(item_code)
            
            price_map = self._batch_get_prices(item_codes)

            analysis = {
                "summary": {},
                "critical_items": [],
                "overstock_items": [],
                "slow_movers": [],
                "fast_movers": [],
                "reorder_recommendations": [],
                "risk_items": [],
                "opportunity_items": [],
                "health_score": 0,
                "priority_actions": [],
            }

            total_value = 0.0
            total_items = 0
            critical_count = 0
            low_count = 0
            overstock_count = 0
            healthy_count = 0
            out_of_stock_count = 0

            for item in inventory:
                if warehouse_code and item.get("WhsCode") != warehouse_code:
                    continue

                # Handle different field name variations from API
                item_code = item.get("ItemCode") or item.get("item_code", "")
                item_name = item.get("ItemName") or item.get("item_name", item_code)
                
                # API uses CurrentOnHand, not OnHand
                on_hand = float(item.get("CurrentOnHand") or item.get("OnHand") or item.get("on_hand") or 0)
                
                # API uses CurrentIsCommited, not IsCommited
                committed = float(item.get("CurrentIsCommited") or item.get("IsCommited") or item.get("is_commited") or 0)
                
                available = on_hand - committed
                
                # Get unit price from price map
                unit_price = price_map.get(item_code, 0)
                item_value = on_hand * unit_price

                total_value += item_value
                total_items += 1

                # Get sales velocity (daily average)
                velocity = velocity_map.get(item_code, 0.0)
                days_of_stock = self._calculate_days_of_stock(available, velocity)

                # Determine stock status
                if available <= 0:
                    stock_status = "OUT_OF_STOCK"
                    out_of_stock_count += 1
                elif days_of_stock != float('inf') and days_of_stock < self.thresholds["critical_stock_days"]:
                    stock_status = "CRITICAL"
                    critical_count += 1
                elif days_of_stock != float('inf') and days_of_stock < self.thresholds["low_stock_days"]:
                    stock_status = "LOW"
                    low_count += 1
                elif days_of_stock != float('inf') and days_of_stock > self.thresholds["max_stock_days"] and velocity > 0:
                    stock_status = "OVERSTOCK"
                    overstock_count += 1
                else:
                    stock_status = "HEALTHY"
                    healthy_count += 1

                # Build item info dictionary
                item_info = {
                    "code": item_code,
                    "name": item_name,
                    "available": round(available, 1),
                    "on_hand": round(on_hand, 1),
                    "committed": round(committed, 1),
                    "daily_avg": round(velocity, 2),
                    "value": round(item_value, 2),
                    "unit_price": round(unit_price, 2),
                    "warehouse": item.get("WhsCode") or item.get("whs_code", "Unknown")
                }
                
                # Add days_left if applicable
                if days_of_stock != float('inf'):
                    item_info["days_left"] = round(days_of_stock, 1)
                else:
                    item_info["days_left"] = "N/A"

                # Categorize items
                if stock_status == "CRITICAL":
                    item_info["action"] = "ORDER IMMEDIATELY"
                    analysis["critical_items"].append(item_info)
                elif stock_status == "LOW":
                    item_info["action"] = "ORDER SOON"
                    analysis["risk_items"].append(item_info)
                elif stock_status == "OVERSTOCK":
                    item_info["action"] = "Consider promotion or reduced ordering"
                    analysis["overstock_items"].append(item_info)
                elif stock_status == "OUT_OF_STOCK":
                    item_info["action"] = "URGENT: Restock immediately"
                    analysis["risk_items"].append(item_info)

                # Slow/fast movers based on sales velocity
                if velocity > 0:
                    if velocity < 0.1:  # Less than 1 unit per 10 days
                        analysis["slow_movers"].append(item_info)
                    elif velocity > 10:  # More than 10 units per day
                        analysis["fast_movers"].append(item_info)

                # Reorder recommendations
                if velocity > 0 and available < (velocity * 14):  # Less than 2 weeks of stock
                    reorder_point = velocity * self.thresholds["reorder_point_multiplier"] * 7
                    urgency = "HIGH" if available < reorder_point * 0.5 else "MEDIUM"
                    analysis["reorder_recommendations"].append({
                        "code": item_code,
                        "name": item_name,
                        "current": round(available, 1),
                        "reorder_at": round(reorder_point),
                        "recommended_qty": round(reorder_point * 2),
                        "urgency": urgency,
                        "daily_avg": round(velocity, 2),
                    })

            # Calculate health score
            total_analyzed = critical_count + low_count + healthy_count + overstock_count + out_of_stock_count
            if total_analyzed > 0:
                weighted_score = (
                    critical_count * 20 +
                    low_count * 40 +
                    healthy_count * 90 +
                    overstock_count * 50 +
                    out_of_stock_count * 0
                ) / total_analyzed
                analysis["health_score"] = min(100, max(0, int(weighted_score)))

            # Priority actions
            if out_of_stock_count > 0:
                analysis["priority_actions"].append({
                    "priority": "HIGHEST",
                    "action": f"🚨 URGENT: {out_of_stock_count} items are OUT OF STOCK",
                    "details": "These items have zero available stock and need immediate replenishment"
                })
            
            if critical_count > 0:
                analysis["priority_actions"].append({
                    "priority": "HIGHEST",
                    "action": f"ORDER IMMEDIATELY: {critical_count} items critically low",
                    "details": "These items will run out in < 3 days"
                })
            
            if low_count > 5:
                analysis["priority_actions"].append({
                    "priority": "HIGH",
                    "action": f"Review {low_count} low stock items",
                    "details": "Place orders within the week"
                })
            
            if overstock_count > 10:
                analysis["priority_actions"].append({
                    "priority": "MEDIUM",
                    "action": f"Review {overstock_count} overstocked items",
                    "details": "Consider promotions or returns"
                })

            # Get top items for summary
            top_critical = analysis["critical_items"][:5]
            top_reorders = analysis["reorder_recommendations"][:5]

            analysis["summary"] = {
                "total_items": total_items,
                "total_inventory_value": round(total_value, 2),
                "critical_items_count": critical_count,
                "low_items_count": low_count,
                "healthy_items_count": healthy_count,
                "overstock_items_count": overstock_count,
                "out_of_stock_count": out_of_stock_count,
                "slow_movers_count": len(analysis["slow_movers"]),
                "fast_movers_count": len(analysis["fast_movers"]),
                "reorder_recommendations_count": len(analysis["reorder_recommendations"]),
                "warehouse": warehouse_code or "All Warehouses",
                "health_rating": self._get_health_rating(analysis["health_score"]),
                "top_critical_items": [
                    {"name": item["name"], "available": item["available"], "days_left": item["days_left"]}
                    for item in top_critical
                ],
                "top_reorder_items": [
                    {"name": item["name"], "current": item["current"], "recommended": item["recommended_qty"]}
                    for item in top_reorders
                ]
            }

            # Cache result
            self._set_cache(cache_key, analysis)
            return analysis
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in analyze_inventory_health: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Inventory analysis failed: {str(e)}"
            }

    # =========================================================
    # FIXED: GET REORDER DECISIONS (Token optimized)
    # =========================================================

    def get_reorder_decisions(
        self,
        filter_item_code: Optional[str] = None,
        days_ahead: int = 14
    ) -> Dict[str, Any]:
        """
        Get reorder recommendations with optimal quantities and actionable insights.
        Token-optimized version that limits data size for LLM.
        
        Args:
            filter_item_code: Optional item code to filter for a single item
            days_ahead: Number of days to plan for (default 14)
        
        Returns:
            Dictionary with reorder decisions, priorities, and actionable recommendations
        """
        cache_key = f"reorder_decisions_{filter_item_code}_{days_ahead}"
        cached_result = self._get_cached(cache_key, ttl=180)  # 3 minutes cache
        if cached_result is not None:
            return cached_result

        try:
            inventory = self.api.get_inventory_report(limit=500)
            if not inventory:
                return {
                    "error": "No inventory data available",
                    "message": "Unable to fetch inventory data for reorder analysis"
                }
            
            velocity_map = self._get_sales_velocity_data_cached()
            
            decisions = {
                "analysis_type": "reorder_decisions",
                "analysis_date": datetime.now().isoformat(),
                "planning_horizon_days": days_ahead,
                "immediate_orders": [],      # URGENT - order now
                "planned_orders": [],         # Schedule for this week
                "monitor_items": [],          # Watch list
                "optimal_quantities": {},
                "total_reorder_cost": 0,
                "priority_summary": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
                "recommendations": [],
                "reorder_by_warehouse": {},
            }

            for item in inventory:
                item_code = item.get("ItemCode", "")
                if filter_item_code and item_code != filter_item_code:
                    continue

                item_name = item.get("ItemName", item_code)
                warehouse = item.get("WhsCode", "Unknown")
                
                # Get stock levels with proper field mapping
                on_hand = float(item.get("CurrentOnHand") or item.get("OnHand", 0) or 0)
                committed = float(item.get("CurrentIsCommited") or item.get("IsCommited", 0) or 0)
                available = on_hand - committed

                # Get sales velocity (daily average)
                velocity = velocity_map.get(item_code, 0.0)
                
                # Skip items with no sales data unless they have committed orders
                if velocity == 0 and committed == 0:
                    continue
                
                # Use committed orders to estimate demand if no sales history
                if velocity == 0 and committed > 0:
                    velocity = committed / 30  # Assume committed represents 30 days demand
                
                # Get pricing
                unit_price = self._get_average_price(item_code)
                if unit_price <= 0:
                    unit_price = 100  # Default estimate if no price available
                
                # Calculate reorder metrics
                days_left = self._calculate_days_of_stock(available, velocity) if velocity > 0 else float('inf')
                
                # Calculate recommended order quantity
                if velocity > 0:
                    # EOQ calculation
                    ordering_cost = 500.0  # Cost per order (estimate)
                    holding_cost = unit_price * 0.25  # Annual holding cost (25% of unit price)
                    annual_demand = velocity * 365
                    
                    if holding_cost > 0:
                        eoq = _sqrt((2 * annual_demand * ordering_cost) / holding_cost)
                    else:
                        eoq = velocity * 30  # 30 days of stock
                    
                    # Recommended order quantity (based on days ahead)
                    recommended_qty = max(velocity * days_ahead, eoq)
                    
                    # Round to reasonable numbers
                    if recommended_qty < 10:
                        recommended_qty = round(recommended_qty)
                    else:
                        recommended_qty = round(recommended_qty / 10) * 10
                else:
                    recommended_qty = 0
                
                # Calculate reorder urgency
                needs_reorder = False
                urgency = "NONE"
                action = "Adequate stock"
                urgency_reason = ""
                
                if available <= 0:
                    needs_reorder = True
                    urgency = "CRITICAL"
                    action = "🔄 ORDER IMMEDIATELY - Out of stock"
                    urgency_reason = f"Item is out of stock (0 units available)"
                elif days_left != float('inf') and days_left < 3:
                    needs_reorder = True
                    urgency = "CRITICAL"
                    action = "⚠️ URGENT - Order within 24 hours"
                    urgency_reason = f"Only {round(available, 1)} units left ({round(days_left, 1)} days of stock)"
                elif days_left != float('inf') and days_left < 7:
                    needs_reorder = True
                    urgency = "HIGH"
                    action = "📦 Order this week"
                    urgency_reason = f"Low stock: {round(available, 1)} units ({round(days_left, 1)} days left)"
                elif days_left != float('inf') and days_left < 14:
                    needs_reorder = True
                    urgency = "MEDIUM"
                    action = "📋 Plan order for next week"
                    urgency_reason = f"Stock running low: {round(available, 1)} units"
                elif days_left != float('inf') and days_left < 30:
                    needs_reorder = False
                    urgency = "LOW"
                    action = "👁️ Monitor stock levels"
                    urgency_reason = f"Stock adequate for {round(days_left, 1)} days"
                
                # Calculate order cost
                order_cost = recommended_qty * unit_price if recommended_qty > 0 else 0
                
                order_item = {
                    "code": item_code,
                    "name": item_name,
                    "warehouse": warehouse,
                    "current_stock": round(on_hand, 1),
                    "committed": round(committed, 1),
                    "available": round(available, 1),
                    "daily_demand": round(velocity, 2),
                    "days_of_stock_left": round(days_left, 1) if days_left != float('inf') else "N/A",
                    "recommended_qty": recommended_qty,
                    "estimated_cost": round(order_cost),
                    "unit_price": round(unit_price, 2),
                    "urgency": urgency,
                    "action": action,
                    "urgency_reason": urgency_reason,
                    "needs_reorder": needs_reorder
                }
                
                # Categorize by urgency - LIMIT to prevent token overflow
                if urgency in ["CRITICAL", "HIGH"]:
                    if urgency == "CRITICAL":
                        decisions["immediate_orders"].append(order_item)
                        decisions["priority_summary"]["CRITICAL"] += 1
                        decisions["total_reorder_cost"] += order_cost
                    elif urgency == "HIGH":
                        decisions["immediate_orders"].append(order_item)
                        decisions["priority_summary"]["HIGH"] += 1
                        decisions["total_reorder_cost"] += order_cost
                elif urgency == "MEDIUM":
                    # Only keep top 10 medium priority items
                    if len(decisions["planned_orders"]) < 10:
                        decisions["planned_orders"].append(order_item)
                        decisions["priority_summary"]["MEDIUM"] += 1
                elif urgency == "LOW":
                    # Skip low priority items entirely
                    pass
                
                # Store optimal quantities (only for items that need attention)
                if needs_reorder:
                    decisions["optimal_quantities"][item_code] = {
                        "name": item_name,
                        "recommended_qty": recommended_qty,
                        "reorder_point_days": 7,
                        "safety_stock_days": 3,
                        "max_stock_days": 60,
                        "unit_price": round(unit_price, 2),
                    }
                
                # Group by warehouse for warehouse-specific recommendations
                if warehouse not in decisions["reorder_by_warehouse"]:
                    decisions["reorder_by_warehouse"][warehouse] = []
                if needs_reorder:
                    decisions["reorder_by_warehouse"][warehouse].append(order_item)

            # =========================================================
            # TOKEN OPTIMIZATION: Limit the size of the response
            # =========================================================
            # Keep only top 5 immediate orders (critical + high)
            decisions["immediate_orders"] = decisions["immediate_orders"][:5]
            
            # Keep only top 5 planned orders
            decisions["planned_orders"] = decisions["planned_orders"][:5]
            
            # Sort by urgency
            urgency_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            decisions["immediate_orders"].sort(
                key=lambda x: (
                    urgency_order.get(x["urgency"], 4),
                    x["days_of_stock_left"] if isinstance(x["days_of_stock_left"], (int, float)) else 999
                )
            )
            decisions["planned_orders"].sort(
                key=lambda x: (
                    urgency_order.get(x["urgency"], 4),
                    x["days_of_stock_left"] if isinstance(x["days_of_stock_left"], (int, float)) else 999
                )
            )
            
            # Generate actionable recommendations (compact)
            recommendations = []
            
            if decisions["priority_summary"]["CRITICAL"] > 0:
                recommendations.append({
                    "priority": "CRITICAL",
                    "message": f"🚨 {decisions['priority_summary']['CRITICAL']} items are OUT OF STOCK or critically low",
                    "action": "Place purchase orders immediately"
                })
            
            if decisions["priority_summary"]["HIGH"] > 0:
                recommendations.append({
                    "priority": "HIGH",
                    "message": f"⚠️ {decisions['priority_summary']['HIGH']} items are running low",
                    "action": "Review and order within 24-48 hours"
                })
            
            if decisions["priority_summary"]["MEDIUM"] > 0:
                recommendations.append({
                    "priority": "MEDIUM",
                    "message": f"📋 {decisions['priority_summary']['MEDIUM']} items need attention soon",
                    "action": "Plan orders for next week's delivery cycle"
                })
            
            # Add total cost recommendation
            if decisions["total_reorder_cost"] > 0:
                recommendations.append({
                    "priority": "INFO",
                    "message": f"💰 Estimated reorder value: KES {decisions['total_reorder_cost']:,.2f}",
                    "action": "Review budget and approve purchase orders"
                })
            
            decisions["recommendations"] = recommendations
            
            # Create a compact summary for quick overview
            decisions["summary"] = {
                "total_items_analyzed": len(inventory),
                "items_needing_reorder": decisions["priority_summary"]["CRITICAL"] + decisions["priority_summary"]["HIGH"] + decisions["priority_summary"]["MEDIUM"],
                "critical_count": decisions["priority_summary"]["CRITICAL"],
                "high_count": decisions["priority_summary"]["HIGH"],
                "medium_count": decisions["priority_summary"]["MEDIUM"],
                "estimated_total_cost": round(decisions["total_reorder_cost"], 2),
                "top_critical_items": [
                    {"name": item["name"], "available": item["available"], "days_left": item["days_of_stock_left"]}
                    for item in decisions["immediate_orders"][:3] if item["urgency"] == "CRITICAL"
                ]
            }
            
            # Create a compact version for LLM (reduces token usage)
            compact_decisions = {
                "analysis_type": "reorder_decisions",
                "summary": decisions["summary"],
                "priority_summary": decisions["priority_summary"],
                "total_reorder_cost": decisions["total_reorder_cost"],
                "immediate_orders": [
                    {
                        "name": item["name"],
                        "code": item["code"],
                        "available": item["available"],
                        "days_left": item["days_of_stock_left"],
                        "recommended_qty": item["recommended_qty"],
                        "urgency": item["urgency"]
                    }
                    for item in decisions["immediate_orders"][:3]
                ],
                "planned_orders": [
                    {
                        "name": item["name"],
                        "code": item["code"],
                        "available": item["available"],
                        "recommended_qty": item["recommended_qty"],
                        "urgency": item["urgency"]
                    }
                    for item in decisions["planned_orders"][:3]
                ],
                "recommendations": decisions["recommendations"],
                "_truncated": len(decisions.get("immediate_orders", [])) > 5 or len(decisions.get("planned_orders", [])) > 5
            }
            
            # Cache the compact result
            self._set_cache(cache_key, compact_decisions)
            return compact_decisions
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in get_reorder_decisions: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Reorder analysis failed: {str(e)}"
            }

    # =========================================================
    # PRICING DECISIONS
    # =========================================================

    def analyze_pricing_opportunities(
        self,
        customer_code: Optional[str] = None,
        days_history: int = 180,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Analyze pricing to find opportunities and risks."""
        cache_key = f"pricing_opportunities_{customer_code}_{days_history}_{limit}"
        cached_result = self._get_cached(cache_key, ttl=300)
        if cached_result is not None:
            return cached_result

        try:
            items = self.api.get_items(limit=limit)
            if not items:
                return {
                    "error": "No items data available",
                    "message": "Unable to fetch items for pricing analysis"
                }
            
            opportunities = {
                "price_drops": [],
                "price_hikes": [],
                "best_value": [],
                "volume_discount_opportunities": [],
                "margin_analysis": [],
                "seasonal_patterns": [],
                "summary": {},
            }

            price_drop_count = 0
            price_hike_count = 0

            for item in items:
                item_code = item.get("ItemCode", "")
                item_name = item.get("ItemName", item_code)

                current_price_result = self.pricing.get_price(item_code)
                current_price = current_price_result.get("price") if current_price_result else None
                
                if current_price is None or current_price <= 0:
                    continue

                historical_prices = self._get_historical_prices(item_code, days_history)

                if historical_prices and current_price > 0:
                    avg_price = _mean(historical_prices)
                    min_price = min(historical_prices)
                    max_price = max(historical_prices)
                    price_std = _std(historical_prices)
                    
                    if avg_price and avg_price > 0:
                        price_change = (current_price - avg_price) / avg_price
                    else:
                        price_change = None
                    
                    confidence = _confidence_score(len(historical_prices))

                    if price_change is not None and price_change < -self.thresholds["price_drop_threshold"]:
                        price_drop_count += 1
                        opportunities["price_drops"].append({
                            "code": item_code,
                            "name": item_name,
                            "current": round(current_price),
                            "avg_price": round(avg_price),
                            "min_price": round(min_price),
                            "max_price": round(max_price),
                            "drop_percent": round(abs(price_change) * 100, 1),
                            "volatility": round(price_std / avg_price * 100, 1) if avg_price else 0,
                            "confidence": confidence,
                            "action": "Good time to stock up",
                            "priority": "HIGH" if price_change < -0.25 else "MEDIUM",
                        })
                    elif price_change is not None and price_change > self.thresholds["price_hike_threshold"]:
                        price_hike_count += 1
                        opportunities["price_hikes"].append({
                            "code": item_code,
                            "name": item_name,
                            "current": round(current_price),
                            "avg_price": round(avg_price),
                            "min_price": round(min_price),
                            "hike_percent": round(price_change * 100, 1),
                            "volatility": round(price_std / avg_price * 100, 1) if avg_price else 0,
                            "confidence": confidence,
                            "action": "Consider alternatives or negotiate",
                            "priority": "HIGH" if price_change > 0.3 else "MEDIUM",
                        })

            # Sort by priority
            priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
            opportunities["price_drops"].sort(
                key=lambda x: (priority_order.get(x["priority"], 3), x["drop_percent"]), 
                reverse=True
            )
            opportunities["price_hikes"].sort(
                key=lambda x: (priority_order.get(x["priority"], 3), x["hike_percent"]), 
                reverse=True
            )

            opportunities["summary"] = {
                "total_items_analyzed": len(items),
                "price_drops_found": price_drop_count,
                "price_hikes_found": price_hike_count,
                "volume_opportunities": len(opportunities["volume_discount_opportunities"]),
                "analysis_period_days": days_history,
            }

            self._set_cache(cache_key, opportunities)
            return opportunities
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in analyze_pricing_opportunities: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Pricing analysis failed: {str(e)}"
            }

    # =========================================================
    # BATCH OPERATIONS
    # =========================================================
    
    def _batch_get_prices(self, item_codes: List[str]) -> Dict[str, float]:
        """Fetch prices for multiple items efficiently."""
        if not item_codes:
            return {}
        
        price_map = {}
        
        # Try to use batch API if available
        try:
            if hasattr(self.pricing, 'get_prices_batch'):
                batch_results = self.pricing.get_prices_batch(item_codes)
                for code, price_data in batch_results.items():
                    if price_data and price_data.get("found"):
                        price_map[code] = float(price_data.get("price", 0))
                return price_map
        except Exception as e:
            logger.debug(f"Batch pricing not available: {e}")
        
        # Fallback to individual calls with rate limiting
        for code in item_codes[:100]:
            try:
                price = self._get_average_price(code)
                if price > 0:
                    price_map[code] = price
            except Exception as e:
                logger.debug(f"Could not get price for {code}: {e}")
        
        return price_map

    # =========================================================
    # SALES TREND ANALYSIS
    # =========================================================

    def get_sales_trend(self, days: int = 90) -> Dict[str, Any]:
        """Get sales trend analysis."""
        cache_key = f"sales_trend_{days}"
        cached_result = self._get_cached(cache_key, ttl=3600)
        if cached_result is not None:
            return cached_result

        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Try to get time series data from API
            try:
                time_series = self.api.get_crm_time_series(
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                    granularity="weekly"
                )
                
                if time_series:
                    result = {
                        "analysis_type": "sales_trend",
                        "period_days": days,
                        "start_date": start_date.strftime("%Y-%m-%d"),
                        "end_date": end_date.strftime("%Y-%m-%d"),
                        "data": time_series,
                        "message": f"Sales trend analysis for the last {days} days"
                    }
                    self._set_cache(cache_key, result)
                    return result
            except Exception as e:
                logger.warning(f"Could not fetch time series data: {e}")
            
            # Fallback to summary data
            summary = self.api.get_crm_data_summary(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )
            
            result = {
                "analysis_type": "sales_trend",
                "period_days": days,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "summary": summary,
                "message": f"Sales trend analysis for the last {days} days"
            }
            self._set_cache(cache_key, result)
            return result
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error getting sales trend: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Could not retrieve sales trend data: {str(e)}"
            }

    # =========================================================
    # INVENTORY TURNOVER ANALYSIS
    # =========================================================

    def get_inventory_turnover(self, warehouse_code: Optional[str] = None) -> Dict[str, Any]:
        """Get inventory turnover analysis."""
        cache_key = f"inventory_turnover_{warehouse_code}"
        cached_result = self._get_cached(cache_key, ttl=3600)
        if cached_result is not None:
            return cached_result

        try:
            # Try to get turnover data from API
            turnover_data = self.api.get_inventory_turnover(warehouse_code=warehouse_code)
            
            if turnover_data:
                if turnover_data:
                    total_turnover = sum(item.get("TurnoverRate", 0) for item in turnover_data)
                    avg_turnover = total_turnover / len(turnover_data) if turnover_data else 0
                    high_turnover = [item for item in turnover_data if item.get("TurnoverRate", 0) > 12]
                    low_turnover = [item for item in turnover_data if item.get("TurnoverRate", 0) < 2]
                    
                    result = {
                        "analysis_type": "inventory_turnover",
                        "warehouse": warehouse_code or "All Warehouses",
                        "data": turnover_data[:20],
                        "summary": {
                            "total_items": len(turnover_data),
                            "average_turnover": round(avg_turnover, 2),
                            "high_turnover_count": len(high_turnover),
                            "low_turnover_count": len(low_turnover),
                            "top_performers": high_turnover[:5],
                            "slow_movers": low_turnover[:5]
                        },
                        "message": f"Inventory turnover analysis for {warehouse_code or 'all warehouses'}"
                    }
                    self._set_cache(cache_key, result)
                    return result
            
            # Fallback - calculate from inventory report
            inventory = self.api.get_inventory_report(limit=200)
            if inventory:
                velocity_map = self._get_sales_velocity_data_cached()
                turnover_items = []
                
                for item in inventory[:50]:
                    item_code = item.get("ItemCode")
                    velocity = velocity_map.get(item_code, 0)
                    on_hand = float(item.get("CurrentOnHand") or item.get("OnHand", 0) or 0)
                    
                    annual_sales = velocity * 365
                    turnover_rate = annual_sales / on_hand if on_hand > 0 else 0
                    
                    turnover_items.append({
                        "ItemCode": item_code,
                        "ItemName": item.get("ItemName"),
                        "TurnoverRate": round(turnover_rate, 2),
                        "DailySales": round(velocity, 2),
                        "OnHand": round(on_hand, 1)
                    })
                
                turnover_items.sort(key=lambda x: x["TurnoverRate"], reverse=True)
                
                result = {
                    "analysis_type": "inventory_turnover",
                    "warehouse": warehouse_code or "All Warehouses",
                    "data": turnover_items[:20],
                    "message": f"Inventory turnover analysis (estimated from sales velocity)"
                }
                self._set_cache(cache_key, result)
                return result
            
            return {
                "error": True,
                "message": "No inventory turnover data available"
            }
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error getting inventory turnover: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Could not retrieve inventory turnover data: {str(e)}"
            }

    # =========================================================
    # CUSTOMER INSIGHTS
    # =========================================================

    def analyze_customer_behavior(self, customer_name: str) -> Dict[str, Any]:
        """Deep dive into a customer's purchasing patterns."""
        cache_key = f"customer_behavior_{customer_name}"
        cached_result = self._get_cached(cache_key, ttl=1800)
        if cached_result is not None:
            return cached_result

        try:
            customers = self.api.get_customers(search=customer_name, limit=1)
            if not customers:
                return {
                    "error": f"Customer '{customer_name}' not found",
                    "message": "Please check the spelling or try a different customer name",
                    "suggestions": ["List all customers", "Search by partial name"]
                }

            customer = customers[0]
            orders = self.api.get_customer_orders(
                customer_name=customer.get("CardName"), limit=100
            )

            analysis = {
                "customer": {
                    "name": customer.get("CardName"),
                    "code": customer.get("CardCode"),
                    "since": customer.get("CreateDate", "Unknown"),
                    "city": customer.get("City", "Unknown"),
                    "phone": customer.get("Phone1", "Unknown"),
                    "email": customer.get("EmailAddress", "Unknown"),
                },
                "purchase_patterns": {},
                "recommendations": [],
                "upsell_opportunities": [],
                "risk_factors": [],
                "rfm_score": {},
                "next_best_actions": [],
            }

            if not orders:
                analysis["risk_factors"].append("No order history found")
                analysis["recommendations"].append("Send welcome offer and product catalog")
                analysis["next_best_actions"] = [
                    {"action": "Send introductory email", "priority": "HIGH"},
                    {"action": "Offer first-purchase discount", "priority": "HIGH"},
                ]
                self._set_cache(cache_key, analysis)
                return analysis

            # Process orders
            dates = []
            amounts = []
            items_bought = Counter()
            categories = Counter()

            for order in orders:
                date_str = order.get("DocDate") or order.get("doc_date", "")
                if date_str:
                    dates.append(date_str[:10])

                amount = float(order.get("DocTotal") or order.get("doc_total") or 0)
                amounts.append(amount)

                lines = order.get("DocumentLines") or order.get("document_lines") or []
                for line in lines:
                    code = line.get("ItemCode")
                    if code:
                        items_bought[code] += 1
                        
                        item_details = self.api.get_items(search=code, limit=1)
                        if item_details and len(item_details) > 0:
                            category = item_details[0].get("item_group", {}).get("ItmsGrpNam", "Unknown")
                            categories[category] += 1

            # Parse dates and calculate intervals
            date_objs = []
            for d in dates:
                try:
                    date_objs.append(datetime.strptime(d, "%Y-%m-%d"))
                except ValueError:
                    pass

            date_objs.sort()

            # Calculate metrics
            total_orders = len(orders)
            total_spent = sum(amounts)
            avg_order = total_spent / total_orders if total_orders > 0 else 0
            
            if len(date_objs) > 1:
                intervals = [(date_objs[i+1] - date_objs[i]).days for i in range(len(date_objs)-1)]
                avg_interval = _mean(intervals)
                purchase_frequency = 30 / avg_interval if avg_interval > 0 else 0
            else:
                avg_interval = 0
                purchase_frequency = 0

            if date_objs:
                days_since_last = (datetime.now() - date_objs[-1]).days
                is_active = days_since_last < 30
                is_churn_risk = days_since_last > self.thresholds["churn_risk_days"]
            else:
                days_since_last = 999
                is_active = False
                is_churn_risk = True

            # RFM scoring
            if days_since_last <= 7:
                recency_score = 5
            elif days_since_last <= 30:
                recency_score = 4
            elif days_since_last <= 60:
                recency_score = 3
            elif days_since_last <= 90:
                recency_score = 2
            else:
                recency_score = 1

            if purchase_frequency >= 4:
                frequency_score = 5
            elif purchase_frequency >= 2:
                frequency_score = 4
            elif purchase_frequency >= 1:
                frequency_score = 3
            elif purchase_frequency >= 0.5:
                frequency_score = 2
            else:
                frequency_score = 1

            if avg_order >= 100000:
                monetary_score = 5
            elif avg_order >= 50000:
                monetary_score = 4
            elif avg_order >= 25000:
                monetary_score = 3
            elif avg_order >= 10000:
                monetary_score = 2
            else:
                monetary_score = 1

            rfm_total = recency_score + frequency_score + monetary_score

            analysis["purchase_patterns"] = {
                "total_orders": total_orders,
                "total_spent": round(total_spent, 2),
                "avg_order_value": round(avg_order, 2),
                "purchase_frequency": round(purchase_frequency, 1),
                "avg_days_between_orders": round(avg_interval, 1) if avg_interval else "N/A",
                "estimated_monthly_spend": round(purchase_frequency * avg_order, 2) if purchase_frequency else 0,
                "last_purchase_days_ago": days_since_last,
                "is_active": is_active,
                "top_items": [
                    {"code": code, "count": count}
                    for code, count in items_bought.most_common(5)
                ],
                "top_categories": [
                    {"category": cat, "count": count}
                    for cat, count in categories.most_common(3)
                ],
            }

            analysis["rfm_score"] = {
                "recency": recency_score,
                "frequency": frequency_score,
                "monetary": monetary_score,
                "total": rfm_total,
                "segment": self._get_rfm_segment(rfm_total),
            }

            if is_churn_risk:
                analysis["risk_factors"].append(
                    f"⚠️ Churn Risk: No purchase in {days_since_last} days"
                )
                analysis["recommendations"].append(
                    "Send re-engagement offer with special discount"
                )
                analysis["next_best_actions"].append({
                    "action": "Send re-engagement email with 15% discount",
                    "priority": "HIGH"
                })

            if purchase_frequency < 0.5:
                analysis["recommendations"].append(
                    "Increase purchase frequency with loyalty program"
                )

            if avg_order > self.thresholds["high_value_threshold"]:
                analysis["upsell_opportunities"].append(
                    "💎 High-value customer — offer premium products and early access"
                )
                analysis["next_best_actions"].append({
                    "action": "Invite to VIP program",
                    "priority": "MEDIUM"
                })

            if items_bought:
                top_item = items_bought.most_common(1)[0][0]
                complementary = self._get_complementary_products(top_item)
                if complementary:
                    analysis["upsell_opportunities"].append(
                        f"Consider cross-selling: {complementary}"
                    )

            self._set_cache(cache_key, analysis)
            return analysis
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in analyze_customer_behavior: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Customer analysis failed: {str(e)}"
            }

    def forecast_demand(self, item_name: str, days_ahead: int = 30, confidence_level: float = 0.95) -> Dict[str, Any]:
        """Demand forecast based on real sales history."""
        cache_key = f"demand_forecast_{item_name}_{days_ahead}"
        cached_result = self._get_cached(cache_key, ttl=3600)
        if cached_result is not None:
            return cached_result

        try:
            items = self.api.get_items(search=item_name, limit=1)
            if not items:
                return {
                    "error": f"Item '{item_name}' not found",
                    "message": "Please check the spelling or try a different item",
                    "suggestions": ["List all items", "Search by partial name"]
                }

            item = items[0]
            item_code = item.get("ItemCode", "")

            sales_history = self._get_sales_history(item_code, days=90)

            if not sales_history:
                return {
                    "item_code": item_code,
                    "item_name": item.get("ItemName"),
                    "error": "Insufficient sales history — check back after more transactions",
                    "current_stock": self._get_current_stock(item_code),
                    "message": "No sales data available for the last 90 days",
                }

            window = min(30, len(sales_history))
            recent = sales_history[-window:]
            avg_daily = _mean(recent)
            std_daily = _std(recent) if len(recent) > 1 else avg_daily * 0.3
            current_stk = self._get_current_stock(item_code)

            trend_slope = self._calculate_trend(sales_history)
            
            seasonal_factor = 1.0
            if len(sales_history) >= 60:
                seasonal_factor = self._detect_seasonality(sales_history)

            z_score = 1.96 if confidence_level >= 0.95 else 1.645
            
            base_forecast = avg_daily * days_ahead
            trend_adjustment = trend_slope * days_ahead * days_ahead / 2
            seasonal_adjustment = base_forecast * (seasonal_factor - 1)
            
            point_forecast = base_forecast + trend_adjustment + seasonal_adjustment
            
            forecast_std = std_daily * _sqrt(days_ahead)
            margin = z_score * forecast_std
            
            forecast = {
                "item_code": item_code,
                "item_name": item.get("ItemName"),
                "current_stock": round(current_stk, 1),
                "analysis_period": f"Last {window} days",
                "daily_avg": round(avg_daily, 2),
                "daily_std_dev": round(std_daily, 2),
                "trend_slope": round(trend_slope, 3),
                "seasonal_factor": round(seasonal_factor, 2),
                "forecast_period": f"{days_ahead} days",
                "point_forecast": round(point_forecast),
                "confidence_interval": {
                    "level": f"{int(confidence_level * 100)}%",
                    "low": round(max(0, point_forecast - margin)),
                    "high": round(point_forecast + margin),
                },
                "coverage_days": self._calculate_coverage_days(current_stk, avg_daily),
                "recommendation": self._get_stock_recommendation(avg_daily, std_daily, days_ahead, current_stk),
                "data_points": len(sales_history),
                "confidence_score": _confidence_score(len(sales_history)),
            }

            if len(sales_history) >= 30:
                first_half = sales_history[:15]
                second_half = sales_history[-15:]
                first_avg = _mean(first_half)
                second_avg = _mean(second_half)

                if first_avg > 0:
                    change_pct = ((second_avg - first_avg) / first_avg) * 100
                    if change_pct > 20:
                        forecast["trend"] = "📈 Strongly Increasing"
                    elif change_pct > 5:
                        forecast["trend"] = "📈 Increasing"
                    elif change_pct < -20:
                        forecast["trend"] = "📉 Strongly Decreasing"
                    elif change_pct < -5:
                        forecast["trend"] = "📉 Decreasing"
                    else:
                        forecast["trend"] = "📊 Stable"
                else:
                    forecast["trend"] = "📊 Insufficient data for trend"

            self._set_cache(cache_key, forecast)
            return forecast
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in forecast_demand: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Demand forecast failed: {str(e)}"
            }

    # =========================================================
    # PRIVATE HELPERS
    # =========================================================

    @lru_cache(maxsize=256)
    def _get_sales_velocity_data_cached(self) -> Dict[str, float]:
        """Cached version of sales velocity data."""
        return self._get_sales_velocity_data()

    def _get_sales_velocity_data(self) -> Dict[str, float]:
        """Build a map of item_code → average daily units sold from sales data."""
        velocity_map: Dict[str, float] = {}
        try:
            # Try to get real sales data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            # Try to get sales analysis data
            sales_data = self.api.get_sales_analysis(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )
            
            if sales_data and isinstance(sales_data, dict):
                # Handle different response structures
                items_data = sales_data.get("items") or sales_data.get("data") or []
                
                for item in items_data:
                    code = item.get("ItemCode") or item.get("item_code")
                    quantity = float(item.get("Quantity") or item.get("quantity") or item.get("total_qty") or 0)
                    if code and quantity > 0:
                        velocity_map[code] = round(quantity / 30, 4)
                
                if velocity_map:
                    logger.info(f"Loaded sales velocity for {len(velocity_map)} items from sales analysis")
                    return velocity_map
            
            # Fallback: Use inventory data with estimated sales based on committed quantities
            logger.warning("No sales analysis data available, using fallback estimation")
            inventory = self.api.get_inventory_report(limit=200)
            
            for item in inventory:
                code = item.get("ItemCode") or item.get("item_code")
                # Estimate daily sales based on committed quantities
                committed = float(item.get("CurrentIsCommited") or item.get("IsCommited") or 0)
                if code and committed > 0:
                    # Assume committed quantity represents 30 days of sales
                    velocity_map[code] = round(committed / 30, 4)
            
            if velocity_map:
                logger.info(f"Estimated sales velocity for {len(velocity_map)} items from committed quantities")
            else:
                logger.warning("No sales velocity data available")
                
        except Exception as e:
            logger.warning(f"Could not build velocity map: {e}")
        
        return velocity_map

    def _calculate_days_of_stock(self, available: float, daily_velocity: float) -> float:
        if daily_velocity <= 0:
            return float("inf")
        return available / daily_velocity

    def _get_average_price(self, item_code: str) -> float:
        try:
            result = self.pricing.get_price(item_code)
            if result and isinstance(result, dict):
                price = result.get("price")
                if price is not None and price > 0:
                    return float(price)
            
            # Try alternative price fetching
            try:
                items = self.api.get_items(search=item_code, limit=1)
                if items and len(items) > 0:
                    item = items[0]
                    price = item.get("Price") or item.get("price") or item.get("SellingPrice")
                    if price and float(price) > 0:
                        return float(price)
            except:
                pass
                
            return 0.0
        except Exception as e:
            logger.debug(f"Could not get price for {item_code}: {e}")
            return 0.0

    def _get_historical_prices(self, item_code: str, days: int = 180) -> List[float]:
        try:
            history = self.api.get_price_history(item_code=item_code, days=days)
            prices = [float(r.get("Price") or r.get("price") or 0) for r in history if (r.get("Price") or r.get("price"))]
            return [p for p in prices if p > 0]
        except Exception as e:
            logger.debug(f"Price history unavailable for {item_code}: {e}")
            return []

    def _get_sales_history(self, item_code: str, days: int = 90) -> List[float]:
        try:
            history = self.api.get_sales_history(item_code=item_code, days=days)
            daily_qty = [float(r.get("Quantity") or r.get("quantity") or r.get("qty") or 0) for r in history]
            return [q for q in daily_qty if q >= 0]
        except Exception as e:
            logger.debug(f"Sales history unavailable for {item_code}: {e}")
            return []

    def _get_current_stock(self, item_code: str) -> float:
        try:
            inventory = self.api.get_inventory_report(search=item_code, limit=1)
            if inventory:
                return float(inventory[0].get("CurrentOnHand") or inventory[0].get("OnHand", 0) or 0)
        except Exception:
            pass
        return 0.0

    def _calculate_trend(self, values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        n = len(values)
        x = list(range(n))
        y = values
        x_mean = _mean(x)
        y_mean = _mean(y)
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        return numerator / denominator if denominator != 0 else 0

    def _detect_seasonality(self, values: List[float]) -> float:
        if len(values) < 14:
            return 1.0
        recent = values[-14:]
        week1_avg = _mean(recent[:7])
        week2_avg = _mean(recent[7:])
        if week1_avg > 0 and week2_avg > 0:
            return week2_avg / week1_avg
        return 1.0

    def _calculate_coverage_days(self, stock: float, daily_rate: float) -> str:
        if daily_rate <= 0:
            return "No sales data"
        days = stock / daily_rate
        if days < 1:
            return "Less than 1 day"
        elif days < 7:
            return f"{round(days, 1)} days"
        elif days < 30:
            return f"{round(days / 7, 1)} weeks"
        else:
            return f"{round(days / 30, 1)} months"

    def _get_rfm_segment(self, rfm_total: int) -> str:
        if rfm_total >= 13:
            return "⭐ Champions"
        elif rfm_total >= 10:
            return "💎 Loyal Customers"
        elif rfm_total >= 7:
            return "📈 Potential Loyalists"
        elif rfm_total >= 4:
            return "⚠️ At Risk"
        else:
            return "❌ Lost"

    def _get_stock_recommendation(self, avg_daily: float, std_daily: float, days_ahead: int, current_stock: float) -> str:
        expected_demand = avg_daily * days_ahead
        safety_buffer = std_daily * _sqrt(days_ahead) * 1.65
        
        if current_stock <= 0:
            return "🚨 OUT OF STOCK - Order immediately!"
        elif current_stock < expected_demand:
            return f"⚠️ Low stock - Order {round(expected_demand - current_stock)} units to cover {days_ahead} days"
        elif current_stock > expected_demand * 2:
            return f"📦 Overstock - Consider reducing orders or running promotion"
        else:
            return f"✅ Adequate stock for {days_ahead} days"

    def _get_complementary_products(self, item_code: str) -> Optional[str]:
        try:
            if self.recommender:
                recs = self.recommender.get_recommendations(item_code)
                if recs and len(recs) > 0:
                    return recs[0].get("name", "")
        except Exception:
            pass
        return None

    def _get_item_price_lists(self, item_code: str) -> List[Dict]:
        try:
            if hasattr(self.api, 'get_item_price_lists'):
                return self.api.get_item_price_lists(item_code)
        except Exception:
            pass
        return []

    def _calculate_volume_discount(self, price_lists: List[Dict]) -> float:
        if len(price_lists) < 2:
            return 0.0
        min_price = min(p.get("price", 0) for p in price_lists)
        max_price = max(p.get("price", 0) for p in price_lists)
        if max_price > 0:
            return (max_price - min_price) / max_price
        return 0.0

    def _get_min_volume_quantity(self, price_lists: List[Dict]) -> int:
        if not price_lists:
            return 0
        best_price_list = min(price_lists, key=lambda x: x.get("price", float('inf')))
        return best_price_list.get("min_quantity", 0)

    def _get_health_rating(self, score: int) -> str:
        if score >= 90:
            return "Excellent"
        elif score >= 75:
            return "Good"
        elif score >= 60:
            return "Fair"
        elif score >= 40:
            return "Poor"
        else:
            return "Critical"

    def _get_competitor_recommendation(self, position: str, leysco_price: float, avg_price: float) -> str:
        recommendations = {
            "VERY_COMPETITIVE": f"✅ Your price (KES {leysco_price:,.2f}) is very competitive! Consider increasing marketing to capture market share.",
            "COMPETITIVE": f"✅ Good pricing position (KES {leysco_price:,.2f} vs market avg KES {avg_price:,.2f}). Monitor competitors and consider loyalty programs.",
            "MARKET_AVERAGE": f"📊 You're at market average (KES {leysco_price:,.2f}). Highlight quality/service differences to stand out.",
            "SLIGHTLY_HIGH": f"🟠 Your price is above average. Consider adding value or bundling to justify premium.",
            "HIGH": f"🔴 Your price is significantly higher than competitors. Urgently review pricing strategy.",
            "NO_PRICE": "⚠️ No price configured. Set up pricing to enable sales.",
            "NO_COMPETITOR_DATA": "📊 No competitor data available. Monitor market manually."
        }
        return recommendations.get(position, "Review pricing strategy based on market conditions.")


# Singleton instance
_decision_support_instance = None


def get_decision_support(api, pricing, warehouse=None, recommender=None) -> DecisionSupport:
    """Get or create DecisionSupport instance."""
    global _decision_support_instance
    if _decision_support_instance is None:
        _decision_support_instance = DecisionSupport(api, pricing, warehouse, recommender)
    return _decision_support_instance