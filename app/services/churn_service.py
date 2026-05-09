"""
app/services/churn_service.py
==============================
RFM-based Churn Prediction Service
No ML required - uses Recency, Frequency, Monetary scoring.

FEATURES:
- Calculate churn risk score (0-100)
- Identify risk factors
- Recommend actions based on risk level
- Track predictions for future ML training
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from collections import defaultdict
import uuid

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


@dataclass
class ChurnPrediction:
    """Churn prediction result"""
    customer_id: str
    customer_name: str
    risk_score: int  # 0-100, higher = more likely to churn
    risk_level: str  # HIGH, MEDIUM, LOW
    recency_score: int
    frequency_score: int
    monetary_score: int
    days_since_last_order: int
    total_orders: int
    avg_order_value: float
    risk_factors: List[str]
    recommended_action: str
    predicted_at: str


class ChurnService:
    """
    RFM-based churn prediction service.
    No ML required - uses proven RFM scoring.
    """
    
    # Score weights (adjustable based on business priorities)
    WEIGHTS = {
        "recency": 0.5,    # Most important - recency is strongest predictor
        "frequency": 0.3,  # Second most important
        "monetary": 0.2,   # Least important for churn prediction
    }
    
    # Thresholds (adjustable)
    HIGH_RISK_THRESHOLD = 70
    MEDIUM_RISK_THRESHOLD = 40
    
    # Recency scoring (days since last order)
    RECENCY_SCORES = {
        0: 100,      # 0-7 days
        7: 100,
        8: 75,       # 8-30 days
        30: 75,
        31: 50,      # 31-60 days
        60: 50,
        61: 25,      # 61-90 days
        90: 25,
        91: 0,       # 90+ days
    }
    
    # Frequency scoring (orders per month)
    FREQUENCY_SCORES = {
        4.0: 100,    # 4+ orders/month
        3.0: 75,     # 2-4 orders/month
        2.0: 75,
        1.0: 50,     # 1 order/month
        0.5: 25,     # <1 order/month
        0.1: 10,     # First-time/rare buyer
    }
    
    # Monetary scoring (average order value in KES)
    MONETARY_SCORES = {
        100000: 100,  # >KES 100k
        50000: 75,    # KES 50k-100k
        10000: 50,    # KES 10k-50k
        1000: 25,     # KES 1k-10k
        0: 10,        # <KES 1k
    }
    
    def __init__(self):
        self.cache = get_cache_service()
    
    def _get_recency_score(self, days_since_last: int) -> int:
        """Convert days since last order to score (0-100)."""
        for threshold, score in sorted(self.RECENCY_SCORES.items()):
            if days_since_last <= threshold:
                return score
        return 0
    
    def _get_frequency_score(self, orders_per_month: float) -> int:
        """Convert orders per month to score (0-100)."""
        for threshold, score in sorted(self.FREQUENCY_SCORES.items(), reverse=True):
            if orders_per_month >= threshold:
                return score
        return 0
    
    def _get_monetary_score(self, avg_order_value: float) -> int:
        """Convert average order value to score (0-100)."""
        for threshold, score in sorted(self.MONETARY_SCORES.items(), reverse=True):
            if avg_order_value >= threshold:
                return score
        return 0
    
    def _identify_risk_factors(
        self,
        days_since_last: int,
        orders_per_month: float,
        avg_order_value: float,
        total_orders: int
    ) -> List[str]:
        """Identify specific risk factors for this customer."""
        risk_factors = []
        
        # Recency risks
        if days_since_last > 60:
            risk_factors.append(f"No purchase in {days_since_last} days")
        elif days_since_last > 30:
            risk_factors.append(f"Last purchase was {days_since_last} days ago")
        
        # Frequency risks
        if total_orders == 1:
            risk_factors.append("One-time buyer - hasn't returned")
        elif orders_per_month < 0.5:
            risk_factors.append("Very infrequent buyer")
        elif orders_per_month < 1:
            risk_factors.append("Less than monthly purchases")
        
        # Monetary risks (high-value customers are HIGHER priority to retain)
        if avg_order_value > 50000 and days_since_last > 45:
            risk_factors.append(f"High-value customer (KES {avg_order_value:,.0f}/order) at risk")
        
        if not risk_factors:
            risk_factors.append("Regular buyer - monitor normally")
        
        return risk_factors
    
    def _generate_recommendation(
        self,
        risk_level: str,
        days_since_last: int,
        avg_order_value: float,
        total_orders: int
    ) -> str:
        """Generate actionable recommendation based on risk level."""
        
        if risk_level == "HIGH":
            if days_since_last > 90:
                return "URGENT: Customer likely lost. Assign to sales rep for immediate call + send 20% win-back offer."
            elif avg_order_value > 50000:
                return "HIGH PRIORITY: High-value customer at risk. Sales rep to call within 24 hours with personalized offer."
            else:
                return "Assign to sales rep for follow-up within 48 hours. Send re-engagement email with 15% discount."
        
        elif risk_level == "MEDIUM":
            if days_since_last > 30:
                return "Schedule follow-up call within 1 week. Send product recommendations based on purchase history."
            else:
                return "Monitor monthly. Consider sending loyalty email with upcoming promotions."
        
        else:
            if total_orders == 1:
                return "Send welcome-back offer to convert to repeat buyer."
            else:
                return "Maintain regular engagement. No immediate action needed."
    
    async def predict(
        self,
        customer_id: str,
        customer_name: str,
        orders: List[Dict]
    ) -> ChurnPrediction:
        """
        Calculate churn risk using RFM scoring.
        
        Args:
            customer_id: Customer code
            customer_name: Customer name
            orders: List of order dicts with DocDate and DocTotal
        
        Returns:
            ChurnPrediction object with risk score and recommendations
        """
        
        if not orders:
            # No orders ever - high churn risk (lead not converted)
            return ChurnPrediction(
                customer_id=customer_id,
                customer_name=customer_name,
                risk_score=85,
                risk_level="HIGH",
                recency_score=0,
                frequency_score=0,
                monetary_score=0,
                days_since_last_order=999,
                total_orders=0,
                avg_order_value=0,
                risk_factors=["No purchase history - lead not converted"],
                recommended_action="Assign to sales rep for lead conversion. Send welcome offer.",
                predicted_at=datetime.now().isoformat()
            )
        
        # Extract order dates and amounts
        order_dates = []
        order_amounts = []
        
        for order in orders:
            doc_date = order.get("DocDate", "")
            doc_total = float(order.get("DocTotal", 0))
            
            if doc_date:
                try:
                    order_dates.append(datetime.strptime(doc_date, "%Y-%m-%d"))
                    order_amounts.append(doc_total)
                except:
                    pass
        
        if not order_dates:
            return ChurnPrediction(
                customer_id=customer_id,
                customer_name=customer_name,
                risk_score=50,
                risk_level="MEDIUM",
                recency_score=0,
                frequency_score=0,
                monetary_score=0,
                days_since_last_order=999,
                total_orders=0,
                avg_order_value=0,
                risk_factors=["Unable to parse order dates"],
                recommended_action="Review customer data manually",
                predicted_at=datetime.now().isoformat()
            )
        
        # Calculate metrics
        last_order_date = max(order_dates)
        days_since_last = (datetime.now() - last_order_date).days
        
        total_orders = len(order_dates)
        total_spent = sum(order_amounts)
        avg_order_value = total_spent / total_orders if total_orders > 0 else 0
        
        # Calculate orders per month
        first_order_date = min(order_dates)
        days_span = (last_order_date - first_order_date).days if len(order_dates) > 1 else 30
        months_span = max(1, days_span / 30)
        orders_per_month = total_orders / months_span
        
        # Calculate component scores
        recency_score = self._get_recency_score(days_since_last)
        frequency_score = self._get_frequency_score(orders_per_month)
        monetary_score = self._get_monetary_score(avg_order_value)
        
        # Calculate weighted risk score
        # Note: Lower scores = better, so we invert (100 - weighted_avg)
        weighted_avg = (
            recency_score * self.WEIGHTS["recency"] +
            frequency_score * self.WEIGHTS["frequency"] +
            monetary_score * self.WEIGHTS["monetary"]
        )
        risk_score = 100 - weighted_avg
        risk_score = max(0, min(100, int(risk_score)))  # Clamp 0-100
        
        # Determine risk level
        if risk_score >= self.HIGH_RISK_THRESHOLD:
            risk_level = "HIGH"
        elif risk_score >= self.MEDIUM_RISK_THRESHOLD:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        
        # Identify risk factors
        risk_factors = self._identify_risk_factors(
            days_since_last, orders_per_month, avg_order_value, total_orders
        )
        
        # Generate recommendation
        recommended_action = self._generate_recommendation(
            risk_level, days_since_last, avg_order_value, total_orders
        )
        
        # Cache prediction for tracking
        await self._cache_prediction(
            customer_id, risk_score, risk_level, recommended_action
        )
        
        return ChurnPrediction(
            customer_id=customer_id,
            customer_name=customer_name,
            risk_score=risk_score,
            risk_level=risk_level,
            recency_score=recency_score,
            frequency_score=frequency_score,
            monetary_score=monetary_score,
            days_since_last_order=days_since_last,
            total_orders=total_orders,
            avg_order_value=round(avg_order_value, 2),
            risk_factors=risk_factors,
            recommended_action=recommended_action,
            predicted_at=datetime.now().isoformat()
        )
    
    async def predict_batch(
        self,
        customers: List[Dict]
    ) -> List[ChurnPrediction]:
        """
        Calculate churn risk for multiple customers.
        Sorted by risk score (highest first).
        """
        predictions = []
        
        for customer in customers:
            prediction = await self.predict(
                customer_id=customer.get("CardCode", ""),
                customer_name=customer.get("CardName", ""),
                orders=customer.get("orders", [])
            )
            predictions.append(prediction)
        
        # Sort by risk score (highest first)
        predictions.sort(key=lambda x: x.risk_score, reverse=True)
        
        return predictions
    
    async def _cache_prediction(
        self,
        customer_id: str,
        risk_score: int,
        risk_level: str,
        recommended_action: str
    ) -> None:
        """Cache prediction for tracking and future ML training."""
        cache_key = f"churn_prediction:{customer_id}"
        prediction_data = {
            "customer_id": customer_id,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "recommended_action": recommended_action,
            "predicted_at": datetime.now().isoformat(),
            "actual_churned": None  # To be filled when we know
        }
        await self.cache.set_simple_async(cache_key, prediction_data, ttl=86400 * 7)  # 7 days
    
    async def record_actual_outcome(
        self,
        customer_id: str,
        did_churn: bool,
        churned_date: Optional[str] = None
    ) -> None:
        """
        Record whether a customer actually churned.
        This data will be used to train ML model later.
        """
        cache_key = f"churn_prediction:{customer_id}"
        prediction = await self.cache.get_simple_async(cache_key)
        
        if prediction:
            prediction["actual_churned"] = did_churn
            prediction["churned_date"] = churned_date or datetime.now().isoformat()
            await self.cache.set_simple_async(cache_key, prediction, ttl=86400 * 30)
            logger.info(f"📝 Recorded actual outcome for customer {customer_id}: churned={did_churn}")


# Singleton instance
_churn_service = None


def get_churn_service() -> ChurnService:
    """Get or create ChurnService singleton."""
    global _churn_service
    if _churn_service is None:
        _churn_service = ChurnService()
    return _churn_service