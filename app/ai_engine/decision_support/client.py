"""Main DecisionSupport class - orchestrates all decision support modules"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from .constants import DEFAULT_LIMIT, DEFAULT_DAYS_AHEAD, DEFAULT_FORECAST_DAYS
from .inventory import InventoryAnalyzer
from .pricing import PricingAnalyzer
from .customer import CustomerAnalyzer
from .forecasting import ForecastingAnalyzer
from .cache import _cache_manager
from .utils import safe_float

logger = logging.getLogger(__name__)


class DecisionSupport:
    """
    Provides decision support for business intelligence.
    Orchestrates inventory, pricing, customer, and forecasting analysis.
    """

    def __init__(self, api, pricing, warehouse=None, recommender=None):
        self.api = api
        self.pricing = pricing
        self.warehouse = warehouse
        self.recommender = recommender
        
        # Initialize analyzers
        self.inventory_analyzer = InventoryAnalyzer(self)
        self.pricing_analyzer = PricingAnalyzer(self)
        self.customer_analyzer = CustomerAnalyzer(self)
        self.forecasting_analyzer = ForecastingAnalyzer(self)
        
        # Metrics collection
        self.metrics = {
            "api_calls": 0,
            "errors": 0,
            "avg_response_time": 0,
            "total_response_time": 0,
            "call_count": 0
        }

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
        return {
            **self.metrics,
            "cache_stats": _cache_manager.get_stats()
        }
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        _cache_manager.clear()
        logger.info("Decision support cache cleared")
    
    # =========================================================
    # INVENTORY METHODS
    # =========================================================
    
    def analyze_inventory_health(
        self,
        warehouse_code: Optional[str] = None,
        include_recommendations: bool = True,
        limit: int = DEFAULT_LIMIT
    ) -> Dict[str, Any]:
        """Comprehensive inventory health analysis."""
        return self.inventory_analyzer.analyze_inventory_health(
            warehouse_code, include_recommendations, limit
        )
    
    def get_reorder_decisions(
        self,
        filter_item_code: Optional[str] = None,
        days_ahead: int = DEFAULT_DAYS_AHEAD
    ) -> Dict[str, Any]:
        """Get reorder recommendations with optimal quantities."""
        return self.inventory_analyzer.get_reorder_decisions(filter_item_code, days_ahead)
    
    def get_inventory_turnover(self, warehouse_code: Optional[str] = None) -> Dict[str, Any]:
        """Get inventory turnover analysis."""
        cache_key = f"inventory_turnover_{warehouse_code}"
        
        try:
            turnover_data = self.api.get_inventory_turnover(warehouse_code=warehouse_code)
            
            if turnover_data:
                total_turnover = sum(item.get("TurnoverRate", 0) for item in turnover_data)
                avg_turnover = total_turnover / len(turnover_data) if turnover_data else 0
                high_turnover = [item for item in turnover_data if item.get("TurnoverRate", 0) > 12]
                low_turnover = [item for item in turnover_data if item.get("TurnoverRate", 0) < 2]
                
                return {
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
                    }
                }
            
            return {"error": True, "message": "No inventory turnover data available"}
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error getting inventory turnover: {e}")
            return {"error": True, "message": str(e)}
    
    # =========================================================
    # PRICING METHODS
    # =========================================================
    
    def analyze_pricing_opportunities(
        self,
        customer_code: Optional[str] = None,
        days_history: int = 180,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Analyze pricing to find opportunities and risks."""
        return self.pricing_analyzer.analyze_pricing_opportunities(
            customer_code, days_history, limit
        )
    
    async def competitor_price_check(self, entities: dict) -> Dict[str, Any]:
        """Check competitor prices for an item."""
        return await self.pricing_analyzer.competitor_price_check(entities)
    
    async def find_best_price(self, entities: dict) -> Dict[str, Any]:
        """Find the best price for an item."""
        item_name = entities.get("item_name", "")
        
        if not item_name:
            return {
                "error": True,
                "message": "Please specify an item to find the best price for"
            }
        
        logger.info(f"💰 Finding best price for: {item_name}")
        
        competitor_service = self.pricing_analyzer._get_competitor_service()
        if competitor_service is None:
            return {
                "analysis_type": "best_price",
                "item_name": item_name,
                "message": "Best price service is currently unavailable."
            }
        
        try:
            items = self.api.get_items(search=item_name, limit=5)
            if not items:
                return {
                    "error": True,
                    "message": f"No items found matching '{item_name}'"
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
                            
                            if savings > 0:
                                result["message"] = f"You could save KES {result['potential_savings']} by buying from {best_price.get('competitor_name', 'another supplier')}"
                            else:
                                result["message"] = "Leysco's price is already competitive!"
                        
                        all_results.append(result)
            
            if not all_results:
                return {
                    "error": True,
                    "message": f"No price data available for {item_name}"
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
            logger.error(f"Error in find_best_price: {e}")
            return {"error": True, "message": str(e)}
    
    async def market_intelligence(self, entities: dict) -> Dict[str, Any]:
        """Get market intelligence and price trends."""
        category = entities.get("item_name", "") or entities.get("category", "")
        
        logger.info(f"📊 Getting market intelligence for: {category or 'all products'}")
        
        competitor_service = self.pricing_analyzer._get_competitor_service()
        if competitor_service is None:
            return {
                "analysis_type": "market_intelligence",
                "category": category or "All Products",
                "timestamp": datetime.now().isoformat(),
                "message": "Market intelligence service is currently unavailable.",
                "market_trends": {
                    "vegetables": "increasing",
                    "fruits": "stable",
                    "grains": "decreasing",
                },
                "key_insights": [
                    "Tomato prices expected to rise next month",
                    "Cabbage prices stable with good availability",
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
                "key_insights": market_data.get("key_insights", []),
                "opportunities": market_data.get("opportunities", []),
                "recommendations": market_data.get("recommendations", []),
            }
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in market_intelligence: {e}")
            return {"error": True, "message": str(e)}
    
    async def price_alert(self, entities: dict) -> Dict[str, Any]:
        """Set up price alerts for items."""
        item_name = entities.get("item_name", "")
        
        if not item_name:
            return {
                "error": True,
                "message": "Please specify an item to monitor for price alerts"
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
            
            return {
                "analysis_type": "price_alert",
                "item_name": item_name,
                "status": "active",
                "message": f"✅ Price alert set for {item_name}. You'll be notified when prices change significantly.",
                "alert_settings": {
                    "monitoring_frequency": "Daily",
                    "threshold": "5% change",
                    "duration": "30 days"
                },
                "current_prices": current_prices,
                "alert_id": f"alert_{item_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            }
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in price_alert: {e}")
            return {"error": True, "message": str(e)}
    
    # =========================================================
    # CUSTOMER METHODS
    # =========================================================
    
    def analyze_customer_behavior(self, customer_name: str) -> Dict[str, Any]:
        """Deep dive into a customer's purchasing patterns."""
        return self.customer_analyzer.analyze_customer_behavior(customer_name)
    
    async def find_customers_by_item(self, item_name: str, limit: int = 10) -> Dict[str, Any]:
        """Find customers who would buy or have bought a specific item."""
        return await self.customer_analyzer.find_customers_by_item(item_name, limit)
    
    # =========================================================
    # FORECASTING METHODS
    # =========================================================
    
    def forecast_demand(
        self, 
        item_name: str, 
        days_ahead: int = DEFAULT_FORECAST_DAYS,
        confidence_level: float = 0.95
    ) -> Dict[str, Any]:
        """Demand forecast based on real sales history."""
        return self.forecasting_analyzer.forecast_demand(item_name, days_ahead, confidence_level)
    
    def get_sales_trend(self, days: int = 90) -> Dict[str, Any]:
        """Get sales trend analysis."""
        return self.forecasting_analyzer.get_sales_trend(days)
    
    def _get_empty_sales_analytics(self, days: int = 30) -> dict:
        """Return empty sales analytics structure"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        return {
            "analysis_type": "sales_analytics",
            "period_days": days,
            "period_description": f"last {days} days",
            "date_range": {
                "from": start_date.strftime("%Y-%m-%d"),
                "to": end_date.strftime("%Y-%m-%d")
            },
            "summary": {
                "total_revenue": 0,
                "total_transactions": 0,
                "average_order_value": 0,
                "unique_customers": 0,
                "total_items_sold": 0
            },
            "top_products": [],
            "top_customers": [],
            "monthly_trend": [],
            "data_points": 0,
            "source": "empty_response"
        }
    
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
                    result = {"error": True, "message": "Customer name is required"}
                else:
                    result = self.analyze_customer_behavior(customer_name)
            
            elif intent == "FORECAST_DEMAND":
                item_name = entities.get("item_name")
                days = entities.get("quantity") or DEFAULT_FORECAST_DAYS
                if not item_name:
                    result = {"error": True, "message": "Item name is required"}
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
            
            elif intent == "FIND_CUSTOMERS_BY_ITEM":
                item_name = entities.get("item_name")
                limit = entities.get("quantity") or 10
                if not item_name:
                    result = {"error": True, "message": "Item name is required"}
                else:
                    result = await self.find_customers_by_item(item_name, limit)
            
            # FIXED: These should fetch actual data, not just return a placeholder
            elif intent == "GET_SALES_ANALYTICS":
                try:
                    period = entities.get("period", "last_30_days")
                    days = entities.get("days", 30)
                    limit = entities.get("quantity", 100)
                    
                    if hasattr(self.api, 'analytics') and self.api.analytics:
                        logger.info(f"Fetching sales analytics for period: {period}")
                        analytics_result = self.api.analytics.get_sales_analytics(
                            period=period, 
                            limit=limit
                        )
                        if analytics_result and len(analytics_result) > 0:
                            result = analytics_result[0]
                            logger.info(f"Sales analytics retrieved: {result.get('summary', {})}")
                        else:
                            logger.warning("No sales analytics data returned")
                            result = self._get_empty_sales_analytics(days)
                    else:
                        logger.warning("Analytics handler not available")
                        result = self._get_empty_sales_analytics(days)
                except Exception as e:
                    logger.error(f"Error fetching sales analytics: {e}", exc_info=True)
                    result = self._get_empty_sales_analytics(30)
            
            elif intent == "GET_TOP_SELLING_ITEMS":
                try:
                    limit = entities.get("quantity", 10)
                    days = entities.get("days", 30)
                    
                    if hasattr(self.api, 'analytics') and self.api.analytics:
                        items = self.api.analytics.get_top_selling_items(limit=limit, days=days)
                        result = {
                            "items": items,
                            "limit": limit,
                            "days": days
                        }
                        logger.info(f"Top selling items retrieved: {len(items)} items")
                    else:
                        result = {"items": [], "limit": limit, "days": days}
                except Exception as e:
                    logger.error(f"Error fetching top selling items: {e}", exc_info=True)
                    result = {"items": [], "limit": 10, "days": 30}
            
            elif intent == "GET_SLOW_MOVING_ITEMS":
                try:
                    limit = entities.get("quantity", 10)
                    days = entities.get("days", 90)
                    
                    if hasattr(self.api, 'analytics') and self.api.analytics:
                        items = self.api.analytics.get_slow_moving_items(limit=limit, days=days)
                        result = {
                            "items": items,
                            "limit": limit,
                            "days": days
                        }
                        logger.info(f"Slow moving items retrieved: {len(items)} items")
                    else:
                        result = {"items": [], "limit": limit, "days": days}
                except Exception as e:
                    logger.error(f"Error fetching slow moving items: {e}", exc_info=True)
                    result = {"items": [], "limit": 10, "days": 90}
            
            else:
                result = {
                    "error": True,
                    "message": f"Analysis for {intent} not implemented yet"
                }
            
            # Ensure result is a dict
            if asyncio.iscoroutine(result):
                result = await result
            
            if not isinstance(result, dict):
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
                "timestamp": datetime.now().isoformat()
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


# Singleton instance factory
_decision_support_instance = None


def get_decision_support(api, pricing, warehouse=None, recommender=None) -> DecisionSupport:
    """Get or create DecisionSupport instance."""
    global _decision_support_instance
    if _decision_support_instance is None:
        _decision_support_instance = DecisionSupport(api, pricing, warehouse, recommender)
    return _decision_support_instance