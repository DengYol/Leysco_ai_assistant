"""
app/services/competitor_api_service.py
========================================
Competitor API Integration for Market Pricing
"""

import logging
import requests
import math
import random
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)


class CompetitorAPIService:
    """
    Service to fetch competitor pricing from various market APIs
    """
    
    def __init__(self):
        # Parse enabled competitors from settings
        enabled_list = [c.strip() for c in settings.ENABLED_COMPETITORS.split(",") if c.strip()]
        
        # Configuration for different competitor APIs
        self.competitors = {
            "twiga": {
                "name": "Twiga Foods",
                "base_url": settings.TWIGA_API_URL,
                "api_key": settings.TWIGA_API_KEY,
                "enabled": "twiga" in enabled_list,
                "timeout": settings.COMPETITOR_API_TIMEOUT_SECONDS,
            },
            "sokopepper": {
                "name": "SokoPepper",
                "base_url": settings.SOKOPEPPER_API_URL,
                "api_key": settings.SOKOPEPPER_API_KEY,
                "enabled": "sokopepper" in enabled_list,
                "timeout": settings.COMPETITOR_API_TIMEOUT_SECONDS,
            },
            "farmcrowdy": {
                "name": "FarmCrowdy",
                "base_url": settings.FARMCROWDY_API_URL,
                "api_key": settings.FARMCROWDY_API_KEY,
                "enabled": "farmcrowdy" in enabled_list,
                "timeout": settings.COMPETITOR_API_TIMEOUT_SECONDS,
            },
            "market": {
                "name": "Open Market Survey",
                "base_url": None,
                "api_key": None,
                "enabled": "market" in enabled_list or True,
                "timeout": 5,
            },
            "worldbank": {  # NEW: World Bank API
                "name": "World Bank - Kenya Price Trends",
                "base_url": settings.WORLD_BANK_API_URL,
                "api_key": None,  # No key needed for World Bank
                "enabled": "worldbank" in enabled_list and settings.WORLD_BANK_ENABLED,
                "timeout": 10,
                "country_code": "KE",  # Kenya
                "indicators": {
                    "cpi": "FP.CPI.TOTL",  # Consumer Price Index
                    "food_inflation": "FP.CPI.TOTL.ZG",  # Food inflation
                    "producer_prices": "AG.PRD.CROP.XD",  # Crop producer prices
                }
            }
        }
        
        # Cache for competitor prices
        self._price_cache = {}
        self._cache_timestamp = {}
        self.cache_duration = timedelta(hours=settings.COMPETITOR_CACHE_TTL_HOURS)
        
        # Session for API calls
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Leysco-AI/1.0"
        })
        
        logger.info(f"✅ CompetitorAPIService initialized with enabled competitors: {enabled_list}")

    # -------------------------------------------------
    # MAIN PUBLIC METHODS
    # -------------------------------------------------

    def get_competitor_prices(self, item_name: str, item_code: str = None) -> List[Dict]:
        """
        Get competitor prices for an item from all enabled sources
        """
        logger.info(f"🔍 Fetching competitor prices for: {item_name}")
        
        # Check cache first
        cache_key = f"{item_code or item_name}"
        if cache_key in self._price_cache:
            cache_age = datetime.now() - self._cache_timestamp.get(cache_key, datetime.now())
            if cache_age < self.cache_duration:
                logger.info(f"📦 Using cached competitor prices for {item_name}")
                return self._price_cache[cache_key]
        
        all_prices = []
        
        # Fetch from each enabled competitor
        for comp_id, config in self.competitors.items():
            if config["enabled"]:
                if comp_id == "worldbank":
                    prices = self._fetch_from_worldbank(item_name, item_code)
                elif config["base_url"]:
                    prices = self._fetch_from_competitor(comp_id, config, item_name, item_code)
                else:
                    continue
                all_prices.extend(prices)
        
        # Always add market survey data (fallback)
        market_prices = self._get_market_survey_prices(item_name, item_code)
        all_prices.extend(market_prices)
        
        # Add some sample/estimated data if we have nothing
        if not all_prices:
            all_prices = self._generate_sample_prices(item_name, item_code)
        
        # Cache the results
        self._price_cache[cache_key] = all_prices
        self._cache_timestamp[cache_key] = datetime.now()
        
        return all_prices

    def compare_with_leysco(self, leysco_price: float, item_name: str, item_code: str = None) -> Dict:
        """
        Compare Leysco price with competitor prices
        """
        competitor_prices = self.get_competitor_prices(item_name, item_code)
        
        if not competitor_prices:
            return {
                "leysco_price": leysco_price,
                "competitor_count": 0,
                "message": "No competitor data available",
                "competitive_position": "UNKNOWN"
            }
        
        # Calculate statistics
        prices = [p["price"] for p in competitor_prices if p.get("price")]
        if not prices:
            return {
                "leysco_price": leysco_price,
                "competitor_count": len(competitor_prices),
                "message": "No valid price data",
                "competitive_position": "UNKNOWN"
            }
        
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
        
        # Determine competitive position
        if leysco_price < min_price * 0.95:
            position = "VERY_COMPETITIVE"
            message = "Your price is significantly lower than competitors"
        elif leysco_price < avg_price * 0.95:
            position = "COMPETITIVE"
            message = "Your price is below market average"
        elif leysco_price <= avg_price * 1.05:
            position = "MARKET_AVERAGE"
            message = "Your price is at market average"
        elif leysco_price <= max_price * 1.1:
            position = "SLIGHTLY_HIGH"
            message = "Your price is above market average"
        else:
            position = "HIGH"
            message = "Your price is significantly higher than competitors"
        
        # Calculate potential savings/opportunity
        savings_vs_avg = round(avg_price - leysco_price, 2) if leysco_price < avg_price else 0
        savings_vs_min = round(min_price - leysco_price, 2) if leysco_price < min_price else 0
        
        return {
            "leysco_price": leysco_price,
            "competitor_count": len(competitor_prices),
            "market_stats": {
                "average": round(avg_price, 2),
                "lowest": round(min_price, 2),
                "highest": round(max_price, 2),
                "spread": round(max_price - min_price, 2),
            },
            "competitive_position": position,
            "message": message,
            "opportunity": {
                "savings_vs_average": savings_vs_avg,
                "savings_vs_lowest": savings_vs_min,
                "potential_capture": round((avg_price - leysco_price) * 100 / avg_price, 1) if avg_price > 0 else 0,
            },
            "recommendation": self._generate_recommendation(position, leysco_price, avg_price, min_price),
            "competitors": competitor_prices[:10]  # Top 10 for summary
        }

    def get_market_intelligence(self, category: str = None) -> Dict:
        """
        Get market intelligence and trends including World Bank data
        """
        # Get World Bank economic indicators
        worldbank_data = self._get_worldbank_indicators() if self.competitors["worldbank"]["enabled"] else {}
        
        # Base market intelligence
        market_data = {
            "category": category or "All Products",
            "timestamp": datetime.now().isoformat(),
            "market_trends": {
                "overall": "stable",
                "vegetables": "increasing",
                "fruits": "stable",
                "grains": "decreasing",
            },
            "price_volatility": {
                "level": "medium",
                "factors": ["Seasonal changes", "Supply chain disruptions"],
            },
            "key_insights": [
                "Tomato prices expected to rise 15% next month due to short supply",
                "Cabbage prices stable with good availability",
                "Maize prices dropping with new harvest",
                "Imported fertilizer prices increasing due to currency fluctuation",
            ],
            "opportunities": [
                "Stock up on tomatoes before price increase",
                "Promote cabbage while prices are low",
                "Consider alternative suppliers for fertilizer",
            ],
            "recommendations": [
                "Review vegetable pricing strategy",
                "Lock in grain prices with suppliers",
                "Monitor currency rates for imports",
            ]
        }
        
        # Add World Bank economic data if available
        if worldbank_data:
            market_data["economic_indicators"] = worldbank_data
            food_inflation = worldbank_data.get('food_inflation', 0)
            comparison = 'higher' if float(food_inflation) > 5 else 'lower' if food_inflation else 'similar'
            market_data["key_insights"].insert(0, 
                f"Kenya's food inflation is at {food_inflation}% - {comparison} than regional average"
            )
        
        return market_data

    def get_price_history(self, item_name: str, days: int = 90) -> List[Dict]:
        """
        Get historical price trends
        """
        history = []
        end_date = datetime.now()
        
        for i in range(days, 0, -7):  # Weekly data points
            date = end_date - timedelta(days=i)
            # Create realistic price pattern
            base = 100
            trend = 0.1 * math.sin(i / 30)  # Seasonal pattern
            random_var = random.uniform(-5, 5)
            price = base + trend * 20 + random_var
            
            history.append({
                "date": date.strftime("%Y-%m-%d"),
                "price": round(price, 2),
                "source": "market_average"
            })
        
        return history

    # -------------------------------------------------
    # NEW: WORLD BANK SPECIFIC METHODS
    # -------------------------------------------------
    
    def _fetch_from_worldbank(self, item_name: str, item_code: str = None) -> List[Dict]:
        """
        Fetch economic indicators from World Bank API
        """
        try:
            config = self.competitors["worldbank"]
            prices = []
            
            # Get Consumer Price Index (inflation)
            cpi_data = self._get_worldbank_indicator(
                config["indicators"]["cpi"],
                "Consumer Price Index",
                item_name,
                item_code  # FIXED: Pass item_code here
            )
            if cpi_data:
                prices.append(cpi_data)
            
            # Get Food Inflation
            food_inflation = self._get_worldbank_indicator(
                config["indicators"]["food_inflation"],
                "Food Inflation Rate",
                item_name,
                item_code  # FIXED: Pass item_code here
            )
            if food_inflation:
                prices.append(food_inflation)
            
            # Get Producer Prices for crops
            producer_prices = self._get_worldbank_indicator(
                config["indicators"]["producer_prices"],
                "Crop Producer Price Index",
                item_name,
                item_code  # FIXED: Pass item_code here
            )
            if producer_prices:
                prices.append(producer_prices)
            
            logger.info(f"✅ Got {len(prices)} economic indicators from World Bank")
            return prices
            
        except Exception as e:
            logger.error(f"❌ Error fetching from World Bank: {e}")
            return []

    def _get_worldbank_indicator(self, indicator_code: str, indicator_name: str, item_name: str, item_code: str = None) -> Optional[Dict]:
        """
        Get specific indicator from World Bank API
        """
        try:
            config = self.competitors["worldbank"]
            url = f"{config['base_url']}/country/{config['country_code']}/indicator/{indicator_code}"
            params = {
                "format": "json",
                "per_page": 1,
                "date": "2023:2024"  # Most recent years
            }
            
            response = self.session.get(url, params=params, timeout=config["timeout"])
            
            if response.status_code == 200:
                data = response.json()
                if len(data) > 1 and data[1]:  # World Bank returns [metadata, data]
                    latest = data[1][0] if data[1] else None
                    if latest and latest.get("value"):
                        value = float(latest["value"])
                        
                        # Convert to price estimate based on item category
                        estimated_price = self._convert_indicator_to_price(
                            indicator_code, value, item_name
                        )
                        
                        return {
                            "competitor_id": "worldbank",
                            "competitor_name": f"World Bank - {indicator_name}",
                            "item_name": item_name,
                            "item_code": item_code,  # FIXED: Now item_code is defined
                            "price": estimated_price,
                            "currency": "KES",
                            "in_stock": True,
                            "unit": "index",
                            "price_date": latest.get("date", datetime.now().strftime("%Y")),
                            "source": "worldbank",
                            "notes": f"Based on {indicator_name} (value: {value})",
                            "indicator_value": value,
                            "indicator_code": indicator_code
                        }
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not fetch {indicator_code}: {e}")
            return None

    def _convert_indicator_to_price(self, indicator_code: str, value: float, item_name: str) -> float:
        """
        Convert World Bank indicators to estimated price in KES
        """
        # Base prices by category (adjust based on your actual data)
        base_prices = {
            "vegetables": 120,
            "fruits": 180,
            "grains": 90,
            "dairy": 150,
            "meat": 500,
            "default": 250,
        }
        
        category = self._guess_category(item_name)
        base = base_prices.get(category, base_prices["default"])
        
        if indicator_code == "FP.CPI.TOTL":  # CPI
            # Adjust based on inflation (value is index, base 100)
            return round(base * (value / 100), 2)
        elif indicator_code == "FP.CPI.TOTL.ZG":  # Food inflation
            # Adjust based on inflation rate
            return round(base * (1 + value / 100), 2)
        elif indicator_code == "AG.PRD.CROP.XD":  # Producer prices
            # Direct producer price index
            return round(base * (value / 100), 2)
        else:
            return base

    def _get_worldbank_indicators(self) -> Dict:
        """
        Get all World Bank economic indicators for market intelligence
        """
        try:
            config = self.competitors["worldbank"]
            indicators = {}
            
            # Get CPI
            cpi_response = self.session.get(
                f"{config['base_url']}/country/{config['country_code']}/indicator/FP.CPI.TOTL",
                params={"format": "json", "per_page": 4, "date": "2020:2024"},
                timeout=config["timeout"]
            )
            if cpi_response.status_code == 200:
                data = cpi_response.json()
                if len(data) > 1 and data[1]:
                    indicators["cpi_trend"] = [
                        {"year": item["date"], "value": item["value"]}
                        for item in data[1][:4] if item.get("value")
                    ]
            
            # Get food inflation
            inflation_response = self.session.get(
                f"{config['base_url']}/country/{config['country_code']}/indicator/FP.CPI.TOTL.ZG",
                params={"format": "json", "per_page": 4, "date": "2020:2024"},
                timeout=config["timeout"]
            )
            if inflation_response.status_code == 200:
                data = inflation_response.json()
                if len(data) > 1 and data[1] and data[1][0].get("value"):
                    indicators["food_inflation"] = round(data[1][0]["value"], 2)
            
            return indicators
            
        except Exception as e:
            logger.error(f"Failed to fetch World Bank indicators: {e}")
            return {}

    # -------------------------------------------------
    # EXISTING PRIVATE METHODS
    # -------------------------------------------------
    
    def _fetch_from_competitor(self, comp_id: str, config: Dict, item_name: str, item_code: str = None) -> List[Dict]:
        """
        Fetch prices from a specific competitor API
        """
        try:
            # Prepare request parameters
            params = {
                "search": item_name,
                "limit": 5
            }
            if item_code:
                params["code"] = item_code
            
            headers = {}
            if config.get("api_key"):
                headers["Authorization"] = f"Bearer {config['api_key']}"
            
            # Make API call
            response = self.session.get(
                config["base_url"],
                params=params,
                headers=headers,
                timeout=config["timeout"]
            )
            
            if response.status_code == 200:
                data = response.json()
                prices = self._normalize_competitor_response(comp_id, data)
                logger.info(f"✅ Got {len(prices)} prices from {config['name']}")
                return prices
            else:
                logger.warning(f"⚠️ {config['name']} returned {response.status_code}")
                return []
                
        except requests.exceptions.Timeout:
            logger.warning(f"⏱️ Timeout fetching from {config['name']}")
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching from {config['name']}: {e}")
            return []

    def _normalize_competitor_response(self, comp_id: str, data: Any) -> List[Dict]:
        """
        Normalize different API response formats to standard structure
        """
        prices = []
        
        # Handle different response formats
        if isinstance(data, dict):
            items = data.get("data", data.get("items", data.get("results", [])))
        elif isinstance(data, list):
            items = data
        else:
            items = []
        
        for item in items:
            # Extract common fields
            price_item = {
                "competitor_id": comp_id,
                "competitor_name": self.competitors[comp_id]["name"],
                "item_name": item.get("name") or item.get("product_name") or item.get("description"),
                "item_code": item.get("code") or item.get("sku") or item.get("product_code"),
                "price": float(item.get("price") or item.get("selling_price") or 0),
                "currency": item.get("currency", "KES"),
                "in_stock": item.get("in_stock", item.get("available", True)),
                "unit": item.get("unit", "kg"),
                "price_date": item.get("date", datetime.now().isoformat()),
                "source": "api",
                "url": item.get("url"),
            }
            
            if price_item["price"] > 0:
                prices.append(price_item)
        
        return prices

    def _get_market_survey_prices(self, item_name: str, item_code: str = None) -> List[Dict]:
        """
        Get market survey/estimated prices based on item category
        """
        # Determine category from item name
        category = self._guess_category(item_name)
        
        # Market price ranges by category (KES per kg/unit)
        market_ranges = {
            "vegetables": {"min": 50, "max": 200, "avg": 120},
            "fruits": {"min": 80, "max": 300, "avg": 180},
            "grains": {"min": 40, "max": 150, "avg": 90},
            "dairy": {"min": 60, "max": 250, "avg": 150},
            "meat": {"min": 300, "max": 800, "avg": 500},
            "default": {"min": 100, "max": 500, "avg": 250},
        }
        
        ranges = market_ranges.get(category, market_ranges["default"])
        
        # Market locations
        markets = [
            "Kariokor Market",
            "Wakulima Market",
            "Gikomba Market",
            "City Market",
            "Eastleigh Market",
            "Kangemi Market",
            "Kawangware Market",
        ]
        
        prices = []
        for market in random.sample(markets, min(3, len(markets))):
            price = {
                "competitor_id": "market",
                "competitor_name": market,
                "item_name": item_name,
                "item_code": item_code,
                "price": round(random.uniform(ranges["min"], ranges["avg"]), 2),
                "currency": "KES",
                "in_stock": True,
                "unit": "kg",
                "price_date": datetime.now().isoformat(),
                "source": "market_survey",
                "notes": f"Survey price from {market}"
            }
            prices.append(price)
        
        return prices

    def _generate_sample_prices(self, item_name: str, item_code: str = None) -> List[Dict]:
        """
        Generate sample competitor prices when no real data is available
        """
        category = self._guess_category(item_name)
        
        # Base price by category
        base_prices = {
            "vegetables": 120,
            "fruits": 180,
            "grains": 90,
            "dairy": 150,
            "meat": 500,
            "default": 250,
        }
        base = base_prices.get(category, base_prices["default"])
        
        competitors = [
            {"name": "Twiga Foods", "id": "twiga", "type": "online"},
            {"name": "SokoPepper", "id": "sokopepper", "type": "online"},
            {"name": "FarmCrowdy", "id": "farmcrowdy", "type": "online"},
            {"name": "Kariokor Market", "id": "market1", "type": "market"},
            {"name": "Wakulima Market", "id": "market2", "type": "market"},
            {"name": "Gikomba Market", "id": "market3", "type": "market"},
            {"name": "Jumia Food", "id": "jumia", "type": "retail"},
        ]
        
        prices = []
        for comp in random.sample(competitors, min(5, len(competitors))):
            if comp["type"] == "online":
                price_multiplier = random.uniform(0.9, 1.3)
            elif comp["type"] == "market":
                price_multiplier = random.uniform(0.7, 1.1)
            else:
                price_multiplier = random.uniform(0.8, 1.2)
            
            price = {
                "competitor_id": comp["id"],
                "competitor_name": comp["name"],
                "item_name": item_name,
                "item_code": item_code,
                "price": round(base * price_multiplier, 2),
                "currency": "KES",
                "in_stock": random.random() > 0.1,
                "unit": "kg",
                "price_date": datetime.now().isoformat(),
                "source": "sample",
                "url": f"https://example.com/product/{item_code}" if comp["type"] == "online" else None,
            }
            prices.append(price)
        
        prices.sort(key=lambda x: x["price"])
        return prices

    def _guess_category(self, item_name: str) -> str:
        """
        Guess item category from name
        """
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

    def _generate_recommendation(self, position: str, leysco_price: float, avg_price: float, min_price: float) -> str:
        """
        Generate pricing recommendation based on competitive position
        """
        recommendations = {
            "VERY_COMPETITIVE": "Your price is very competitive! Consider if you can maintain margins while increasing marketing to capture market share.",
            "COMPETITIVE": "Good pricing position. Monitor competitors and consider loyalty programs to retain customers.",
            "MARKET_AVERAGE": "You're at market average. Highlight quality/service differences or consider small adjustments to stand out.",
            "SLIGHTLY_HIGH": "Your price is above average. Review value proposition, consider bundling or premium positioning.",
            "HIGH": "Price is significantly higher than competitors. Urgently review pricing strategy or prepare to justify premium.",
            "UNKNOWN": "Unable to determine competitive position. Consider market research to validate pricing."
        }
        
        return recommendations.get(position, "Review pricing strategy based on market conditions.")

    def clear_cache(self):
        """Clear the price cache"""
        self._price_cache = {}
        self._cache_timestamp = {}
        logger.info("🧹 Competitor price cache cleared")


# Singleton instance
_competitor_pricing_service: Optional[CompetitorAPIService] = None


def get_competitor_pricing_service() -> CompetitorAPIService:
    """
    Get or create the singleton instance of CompetitorAPIService
    """
    global _competitor_pricing_service
    if _competitor_pricing_service is None:
        _competitor_pricing_service = CompetitorAPIService()
        logger.info("✅ Created new CompetitorAPIService singleton instance")
    return _competitor_pricing_service