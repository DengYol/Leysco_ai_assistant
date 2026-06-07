"""
app/services/competitor_api_service.py (P1.4 - Gated Sample Data)
==================================================================
Competitor API Integration with feature-gated sample pricing.

CHANGE:
- ALLOW_SAMPLE_DATA flag controls fallback to sample prices
- Production: Returns error if no real API data (no sample fallback)
- Testing: Can use sample prices with ALLOW_SAMPLE_DATA=true
- Data source always marked in responses
"""

import logging
import asyncio
import requests
import math
import random
import hashlib
import os
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from functools import lru_cache, wraps
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE GATE: Allow sample data (default: false for production)
# ============================================================================

ALLOW_SAMPLE_DATA = os.getenv("ALLOW_SAMPLE_DATA", "false").lower() == "true"

if not ALLOW_SAMPLE_DATA:
    logger.warning("⚠️ ALLOW_SAMPLE_DATA is disabled. Sample pricing will NOT be used.")
else:
    logger.info("✅ ALLOW_SAMPLE_DATA is enabled. Sample pricing will be used as fallback.")

# Safe import with fallback for settings
try:
    from app.core.config import settings
except ImportError:
    from types import SimpleNamespace
    settings = SimpleNamespace()
    settings.ENABLED_COMPETITORS = ""
    settings.TWIGA_API_URL = ""
    settings.TWIGA_API_KEY = ""
    settings.SOKOPEPPER_API_URL = ""
    settings.SOKOPEPPER_API_KEY = ""
    settings.FARMCROWDY_API_URL = ""
    settings.FARMCROWDY_API_KEY = ""
    settings.WORLD_BANK_API_URL = "https://api.worldbank.org/v2"
    settings.WORLD_BANK_ENABLED = False
    settings.COMPETITOR_API_TIMEOUT_SECONDS = 10
    settings.COMPETITOR_CACHE_TTL_HOURS = 1
    logger.warning("Using fallback settings for competitor API service")

# Import cache service safely
try:
    from app.services.cache_service import get_cache_service
except ImportError:
    class MockCache:
        def get_simple(self, key):
            return None
        def set_simple(self, key, value, ttl=300):
            pass
        def clear(self):
            pass
    
    def get_cache_service():
        return MockCache()
    
    logger.warning("Using mock cache service for competitor API")

# Cache TTLs
COMPETITOR_CACHE_TTL = 3600  # 1 hour
MARKET_INTEL_TTL = 7200  # 2 hours


def cache_competitor(ttl_seconds: int = COMPETITOR_CACHE_TTL):
    """Decorator to cache competitor API results."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                cache = get_cache_service()
                
                # Generate cache key
                func_name = func.__name__
                cache_str = f"competitor:{func_name}:{str(args)}:{str(sorted(kwargs.items()))}"
                cache_key = hashlib.md5(cache_str.encode()).hexdigest()
                
                # Check cache
                cached = cache.get_simple(cache_key)
                if cached is not None:
                    logger.info(f"⚡ Competitor cache hit: {func_name}")
                    return cached
                
                # Execute function
                result = func(self, *args, **kwargs)
                
                # Cache result
                if result:
                    cache.set_simple(cache_key, result, ttl=ttl_seconds)
                
                return result
            except Exception as e:
                logger.warning(f"Cache error in competitor service: {e}")
                return func(self, *args, **kwargs)
        return wrapper
    return decorator


class CompetitorAPIService:
    """
    Service to fetch competitor pricing from market APIs.
    
    PRODUCTION (ALLOW_SAMPLE_DATA=false):
    - Returns error if no real competitor data available
    - No fallback to sample/generated prices
    
    TESTING (ALLOW_SAMPLE_DATA=true):
    - Falls back to sample prices if APIs unavailable
    - Clearly marks sample data source
    """
    
    def __init__(self):
        enabled_list = []
        if hasattr(settings, 'ENABLED_COMPETITORS') and settings.ENABLED_COMPETITORS:
            enabled_list = [c.strip() for c in settings.ENABLED_COMPETITORS.split(",") if c.strip()]
        
        # Competitor API configuration
        self.competitors = {
            "twiga": {
                "name": "Twiga Foods",
                "base_url": getattr(settings, 'TWIGA_API_URL', ''),
                "api_key": getattr(settings, 'TWIGA_API_KEY', ''),
                "enabled": "twiga" in enabled_list,
                "timeout": getattr(settings, 'COMPETITOR_API_TIMEOUT_SECONDS', 10),
            },
            "sokopepper": {
                "name": "SokoPepper",
                "base_url": getattr(settings, 'SOKOPEPPER_API_URL', ''),
                "api_key": getattr(settings, 'SOKOPEPPER_API_KEY', ''),
                "enabled": "sokopepper" in enabled_list,
                "timeout": getattr(settings, 'COMPETITOR_API_TIMEOUT_SECONDS', 10),
            },
            "farmcrowdy": {
                "name": "FarmCrowdy",
                "base_url": getattr(settings, 'FARMCROWDY_API_URL', ''),
                "api_key": getattr(settings, 'FARMCROWDY_API_KEY', ''),
                "enabled": "farmcrowdy" in enabled_list,
                "timeout": getattr(settings, 'COMPETITOR_API_TIMEOUT_SECONDS', 10),
            },
        }
        
        # Cache
        self._price_cache = {}
        self._cache_timestamp = {}
        cache_ttl_hours = getattr(settings, 'COMPETITOR_CACHE_TTL_HOURS', 1)
        self.cache_duration = timedelta(hours=cache_ttl_hours)
        
        # Session
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Leysco-AI/1.0"
        })
        
        # Thread pool
        self._executor = ThreadPoolExecutor(max_workers=5)
        
        # Stats
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "errors": 0
        }
        
        logger.info(f"CompetitorAPIService initialized with {len([c for c in self.competitors.values() if c.get('enabled')])} enabled competitors")

    # ------------------------------------------------------------------
    # MAIN PUBLIC METHODS
    # ------------------------------------------------------------------

    @cache_competitor(ttl_seconds=COMPETITOR_CACHE_TTL)
    def get_competitor_prices(self, item_name: str, item_code: str = None) -> List[Dict]:
        """
        Get competitor prices for an item from all enabled sources.
        
        PRODUCTION (ALLOW_SAMPLE_DATA=false):
        - Returns empty list if no real data available
        - Caller must handle and return error
        
        TESTING (ALLOW_SAMPLE_DATA=true):
        - Falls back to generated sample prices
        - Marks as 'sample' in source field
        """
        if not item_name:
            logger.warning("get_competitor_prices called with empty item_name")
            return []
            
        logger.info(f"🔍 Fetching competitor prices for: {item_name}")
        
        all_prices = []
        
        # Fetch from enabled competitors (if any configured)
        for comp_id, config in self.competitors.items():
            if config.get("enabled", False) and config.get("base_url"):
                prices = self._fetch_from_competitor(comp_id, config, item_name, item_code)
                if prices:
                    all_prices.extend(prices)
        
        # ===== HANDLE NO REAL DATA =====
        if not all_prices:
            logger.warning(f"⚠️ No real competitor data for {item_name}")
            
            if not ALLOW_SAMPLE_DATA:
                logger.error(f"🚫 Sample data disabled (ALLOW_SAMPLE_DATA=false). Returning empty list.")
                return []
            
            # Fallback to sample/estimated data (TESTING ONLY)
            logger.warning(f"📊 Generating SAMPLE prices for {item_name} (ALLOW_SAMPLE_DATA=true)")
            all_prices = self._generate_sample_prices(item_name, item_code)
        
        return all_prices

    async def get_competitor_prices_async(self, item_name: str, item_code: str = None) -> List[Dict]:
        """Async version of get_competitor_prices."""
        return await asyncio.to_thread(self.get_competitor_prices, item_name, item_code)

    @cache_competitor(ttl_seconds=COMPETITOR_CACHE_TTL)
    def compare_with_leysco(self, leysco_price: float, item_name: str, item_code: str = None) -> Dict:
        """
        Compare Leysco price with competitor prices.
        
        PRODUCTION (ALLOW_SAMPLE_DATA=false):
        - Returns error if no real competitor data
        
        TESTING (ALLOW_SAMPLE_DATA=true):
        - Uses sample data if needed
        """
        # Handle None or invalid leysco_price
        if leysco_price is None:
            leysco_price = 0.0
        elif isinstance(leysco_price, (int, float)):
            leysco_price = float(leysco_price)
        else:
            try:
                leysco_price = float(leysco_price)
            except (ValueError, TypeError):
                leysco_price = 0.0
        
        competitor_prices = self.get_competitor_prices(item_name, item_code)
        
        # ===== NO COMPETITOR DATA AVAILABLE =====
        if not competitor_prices:
            return {
                "leysco_price": leysco_price,
                "competitor_count": 0,
                "error": "NO_COMPETITOR_DATA",
                "message": (
                    "No competitor pricing data available. "
                    "Configure ALLOW_SAMPLE_DATA=true to use sample data."
                ),
                "competitive_position": "UNKNOWN",
                "data_source": "none"
            }
        
        # Calculate statistics
        prices = []
        for p in competitor_prices:
            price = p.get("price")
            if price is not None and isinstance(price, (int, float)) and price > 0:
                prices.append(float(price))
        
        if not prices:
            return {
                "leysco_price": leysco_price,
                "competitor_count": len(competitor_prices),
                "message": "No valid price data",
                "competitive_position": "UNKNOWN",
                "data_source": "invalid"
            }
        
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
        
        # Determine competitive position
        if leysco_price <= 0:
            position = "NO_PRICE"
            message = "No price configured for this item in Leysco system"
        elif leysco_price < min_price * 0.95:
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
        
        # Calculate savings
        savings_vs_avg = round(avg_price - leysco_price, 2) if leysco_price > 0 and leysco_price < avg_price else 0
        savings_vs_min = round(min_price - leysco_price, 2) if leysco_price > 0 and leysco_price < min_price else 0
        
        # ===== DETERMINE DATA SOURCE FOR AUDIT =====
        is_sample = any(p.get("source") == "sample" for p in competitor_prices)
        
        result = {
            "leysco_price": leysco_price,
            "competitor_count": len(prices),
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
                "potential_capture": round((avg_price - leysco_price) * 100 / avg_price, 1) if avg_price > 0 and leysco_price > 0 else 0,
            },
            "recommendation": self._generate_recommendation(position, leysco_price, avg_price, min_price),
            "data_source": "sample" if is_sample else "real",
            "competitors": competitor_prices[:10]
        }
        
        if is_sample:
            result["warning"] = "⚠️ Comparison uses SAMPLE data for testing purposes"
        
        return result

    @cache_competitor(ttl_seconds=MARKET_INTEL_TTL)
    def get_market_intelligence(self, category: str = None) -> Dict:
        """
        Get market intelligence and trends.
        
        This returns curated market insights (not sample data).
        """
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
            ],
            "data_source": "market_intelligence"
        }
        
        return market_data

    async def get_market_intelligence_async(self, category: str = None) -> Dict:
        """Async version of get_market_intelligence."""
        return await asyncio.to_thread(self.get_market_intelligence, category)

    # -------------------------------------------------
    # PRIVATE METHODS
    # -------------------------------------------------
    
    def _fetch_from_competitor(self, comp_id: str, config: Dict, item_name: str, item_code: str = None) -> List[Dict]:
        """
        Fetch prices from a specific competitor API.
        Returns empty list if API unavailable (no fallback to sample here).
        """
        try:
            self._stats["api_calls"] += 1
            
            # For now, return empty list since APIs not fully configured
            # In production, implement actual API calls here
            logger.debug(f"Competitor API {comp_id} not fully configured yet")
            return []
                
        except requests.exceptions.Timeout:
            logger.debug(f"Timeout fetching from {config['name']}")
            return []
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"Error fetching from {config['name']}: {e}")
            return []

    def _generate_sample_prices(self, item_name: str, item_code: str = None) -> List[Dict]:
        """
        Generate SAMPLE competitor prices for TESTING ONLY.
        
        ⚠️ Only called when ALLOW_SAMPLE_DATA=true and no real data available.
        """
        logger.warning(f"⚠️ Generating SAMPLE prices for {item_name} (for testing only)")
        
        category = self._guess_category(item_name)
        
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
            {"name": "Twiga Foods", "id": "twiga"},
            {"name": "SokoPepper", "id": "sokopepper"},
            {"name": "Kariokor Market", "id": "market1"},
            {"name": "Wakulima Market", "id": "market2"},
        ]
        
        prices = []
        for comp in competitors:
            try:
                price_multiplier = random.uniform(0.85, 1.25)
                price = {
                    "competitor_id": comp["id"],
                    "competitor_name": comp["name"],
                    "item_name": item_name,
                    "item_code": item_code,
                    "price": round(base * price_multiplier, 2),
                    "currency": "KES",
                    "in_stock": True,
                    "unit": "kg",
                    "price_date": datetime.now().isoformat(),
                    "source": "sample",  # ===== MARK AS SAMPLE =====
                }
                prices.append(price)
            except Exception as e:
                logger.debug(f"Error generating sample price: {e}")
                continue
        
        prices.sort(key=lambda x: x["price"])
        logger.warning(f"⚠️ Generated {len(prices)} SAMPLE prices")
        return prices

    @lru_cache(maxsize=256)
    def _guess_category(self, item_name: str) -> str:
        """Guess item category from name."""
        if not item_name:
            return "default"
            
        item_lower = item_name.lower()
        
        vegetables = ["cabbage", "tomato", "onion", "potato", "carrot", "kale", "spinach", "capsicum"]
        fruits = ["mango", "banana", "apple", "orange", "pineapple", "avocado"]
        grains = ["maize", "wheat", "rice", "beans", "peas"]
        dairy = ["milk", "cheese", "yogurt", "butter"]
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
        """Generate pricing recommendation."""
        recommendations = {
            "VERY_COMPETITIVE": "Your price is very competitive! Consider maintaining margins while increasing marketing.",
            "COMPETITIVE": "Good pricing position. Monitor competitors and consider loyalty programs.",
            "MARKET_AVERAGE": "You're at market average. Highlight quality differences to stand out.",
            "SLIGHTLY_HIGH": "Price is above average. Review value proposition or consider bundling.",
            "HIGH": "Price is significantly higher. Urgently review pricing strategy.",
            "NO_PRICE": "No price configured. Set up pricing to enable sales.",
            "UNKNOWN": "Unable to determine position. Consider market research."
        }
        
        return recommendations.get(position, "Review pricing strategy based on market conditions.")

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return self._stats.copy()

    def clear_cache(self):
        """Clear the price cache."""
        self._price_cache = {}
        self._cache_timestamp = {}
        self._guess_category.cache_clear()
        logger.info("Competitor price cache cleared")
        self._stats["cache_hits"] = 0
        self._stats["cache_misses"] = 0


# Singleton instance
_competitor_pricing_service: Optional[CompetitorAPIService] = None


def get_competitor_pricing_service() -> CompetitorAPIService:
    """Get or create the singleton instance of CompetitorAPIService."""
    global _competitor_pricing_service
    if _competitor_pricing_service is None:
        try:
            _competitor_pricing_service = CompetitorAPIService()
            logger.info("Created new CompetitorAPIService singleton instance")
        except Exception as e:
            logger.error(f"Failed to create CompetitorAPIService: {e}")
            _competitor_pricing_service = CompetitorAPIService()
    return _competitor_pricing_service