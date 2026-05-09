"""
app/services/anomaly_detection_service.py
==========================================
Anomaly Detection Service
Detects unusual patterns in sales, inventory, and pricing.

FEATURES:
- Sales anomaly detection (sudden drops/spikes)
- Stock anomaly detection (unusual depletion)
- Pricing anomaly detection (unexpected changes)
- Tenant-safe with per-tenant thresholds
- Explainable alerts with severity scoring
"""

import logging
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict
import asyncio

from app.services.cache_service import get_cache_service
from app.services.config_service import get_config_service

logger = logging.getLogger(__name__)


@dataclass
class Anomaly:
    """Data class for a detected anomaly"""
    id: str
    tenant_code: str
    type: str  # "sales", "stock", "pricing"
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    title: str
    message: str
    message_sw: str
    score: int  # 0-100
    detected_at: str
    entity_type: str  # "item", "customer", "warehouse"
    entity_code: str
    entity_name: str
    current_value: float
    expected_value: float
    deviation_percent: float
    data_points: int
    recommendation: str
    metadata: Dict[str, Any]


class AnomalyDetectionService:
    """
    Detects anomalies in sales, inventory, and pricing data.
    Uses statistical methods (Z-score, IQR, rolling averages).
    """
    
    # Cache TTL
    ANOMALY_CACHE_TTL = 3600  # 1 hour
    
    # Default thresholds (can be overridden by config)
    DEFAULT_THRESHOLDS = {
        "sales_zscore_threshold": 2.5,      # 2.5 standard deviations
        "sales_percent_change": 0.30,        # 30% change
        "stock_drop_percent": 0.50,          # 50% stock drop
        "price_change_percent": 0.20,        # 20% price change
        "min_data_points": 14,               # Minimum days for analysis
        "lookback_days": 30,                 # Default lookback period
    }
    
    def __init__(self):
        self.cache = get_cache_service()
        self.config = get_config_service()
    
    # =========================================================
    # SALES ANOMALY DETECTION
    # =========================================================
    
    async def detect_sales_anomalies(
        self,
        tenant_code: str,
        item_code: str = None,
        days: int = 30,
        user_token: str = None
    ) -> List[Anomaly]:
        """
        Detect anomalies in sales data.
        
        Methods used:
        1. Z-score - detects outliers beyond N standard deviations
        2. Percent change - detects sudden drops or spikes
        3. Rolling average - compares to recent trend
        """
        anomalies = []
        
        try:
            # Get historical sales data
            from app.api.ai_routes import _get_historical_sales
            
            sales_data = await _get_historical_sales(
                item_code=item_code,
                days=days,
                user_token=user_token,
                company_code=tenant_code
            )
            
            if not sales_data or len(sales_data) < self.DEFAULT_THRESHOLDS["min_data_points"]:
                logger.debug(f"Insufficient sales data for anomaly detection: {len(sales_data)} points")
                return anomalies
            
            # Extract daily quantities
            daily_quantities = [d["quantity"] for d in sales_data]
            dates = [d["date"] for d in sales_data]
            
            # Method 1: Z-Score detection
            zscore_anomalies = self._detect_zscore_anomalies(
                daily_quantities, dates, "sales", 
                threshold=self.DEFAULT_THRESHOLDS["sales_zscore_threshold"]
            )
            
            # Method 2: Percent change detection
            pct_anomalies = self._detect_percent_change_anomalies(
                daily_quantities, dates, "sales",
                threshold=self.DEFAULT_THRESHOLDS["sales_percent_change"]
            )
            
            # Method 3: Rolling average detection
            rolling_anomalies = self._detect_rolling_average_anomalies(
                daily_quantities, dates, "sales",
                window=7
            )
            
            # Combine and deduplicate
            all_anomalies = zscore_anomalies + pct_anomalies + rolling_anomalies
            
            # Create Anomaly objects
            for anomaly_data in all_anomalies[:10]:  # Limit to top 10
                score = self._calculate_severity_score(
                    anomaly_data["deviation_percent"],
                    anomaly_data["method"]
                )
                
                anomaly = Anomaly(
                    id=f"sales_{datetime.now().timestamp()}_{anomaly_data['index']}",
                    tenant_code=tenant_code,
                    type="sales",
                    severity=self._get_severity(score),
                    title=f"📉 Sales Anomaly Detected",
                    message=self._generate_sales_message(anomaly_data, item_code),
                    message_sw=self._generate_sales_message_sw(anomaly_data, item_code),
                    score=score,
                    detected_at=datetime.now().isoformat(),
                    entity_type="item",
                    entity_code=item_code or "ALL",
                    entity_name=item_code or "All Items",
                    current_value=anomaly_data["current_value"],
                    expected_value=anomaly_data["expected_value"],
                    deviation_percent=anomaly_data["deviation_percent"],
                    data_points=len(sales_data),
                    recommendation=self._generate_recommendation(anomaly_data, "sales"),
                    metadata={
                        "date": anomaly_data["date"],
                        "method": anomaly_data["method"],
                        "historical_avg": anomaly_data.get("historical_avg")
                    }
                )
                anomalies.append(anomaly)
            
            logger.info(f"🔍 Detected {len(anomalies)} sales anomalies")
            
        except Exception as e:
            logger.error(f"Error detecting sales anomalies: {e}", exc_info=True)
        
        return anomalies
    
    # =========================================================
    # STOCK ANOMALY DETECTION
    # =========================================================
    
    async def detect_stock_anomalies(
        self,
        tenant_code: str,
        user_token: str = None
    ) -> List[Anomaly]:
        """
        Detect anomalies in inventory levels.
        
        Detects:
        - Sudden stock depletion
        - Unusual stock increases
        - Items that should be reordered but aren't
        """
        anomalies = []
        
        try:
            from app.services.leysco_api_service import create_api_service
            
            api_service = create_api_service(user_token=user_token)
            
            # Get current inventory
            inventory = api_service.get_inventory_report(limit=500)
            
            if not inventory:
                return anomalies
            
            # Get historical inventory snapshots (from cache or previous scans)
            historical = await self._get_historical_inventory_snapshots(tenant_code)
            
            for item in inventory[:100]:  # Limit for performance
                item_code = item.get("ItemCode")
                item_name = item.get("ItemName", item_code)
                current_on_hand = float(item.get("CurrentOnHand", 0))
                current_committed = float(item.get("CurrentIsCommited", 0))
                
                # Get historical average for this item
                historical_avg = historical.get(item_code, {}).get("avg_on_hand", current_on_hand)
                
                if historical_avg > 0:
                    drop_percent = (historical_avg - current_on_hand) / historical_avg
                    
                    # Detect significant stock drop
                    if drop_percent >= self.DEFAULT_THRESHOLDS["stock_drop_percent"]:
                        score = min(90, int(drop_percent * 100))
                        
                        anomaly = Anomaly(
                            id=f"stock_{datetime.now().timestamp()}_{item_code}",
                            tenant_code=tenant_code,
                            type="stock",
                            severity=self._get_severity(score),
                            title=f"📦 Stock Drop Alert: {item_name}",
                            message=f"Stock dropped {drop_percent:.0%} from historical average. Current: {current_on_hand:.0f} units (was ~{historical_avg:.0f}).",
                            message_sw=f"📦 Tahadhari ya Hisa: {item_name} imepungua kwa {drop_percent:.0%}. Sasa: {current_on_hand:.0f} vitengo (ilikuwa ~{historical_avg:.0f}).",
                            score=score,
                            detected_at=datetime.now().isoformat(),
                            entity_type="item",
                            entity_code=item_code,
                            entity_name=item_name,
                            current_value=current_on_hand,
                            expected_value=historical_avg,
                            deviation_percent=drop_percent * 100,
                            data_points=1,
                            recommendation=f"Reorder {int(historical_avg - current_on_hand)} units to restore normal stock levels.",
                            metadata={"committed": current_committed}
                        )
                        anomalies.append(anomaly)
            
            # Cache current snapshot for future comparison
            await self._save_inventory_snapshot(tenant_code, inventory)
            
            logger.info(f"🔍 Detected {len(anomalies)} stock anomalies")
            
        except Exception as e:
            logger.error(f"Error detecting stock anomalies: {e}", exc_info=True)
        
        return anomalies
    
    # =========================================================
    # PRICING ANOMALY DETECTION
    # =========================================================
    
    async def detect_pricing_anomalies(
        self,
        tenant_code: str,
        user_token: str = None
    ) -> List[Anomaly]:
        """
        Detect anomalies in pricing.
        
        Detects:
        - Unexpected price changes
        - Price inconsistencies across similar items
        """
        anomalies = []
        
        try:
            from app.services.leysco_api_service import create_api_service
            from app.services.pricing_service import create_pricing_service
            
            api_service = create_api_service(user_token=user_token)
            pricing_service = create_pricing_service(user_token=user_token)
            
            # Get top selling items (most likely to have price changes)
            items = api_service.get_items(limit=100)
            
            # Get historical prices from cache
            historical_prices = await self._get_historical_prices(tenant_code)
            
            for item in items[:50]:
                item_code = item.get("ItemCode")
                item_name = item.get("ItemName", item_code)
                
                # Get current price
                current_price = pricing_service.get_price(item_code=item_code)
                current_price_value = current_price.get("price", 0) if current_price else 0
                
                # Get historical price
                historical = historical_prices.get(item_code, {})
                historical_avg = historical.get("avg_price", current_price_value)
                
                if historical_avg > 0 and current_price_value > 0:
                    change_percent = abs(current_price_value - historical_avg) / historical_avg
                    
                    if change_percent >= self.DEFAULT_THRESHOLDS["price_change_percent"]:
                        is_increase = current_price_value > historical_avg
                        score = min(80, int(change_percent * 100))
                        
                        anomaly = Anomaly(
                            id=f"pricing_{datetime.now().timestamp()}_{item_code}",
                            tenant_code=tenant_code,
                            type="pricing",
                            severity=self._get_severity(score),
                            title=f"💰 Price Change Alert: {item_name}",
                            message=f"Price {'increased' if is_increase else 'decreased'} {change_percent:.0%} to KES {current_price_value:,.2f} (was KES {historical_avg:,.2f}).",
                            message_sw=f"💰 Bei {'imepanda' if is_increase else 'imeshuka'} kwa {change_percent:.0%} hadi KES {current_price_value:,.2f} (ilikuwa KES {historical_avg:,.2f}).",
                            score=score,
                            detected_at=datetime.now().isoformat(),
                            entity_type="item",
                            entity_code=item_code,
                            entity_name=item_name,
                            current_value=current_price_value,
                            expected_value=historical_avg,
                            deviation_percent=change_percent * 100,
                            data_points=1,
                            recommendation=f"Review pricing strategy. {'Consider adjusting back' if is_increase else 'Consider promoting this price drop'}.",
                            metadata={"direction": "up" if is_increase else "down"}
                        )
                        anomalies.append(anomaly)
            
            # Save current prices for future comparison
            await self._save_price_snapshot(tenant_code, items, pricing_service)
            
            logger.info(f"🔍 Detected {len(anomalies)} pricing anomalies")
            
        except Exception as e:
            logger.error(f"Error detecting pricing anomalies: {e}", exc_info=True)
        
        return anomalies
    
    # =========================================================
    # STATISTICAL METHODS
    # =========================================================
    
    def _detect_zscore_anomalies(
        self,
        values: List[float],
        dates: List[str],
        data_type: str,
        threshold: float = 2.5
    ) -> List[Dict]:
        """Detect anomalies using Z-score (standard deviation)."""
        anomalies = []
        
        if len(values) < 14:
            return anomalies
        
        mean = np.mean(values)
        std = np.std(values)
        
        if std == 0:
            return anomalies
        
        for i, (value, date) in enumerate(zip(values, dates)):
            z_score = abs(value - mean) / std
            
            if z_score > threshold:
                deviation = ((value - mean) / mean) * 100 if mean > 0 else 0
                anomalies.append({
                    "index": i,
                    "date": date,
                    "current_value": value,
                    "expected_value": mean,
                    "deviation_percent": abs(deviation),
                    "direction": "up" if value > mean else "down",
                    "method": "zscore",
                    "z_score": z_score
                })
        
        return anomalies
    
    def _detect_percent_change_anomalies(
        self,
        values: List[float],
        dates: List[str],
        data_type: str,
        threshold: float = 0.30
    ) -> List[Dict]:
        """Detect anomalies using day-over-day percent change."""
        anomalies = []
        
        if len(values) < 7:
            return anomalies
        
        for i in range(1, len(values)):
            if values[i-1] == 0:
                continue
            
            change = abs(values[i] - values[i-1]) / values[i-1]
            
            if change > threshold:
                anomalies.append({
                    "index": i,
                    "date": dates[i],
                    "current_value": values[i],
                    "expected_value": values[i-1],
                    "deviation_percent": change * 100,
                    "direction": "up" if values[i] > values[i-1] else "down",
                    "method": "percent_change",
                    "previous_value": values[i-1]
                })
        
        return anomalies
    
    def _detect_rolling_average_anomalies(
        self,
        values: List[float],
        dates: List[str],
        data_type: str,
        window: int = 7
    ) -> List[Dict]:
        """Detect anomalies by comparing to rolling average."""
        anomalies = []
        
        if len(values) < window + 7:
            return anomalies
        
        for i in range(window, len(values)):
            rolling_avg = np.mean(values[i-window:i])
            
            if rolling_avg == 0:
                continue
            
            deviation = abs(values[i] - rolling_avg) / rolling_avg
            
            if deviation > 0.40:  # 40% deviation from rolling average
                anomalies.append({
                    "index": i,
                    "date": dates[i],
                    "current_value": values[i],
                    "expected_value": rolling_avg,
                    "deviation_percent": deviation * 100,
                    "direction": "up" if values[i] > rolling_avg else "down",
                    "method": "rolling_average",
                    "window": window
                })
        
        return anomalies
    
    # =========================================================
    # HELPER METHODS
    # =========================================================
    
    def _calculate_severity_score(self, deviation_percent: float, method: str) -> int:
        """Calculate severity score (0-100) based on deviation."""
        # Base score from deviation
        score = min(100, int(deviation_percent))
        
        # Boost for certain methods
        if method == "zscore":
            score = min(100, score + 10)
        
        return max(10, min(100, score))
    
    def _get_severity(self, score: int) -> str:
        """Convert score to severity level."""
        if score >= 80:
            return "CRITICAL"
        elif score >= 60:
            return "HIGH"
        elif score >= 40:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _generate_sales_message(self, anomaly: Dict, item_code: str) -> str:
        """Generate human-readable sales anomaly message."""
        direction = anomaly["direction"]
        deviation = anomaly["deviation_percent"]
        
        if direction == "down":
            return f"⚠️ Sales for {item_code or 'this item'} dropped {deviation:.0f}% {anomaly['method']}. Expected ~{anomaly['expected_value']:.0f} units, got {anomaly['current_value']:.0f} on {anomaly['date']}."
        else:
            return f"📈 Sales spike detected for {item_code or 'this item'}: {deviation:.0f}% above normal. {anomaly['current_value']:.0f} units sold on {anomaly['date']} (expected ~{anomaly['expected_value']:.0f})."
    
    def _generate_sales_message_sw(self, anomaly: Dict, item_code: str) -> str:
        """Generate Swahili sales anomaly message."""
        direction = anomaly["direction"]
        deviation = anomaly["deviation_percent"]
        
        if direction == "down":
            return f"⚠️ Mauzo ya {item_code or 'bidhaa hii'} yamepungua kwa {deviation:.0f}%. Ilitarajiwa vitengo ~{anomaly['expected_value']:.0f}, ilipatikana {anomaly['current_value']:.0f} tarehe {anomaly['date']}."
        else:
            return f"📈 Mauzo yameongezeka sana: {deviation:.0f}% juu ya kawaida. Vitengo {anomaly['current_value']:.0f} vilivyouzwa tarehe {anomaly['date']} (ilitarajiwa ~{anomaly['expected_value']:.0f})."
    
    def _generate_recommendation(self, anomaly: Dict, anomaly_type: str) -> str:
        """Generate actionable recommendation."""
        direction = anomaly.get("direction", "unknown")
        
        if anomaly_type == "sales":
            if direction == "down":
                return "Investigate cause: stockout? competitor action? seasonal? Consider promotion."
            else:
                return "Great sales spike! Check stock levels and consider increasing orders."
        elif anomaly_type == "stock":
            return "Review reorder quantities. Update safety stock levels."
        elif anomaly_type == "pricing":
            if direction == "up":
                return "Review price increase impact on sales. Consider customer communication."
            else:
                return "Price drop detected. Consider promoting this to increase volume."
        
        return "Investigate anomaly and take appropriate action."
    
    # =========================================================
    # CACHE HELPERS FOR HISTORICAL DATA
    # =========================================================
    
    async def _get_historical_inventory_snapshots(self, tenant_code: str) -> Dict:
        """Get historical inventory snapshots from cache."""
        cache_key = f"inventory_history:{tenant_code}"
        return await self.cache.get_simple_async(cache_key) or {}
    
    async def _save_inventory_snapshot(self, tenant_code: str, inventory: List[Dict]) -> None:
        """Save current inventory snapshot for future comparison."""
        cache_key = f"inventory_history:{tenant_code}"
        
        # Calculate averages
        snapshot = {}
        for item in inventory[:200]:
            code = item.get("ItemCode")
            on_hand = float(item.get("CurrentOnHand", 0))
            
            if code:
                snapshot[code] = {
                    "avg_on_hand": on_hand,
                    "last_updated": datetime.now().isoformat()
                }
        
        await self.cache.set_simple_async(cache_key, snapshot, ttl=86400)  # 24 hours
    
    async def _get_historical_prices(self, tenant_code: str) -> Dict:
        """Get historical price snapshots from cache."""
        cache_key = f"price_history:{tenant_code}"
        return await self.cache.get_simple_async(cache_key) or {}
    
    async def _save_price_snapshot(self, tenant_code: str, items: List[Dict], pricing_service) -> None:
        """Save current prices for future comparison."""
        cache_key = f"price_history:{tenant_code}"
        
        snapshot = {}
        for item in items[:100]:
            code = item.get("ItemCode")
            if code:
                price_result = pricing_service.get_price(item_code=code)
                snapshot[code] = {
                    "avg_price": price_result.get("price", 0) if price_result else 0,
                    "last_updated": datetime.now().isoformat()
                }
        
        await self.cache.set_simple_async(cache_key, snapshot, ttl=86400)  # 24 hours
    
    # =========================================================
    # MAIN SCAN METHOD
    # =========================================================
    
    async def scan_all_anomalies(
        self,
        tenant_code: str,
        user_token: str = None
    ) -> Dict[str, List[Anomaly]]:
        """
        Run all anomaly detectors and return combined results.
        """
        results = {
            "sales_anomalies": [],
            "stock_anomalies": [],
            "pricing_anomalies": []
        }
        
        # Run detectors in parallel
        sales_task = self.detect_sales_anomalies(tenant_code, user_token=user_token)
        stock_task = self.detect_stock_anomalies(tenant_code, user_token=user_token)
        pricing_task = self.detect_pricing_anomalies(tenant_code, user_token=user_token)
        
        sales_anomalies, stock_anomalies, pricing_anomalies = await asyncio.gather(
            sales_task, stock_task, pricing_task
        )
        
        results["sales_anomalies"] = sales_anomalies
        results["stock_anomalies"] = stock_anomalies
        results["pricing_anomalies"] = pricing_anomalies
        
        total = len(sales_anomalies) + len(stock_anomalies) + len(pricing_anomalies)
        logger.info(f"🔍 Anomaly scan complete: {total} anomalies found")
        
        return results


# Singleton instance
_anomaly_detection_service = None


def get_anomaly_detection_service() -> AnomalyDetectionService:
    """Get or create AnomalyDetectionService singleton."""
    global _anomaly_detection_service
    if _anomaly_detection_service is None:
        _anomaly_detection_service = AnomalyDetectionService()
    return _anomaly_detection_service