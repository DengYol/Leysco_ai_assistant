"""
app/services/pricing_intelligence_service.py
=============================================
Combined Pricing Intelligence Service
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime  # ADD THIS IMPORT
from app.services.competitor_api_service import CompetitorAPIService
from app.services.leysco_api_service import LeyscoAPIService

logger = logging.getLogger(__name__)


class PricingIntelligenceService:
    """
    Combines Leysco pricing with competitor intelligence
    """
    
    def __init__(self):
        self.leysco_api = LeyscoAPIService()
        self.competitor_api = CompetitorAPIService()
    
    def get_complete_pricing_picture(self, item_name: str, item_code: str = None) -> Dict:
        """
        Get complete pricing picture including Leysco price and competitor comparison
        """
        # Get Leysco item details
        items = self.leysco_api.get_items(search=item_name, limit=1)
        if not items:
            return {
                "error": True,
                "message": f"Item '{item_name}' not found in Leysco system"
            }
        
        item = items[0]
        item_code = item.get("ItemCode")
        item_name = item.get("ItemName")
        
        # Get Leysco price (you'll need to implement this)
        leysco_price = self._get_leysco_price(item_code)
        
        if not leysco_price:
            return {
                "error": True,
                "message": f"Could not determine price for {item_name}"
            }
        
        # Get competitor prices
        competitor_prices = self.competitor_api.get_competitor_prices(item_name, item_code)
        
        # Get comparison
        comparison = self.competitor_api.compare_with_leysco(
            leysco_price=leysco_price["price"],
            item_name=item_name,
            item_code=item_code
        )
        
        # Get market intelligence
        market_intel = self.competitor_api.get_market_intelligence(
            category=self._guess_category(item_name)
        )
        
        return {
            "item": {
                "code": item_code,
                "name": item_name,
                "description": item.get("ItemDescription", ""),
                "group": item.get("ItemsGroupCode"),
            },
            "leysco_price": leysco_price,
            "competitor_analysis": comparison,
            "market_intelligence": market_intel,
            "price_history": self.competitor_api.get_price_history(item_name),
            "recommendations": self._generate_recommendations(comparison, market_intel),
            "timestamp": datetime.now().isoformat(),
        }
    
    def _get_leysco_price(self, item_code: str) -> Optional[Dict]:
        """
        Get Leysco's current price for an item
        """
        # Implement your price lookup logic here
        # This could come from price lists, customer-specific pricing, etc.
        
        # Placeholder - replace with actual implementation
        return {
            "price": 250.0,
            "currency": "KES",
            "price_list": "Standard Retail",
            "valid_from": "2024-01-01",
            "includes_vat": True
        }
    
    def _guess_category(self, item_name: str) -> str:
        """Guess category from item name"""
        # Use the same logic as competitor_api_service
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
    
    def _generate_recommendations(self, comparison: Dict, market_intel: Dict) -> List[str]:
        """Generate actionable pricing recommendations"""
        recommendations = []
        
        # Based on competitive position
        position = comparison.get("competitive_position")
        if position == "HIGH":
            recommendations.append("🔴 URGENT: Review pricing strategy - your price is significantly higher than competitors")
        elif position == "SLIGHTLY_HIGH":
            recommendations.append("🟡 Consider price adjustment or enhance value proposition")
        elif position == "MARKET_AVERAGE":
            recommendations.append("🟢 Monitor competitor promotions and consider loyalty programs")
        elif position == "COMPETITIVE":
            recommendations.append("✅ Good position - highlight this in marketing")
        
        # Based on market intelligence
        if market_intel and market_intel.get("opportunities"):
            recommendations.extend([f"💡 {opp}" for opp in market_intel["opportunities"][:2]])
        
        return recommendations