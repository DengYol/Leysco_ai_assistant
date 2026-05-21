"""Pricing analysis and competitor price support"""

import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

from .constants import THRESHOLDS, CACHE_TTL, COMPETITOR_RECOMMENDATIONS
from .utils import mean, std_dev, sqrt, confidence_score, get_competitor_recommendation
from .cache import cached

logger = logging.getLogger(__name__)


class PricingAnalyzer:
    """Handles pricing opportunities and competitor analysis"""
    
    def __init__(self, parent):
        self.parent = parent
        self.api = parent.api
        self.pricing = parent.pricing
        self._competitor_service = None
    
    def _get_competitor_service(self):
        """Lazy load competitor service."""
        if self._competitor_service is None:
            try:
                from app.services.competitor_api_service import get_competitor_pricing_service
                self._competitor_service = get_competitor_pricing_service()
            except Exception as e:
                logger.warning(f"Competitor service unavailable: {e}")
        return self._competitor_service
    
    @cached("pricing_opportunities")
    def analyze_pricing_opportunities(
        self,
        customer_code: Optional[str] = None,
        days_history: int = 180,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Analyze pricing to find opportunities and risks."""
        
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
                    avg_price = mean(historical_prices)
                    min_price = min(historical_prices)
                    max_price = max(historical_prices)
                    price_std = std_dev(historical_prices)
                    
                    if avg_price and avg_price > 0:
                        price_change = (current_price - avg_price) / avg_price
                    else:
                        price_change = None
                    
                    conf = confidence_score(len(historical_prices))

                    if price_change is not None and price_change < -THRESHOLDS["price_drop_threshold"]:
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
                            "confidence": conf,
                            "action": "Good time to stock up",
                            "priority": "HIGH" if price_change < -0.25 else "MEDIUM",
                        })
                    elif price_change is not None and price_change > THRESHOLDS["price_hike_threshold"]:
                        price_hike_count += 1
                        opportunities["price_hikes"].append({
                            "code": item_code,
                            "name": item_name,
                            "current": round(current_price),
                            "avg_price": round(avg_price),
                            "min_price": round(min_price),
                            "hike_percent": round(price_change * 100, 1),
                            "volatility": round(price_std / avg_price * 100, 1) if avg_price else 0,
                            "confidence": conf,
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

            return opportunities
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Error in analyze_pricing_opportunities: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Pricing analysis failed: {str(e)}"
            }
    
    async def competitor_price_check(self, entities: dict) -> Dict[str, Any]:
        """Check competitor prices for an item."""
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
        
        competitor_service = self._get_competitor_service()
        if competitor_service is None:
            return {
                "analysis_type": "competitor_price_check",
                "item_name": item_name,
                "message": "Competitor price service is currently unavailable.",
                "status": "service_unavailable"
            }
        
        try:
            # Find sellable items
            items = self.api.get_items(search=item_name, limit=50)
            
            # Filter for sellable items only
            sellable_items = []
            for item in items:
                is_sellable = item.get("SellItem") == "Y"
                group_code = item.get("ItmsGrpCod")
                is_packaging = group_code == 3
                
                if is_sellable and not is_packaging:
                    sellable_items.append(item)
            
            if not sellable_items:
                # Try broader search
                base_name = re.sub(r'\s+\d+(?:ml|ML|mL|kg|KG|g|G|l|L)\b', '', item_name).strip()
                if base_name != item_name:
                    more_items = self.api.get_items(search=base_name, limit=50)
                    for item in more_items:
                        if item.get("SellItem") == "Y" and item.get("ItmsGrpCod") != 3:
                            if item not in sellable_items:
                                sellable_items.append(item)
            
            if not sellable_items:
                return {
                    "error": True,
                    "message": f"No sellable items found matching '{item_name}'.",
                    "suggestions": ["Try a different product name", "Browse available items"]
                }
            
            # Limit to top 3 variants
            prioritized_items = sellable_items[:3]
            all_variants = []
            
            for item in prioritized_items:
                item_code = item.get("ItemCode")
                item_display_name = item.get("ItemName", item_name)
                
                # Get Leysco's price
                leysco_price = None
                try:
                    price_result = self.pricing.get_price(item_code)
                    if price_result and price_result.get("found"):
                        leysco_price = price_result.get("price")
                except Exception as e:
                    logger.warning(f"Could not get price for {item_code}: {e}")
                
                # Get competitor prices
                try:
                    competitor_prices = await competitor_service.get_competitor_prices_async(
                        item_name=item_display_name,
                        item_code=item_code
                    )
                except Exception as e:
                    logger.warning(f"Could not fetch competitor prices: {e}")
                    competitor_prices = []
                
                valid_competitor_prices = [p for p in competitor_prices if p.get("price") and p.get("price") > 0][:3]
                
                comparison_data = None
                
                if leysco_price and leysco_price > 0:
                    if valid_competitor_prices:
                        avg_comp_price = sum(p["price"] for p in valid_competitor_prices) / len(valid_competitor_prices)
                        min_comp_price = min(p["price"] for p in valid_competitor_prices)
                        
                        if leysco_price < min_comp_price * 0.95:
                            position = "VERY_COMPETITIVE"
                        elif leysco_price < avg_comp_price * 0.95:
                            position = "COMPETITIVE"
                        elif leysco_price <= avg_comp_price * 1.05:
                            position = "MARKET_AVERAGE"
                        elif leysco_price <= avg_comp_price * 1.1:
                            position = "SLIGHTLY_HIGH"
                        else:
                            position = "HIGH"
                        
                        comparison_data = {
                            "leysco_price": leysco_price,
                            "competitive_position": position,
                            "message": get_competitor_recommendation(position, leysco_price, avg_comp_price),
                            "market_stats": {
                                "average": round(avg_comp_price, 2),
                                "lowest": round(min_comp_price, 2),
                            }
                        }
                    else:
                        comparison_data = {
                            "leysco_price": leysco_price,
                            "competitive_position": "NO_COMPETITOR_DATA",
                            "message": "No competitor price data available for this item"
                        }
                else:
                    comparison_data = {
                        "leysco_price": None,
                        "competitive_position": "NO_PRICE",
                        "message": "No price configured in Leysco system"
                    }
                
                variant_data = {
                    "item_code": item_code,
                    "item_name": item_display_name,
                    "leysco_price": leysco_price,
                    "competitor_count": len(valid_competitor_prices),
                    "competitors": valid_competitor_prices[:3],
                    "comparison": comparison_data
                }
                
                all_variants.append(variant_data)
            
            result = {
                "analysis_type": "competitor_price_check",
                "search_term": item_name,
                "variants_found": len(all_variants),
                "variants": all_variants,
                "timestamp": datetime.now().isoformat(),
            }
            
            if len(all_variants) == 1:
                result.update({
                    "item_name": all_variants[0]["item_name"],
                    "item_code": all_variants[0]["item_code"],
                    "leysco_price": all_variants[0]["leysco_price"],
                    "comparison": all_variants[0]["comparison"],
                    "competitors": all_variants[0]["competitors"],
                })
            
            return result
                
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Error in competitor_price_check: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Failed to check competitor prices: {str(e)}"
            }
    
    def _get_historical_prices(self, item_code: str, days: int = 180) -> List[float]:
        """Get historical prices for an item."""
        try:
            history = self.api.get_price_history(item_code=item_code, days=days)
            prices = [float(r.get("Price") or r.get("price") or 0) for r in history if (r.get("Price") or r.get("price"))]
            return [p for p in prices if p > 0]
        except Exception as e:
            logger.debug(f"Price history unavailable for {item_code}: {e}")
            return []