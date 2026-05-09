"""
app/services/pricing_intelligence_service.py
=============================================
Combined Pricing Intelligence Service

Provides competitor price comparison for items, returning ALL variants
with Leysco prices vs competitor prices in a format similar to item price.

MODIFIED FOR PHASE 1: Accepts user token and passes to all services
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from app.services.competitor_api_service import CompetitorAPIService
from app.services.leysco_api_service import LeyscoAPIService, create_api_service
from app.services.pricing_service import PricingService, create_pricing_service

logger = logging.getLogger(__name__)


class PricingIntelligenceService:
    """
    Combines Leysco pricing with competitor intelligence.
    Returns all item variants with their Leysco prices and competitor comparisons.
    
    MODIFIED: Now accepts user_token to properly authenticate API calls.
    """

    def __init__(self, user_token: str = None):
        """
        Initialize PricingIntelligenceService with user token.
        
        Args:
            user_token: Bearer token from authenticated user
        """
        self.user_token = user_token
        
        # Create API services with the user token
        if user_token:
            self.leysco_api = create_api_service(user_token)
            self.pricing_service = create_pricing_service(user_token)
            logger.debug("PricingIntelligenceService initialized with user token")
        else:
            logger.warning("PricingIntelligenceService initialized WITHOUT user token - API calls will fail")
            self.leysco_api = LeyscoAPIService()
            self.pricing_service = PricingService()
        
        self.competitor_api = CompetitorAPIService()
    
    def set_user_token(self, token: str):
        """Update user token for this instance."""
        self.user_token = token
        self.leysco_api.set_user_token(token)
        self.pricing_service.set_user_token(token)
        logger.debug("PricingIntelligenceService user token updated")
    
    def get_complete_pricing_picture(self, item_name: str, item_code: str = None) -> Dict:
        """
        Get complete pricing picture including ALL Leysco item variants and competitor comparisons.
        
        Returns a structured response similar to item price format:
        {
            "item_name": "vegimax",
            "variants": [
                {
                    "item_code": "KAVGX001",
                    "item_name": "VEGIMAX-10ML",
                    "leysco_price": 0.00,
                    "currency": "KES",
                    "price_list": "Standard",
                    "competitor_prices": [...],
                    "market_position": "No price configured"
                },
                ...
            ],
            "summary": {
                "total_variants": 5,
                "variants_with_prices": 4,
                "best_competitor": "Twiga Foods",
                "average_competitor_price": 525.00
            },
            "recommendations": [...]
        }
        """
        # Get ALL items matching the search (not just first one)
        items = self.leysco_api.get_items(search=item_name, limit=30)
        
        if not items:
            return {
                "error": True,
                "message": f"Item '{item_name}' not found in Leysco system",
                "suggestions": ["Check spelling", "Try a different name", "Show me items to browse"]
            }
        
        # Process all variants
        variants = []
        total_priced = 0
        total_leysco_value = 0
        all_competitor_prices = []
        
        for item in items:
            variant_code = item.get("ItemCode")
            variant_name = item.get("ItemName")
            
            if not variant_code:
                continue
            
            # Get Leysco price for this variant
            leysco_price_info = self._get_leysco_price(variant_code)
            
            # Get competitor prices for this variant
            competitor_prices = self.competitor_api.get_competitor_prices(variant_name, variant_code)
            
            # Filter valid competitor prices
            valid_competitor_prices = [p for p in competitor_prices if p.get("price", 0) > 0]
            
            # Track for summary
            if leysco_price_info and leysco_price_info.get("price", 0) > 0:
                total_priced += 1
                total_leysco_value += leysco_price_info["price"]
            
            for cp in valid_competitor_prices:
                all_competitor_prices.append(cp.get("price", 0))
            
            # Determine market position
            market_position = self._determine_market_position(
                leysco_price_info.get("price", 0) if leysco_price_info else 0,
                valid_competitor_prices
            )
            
            variants.append({
                "item_code": variant_code,
                "item_name": variant_name,
                "leysco_price": leysco_price_info.get("price", 0) if leysco_price_info else 0,
                "currency": leysco_price_info.get("currency", "KES") if leysco_price_info else "KES",
                "price_list": leysco_price_info.get("price_list", "Standard") if leysco_price_info else "Not configured",
                "is_gross_price": leysco_price_info.get("includes_vat", True) if leysco_price_info else True,
                "competitor_prices": valid_competitor_prices[:5],  # Top 5 competitor prices
                "competitor_count": len(valid_competitor_prices),
                "lowest_competitor_price": min([p.get("price", 0) for p in valid_competitor_prices]) if valid_competitor_prices else None,
                "highest_competitor_price": max([p.get("price", 0) for p in valid_competitor_prices]) if valid_competitor_prices else None,
                "average_competitor_price": sum(p.get("price", 0) for p in valid_competitor_prices) / len(valid_competitor_prices) if valid_competitor_prices else None,
                "market_position": market_position,
                "savings_vs_average": round(leysco_price_info.get("price", 0) - (sum(p.get("price", 0) for p in valid_competitor_prices) / len(valid_competitor_prices)), 2) if valid_competitor_prices and leysco_price_info.get("price", 0) > 0 else None,
                "recommendation": self._get_variant_recommendation(market_position, leysco_price_info.get("price", 0) if leysco_price_info else 0, valid_competitor_prices)
            })
        
        # Calculate summary statistics
        avg_competitor_price = sum(all_competitor_prices) / len(all_competitor_prices) if all_competitor_prices else 0
        best_competitor = self._find_best_competitor(all_competitor_prices) if all_competitor_prices else None
        
        # Generate overall recommendations
        recommendations = self._generate_recommendations(variants, avg_competitor_price)
        
        # Format for response
        return {
            "item_name": item_name,
            "variants": variants,
            "summary": {
                "total_variants": len(variants),
                "variants_with_prices": total_priced,
                "average_leysco_price": total_leysco_value / total_priced if total_priced > 0 else 0,
                "average_competitor_price": round(avg_competitor_price, 2),
                "best_competitor": best_competitor,
                "total_competitor_sources": len(all_competitor_prices),
                "price_advantage": round((avg_competitor_price - (total_leysco_value / total_priced if total_priced > 0 else 0)) / avg_competitor_price * 100, 1) if avg_competitor_price > 0 and total_priced > 0 else 0
            },
            "recommendations": recommendations,
            "timestamp": datetime.now().isoformat()
        }
    
    def _get_leysco_price(self, item_code: str) -> Optional[Dict]:
        """
        Get Leysco's current price for an item using the pricing service.
        Now returns ALL price lists for the item.
        """
        try:
            # Use the pricing service to get price
            price_result = self.pricing_service.get_price(item_code)
            
            if not price_result or not price_result.get("found"):
                logger.debug(f"No price found for item {item_code}")
                return None
            
            return {
                "price": price_result.get("price"),
                "currency": price_result.get("currency", "KES"),
                "price_list": price_result.get("price_list_name", "Standard"),
                "price_list_id": price_result.get("price_list_id"),
                "sap_list_num": price_result.get("sap_list_num"),
                "includes_vat": price_result.get("is_gross_price", True),
                "uom_entry": price_result.get("uom_entry"),
                "note": price_result.get("note", ""),
                "chain_walked": price_result.get("chain_walked", [])
            }
        except Exception as e:
            logger.error(f"Error getting Leysco price for {item_code}: {e}")
            return None
    
    def _determine_market_position(self, leysco_price: float, competitor_prices: List[Dict]) -> str:
        """Determine Leysco's market position based on competitor prices."""
        if leysco_price <= 0:
            return "No price configured"
        
        if not competitor_prices:
            return "No competitor data available"
        
        prices = [p.get("price", 0) for p in competitor_prices if p.get("price", 0) > 0]
        if not prices:
            return "No competitor price data"
        
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        
        if leysco_price < min_price * 0.95:
            return "🟢 Very Competitive - Lowest price in market"
        elif leysco_price < avg_price * 0.95:
            return "🟢 Competitive - Below market average"
        elif leysco_price <= avg_price * 1.05:
            return "🟡 Market Average - Competitive"
        elif leysco_price <= avg_price * 1.15:
            return "🟠 Slightly High - Above market average"
        else:
            return "🔴 High - Significantly above competitors"
    
    def _get_variant_recommendation(self, market_position: str, leysco_price: float, competitor_prices: List[Dict]) -> str:
        """Get recommendation for a specific variant."""
        if leysco_price <= 0:
            return "⚠️ No price configured. Contact sales team to set pricing."
        
        if not competitor_prices:
            return "📊 No competitor data available. Monitor market manually."
        
        if "Very Competitive" in market_position:
            return "✅ Excellent price position. Highlight in marketing and consider volume promotions."
        elif "Competitive - Below" in market_position:
            return "✅ Good price position. Maintain and monitor competitors."
        elif "Market Average" in market_position:
            return "📊 At market average. Consider differentiating on service or quality."
        elif "Slightly High" in market_position:
            return "⚠️ Price is above market. Consider adjusting or adding value."
        elif "High" in market_position:
            return "🔴 URGENT: Price is significantly higher. Review pricing strategy immediately."
        
        return "📊 Monitor market and adjust pricing as needed."
    
    def _find_best_competitor(self, all_prices: List[float]) -> Optional[str]:
        """Find the competitor with the best prices overall."""
        if not all_prices:
            return None
        
        # This would ideally map prices to competitors
        # For now, return a generic best competitor
        return "Multiple competitors (check variant details)"
    
    def _generate_recommendations(self, variants: List[Dict], avg_competitor_price: float) -> List[str]:
        """Generate overall pricing recommendations."""
        recommendations = []
        
        # Count variants in different positions
        high_count = sum(1 for v in variants if "🔴 High" in v.get("market_position", ""))
        slightly_high_count = sum(1 for v in variants if "🟠 Slightly High" in v.get("market_position", ""))
        competitive_count = sum(1 for v in variants if "🟢" in v.get("market_position", ""))
        no_price_count = sum(1 for v in variants if v.get("leysco_price", 0) <= 0)
        
        if high_count > 0:
            recommendations.append(f"🔴 {high_count} variant(s) are significantly overpriced. Immediate review needed.")
        
        if slightly_high_count > 0:
            recommendations.append(f"🟠 {slightly_high_count} variant(s) are above market average. Consider price adjustment.")
        
        if no_price_count > 0:
            recommendations.append(f"⚠️ {no_price_count} variant(s) have no price configured. Set up pricing to enable sales.")
        
        if competitive_count > 0 and not high_count:
            recommendations.append(f"✅ {competitive_count} variant(s) are competitively priced. Maintain current strategy.")
        
        # General recommendations
        if avg_competitor_price > 0:
            recommendations.append(f"📊 Average competitor price across variants: KES {avg_competitor_price:,.2f}")
        
        recommendations.append("💡 Tip: Use competitor price intelligence to negotiate with customers and adjust promotions.")
        
        return recommendations[:5]  # Limit to 5 recommendations
    
    def get_single_item_comparison(self, item_code: str, customer_name: str = None) -> Dict:
        """
        Get competitor price comparison for a single item (by item code).
        Useful for quick lookups.
        """
        # Get item details
        item = self.leysco_api.get_item_by_code(item_code)
        if not item:
            return {
                "error": True,
                "message": f"Item with code '{item_code}' not found"
            }
        
        item_name = item.get("ItemName")
        
        # Get Leysco price
        if customer_name:
            customer = self.leysco_api.get_customer_by_name(customer_name)
            if customer:
                leysco_price = self.pricing_service.get_price_for_customer(item_code, customer)
            else:
                leysco_price = self.pricing_service.get_price(item_code)
        else:
            leysco_price = self.pricing_service.get_price(item_code)
        
        # Get competitor prices
        competitor_prices = self.competitor_api.get_competitor_prices(item_name, item_code)
        
        # Filter valid prices
        valid_prices = [p for p in competitor_prices if p.get("price", 0) > 0]
        
        return {
            "item_code": item_code,
            "item_name": item_name,
            "leysco_price": leysco_price.get("price") if leysco_price and leysco_price.get("found") else None,
            "competitor_prices": valid_prices[:10],
            "competitor_count": len(valid_prices),
            "lowest_competitor_price": min([p.get("price", 0) for p in valid_prices]) if valid_prices else None,
            "average_competitor_price": sum(p.get("price", 0) for p in valid_prices) / len(valid_prices) if valid_prices else None,
            "recommendation": self._get_variant_recommendation(
                self._determine_market_position(
                    leysco_price.get("price") if leysco_price and leysco_price.get("found") else 0,
                    valid_prices
                ),
                leysco_price.get("price") if leysco_price and leysco_price.get("found") else 0,
                valid_prices
            ),
            "timestamp": datetime.now().isoformat()
        }
    
    def _guess_category(self, item_name: str) -> str:
        """Guess category from item name."""
        if not item_name:
            return "default"
            
        item_lower = item_name.lower()
        
        vegetables = ["cabbage", "tomato", "onion", "potato", "carrot", "kale", "spinach", "capsicum"]
        fruits = ["mango", "banana", "apple", "orange", "pineapple", "avocado", "lemon", "lime"]
        grains = ["maize", "wheat", "rice", "beans", "peas", "lentils", "soy"]
        dairy = ["milk", "cheese", "yogurt", "butter", "cream"]
        meat = ["beef", "chicken", "goat", "lamb", "pork", "fish"]
        
        if any(v in item_lower for v in vegetables):
            return "vegetables"
        elif any(f in item_lower for f in fruits):
            return "fruits"
        elif any(g in item_lower for g in grains):
            return "grains"
        elif any(d in item_lower for d in dairy):
            return "dairy"
        elif any(m in item_lower for m in meat):
            return "meat"
        
        return "default"


# =========================================================
# Factory function to create PricingIntelligenceService with user token
# =========================================================

def create_pricing_intelligence_service(user_token: str = None) -> PricingIntelligenceService:
    """
    Create a PricingIntelligenceService instance with the user's token.
    
    Args:
        user_token: The authenticated user's Bearer token
    
    Returns:
        Configured PricingIntelligenceService instance
    """
    if not user_token:
        logger.warning("⚠️ create_pricing_intelligence_service called WITHOUT user token - data access will fail")
    else:
        logger.info("✅ create_pricing_intelligence_service called WITH user token")
    
    return PricingIntelligenceService(user_token=user_token)