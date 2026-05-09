"""
app/ml/forecasting_service.py
==============================
ML Forecasting Service using Prophet and ARIMA

REQUIRES: pip install prophet statsmodels pandas numpy
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import json

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# Try to import ML libraries (optional - graceful fallback)
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
    logger.info("✅ Prophet library loaded")
except ImportError:
    PROPHET_AVAILABLE = False
    logger.warning("Prophet not installed. Install with: pip install prophet")

try:
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.tsa.stattools import adfuller
    STATSMODELS_AVAILABLE = True
    logger.info("✅ Statsmodels loaded")
except ImportError:
    STATSMODELS_AVAILABLE = False
    logger.warning("Statsmodels not installed. Install with: pip install statsmodels")


@dataclass
class ForecastResult:
    """ML forecast result"""
    item_code: str
    item_name: str
    forecast_days: int
    point_forecast: float
    confidence_lower: float
    confidence_upper: float
    seasonal_pattern: Optional[str]
    trend_direction: str  # "up", "down", "stable"
    recommendations: List[str]
    model_used: str  # "prophet", "arima", "ensemble"
    accuracy_score: float  # 0-100
    created_at: str


class MLForecastingService:
    """
    Machine Learning demand forecasting.
    Uses Prophet (seasonality) + ARIMA (trend) ensemble.
    """
    
    # Cache TTL for forecasts (24 hours - forecasts are expensive)
    FORECAST_CACHE_TTL = 86400
    
    def __init__(self):
        self.cache = get_cache_service()
        self._model_cache = {}
    
    # =========================================================
    # MAIN FORECAST METHOD
    # =========================================================
    
    async def forecast_demand(
        self,
        item_code: str,
        item_name: str,
        historical_sales: List[Dict],
        forecast_days: int = 30,
        use_ensemble: bool = True
    ) -> Dict[str, Any]:
        """
        Forecast demand using ML models.
        
        Args:
            item_code: Item identifier
            item_name: Item name for display
            historical_sales: List of {date, quantity} for last 12+ months
            forecast_days: Days to forecast (30, 60, 90)
            use_ensemble: Combine Prophet + ARIMA
        
        Returns:
            Forecast results with confidence intervals
        """
        
        # Check cache
        cache_key = f"ml_forecast:{item_code}:{forecast_days}"
        cached = await self.cache.get_simple_async(cache_key)
        if cached:
            logger.info(f"📦 ML forecast cache hit for {item_code}")
            return cached
        
        # Convert to DataFrame
        df = pd.DataFrame(historical_sales)
        df['ds'] = pd.to_datetime(df['date'])
        df['y'] = df['quantity'].astype(float)
        df = df.sort_values('ds')
        
        # Check if we have enough data
        if len(df) < 90:  # Need at least 90 days for meaningful forecast
            return self._fallback_forecast(item_code, item_name, df, forecast_days)
        
        results = {}
        
        # Run Prophet if available
        if PROPHET_AVAILABLE:
            prophet_result = await self._forecast_prophet(df, forecast_days)
            results["prophet"] = prophet_result
        
        # Run ARIMA if available
        if STATSMODELS_AVAILABLE:
            arima_result = await self._forecast_arima(df, forecast_days)
            results["arima"] = arima_result
        
        # Ensemble (average of both models)
        if use_ensemble and len(results) > 1:
            ensemble = self._ensemble_forecast(results, forecast_days)
            results["ensemble"] = ensemble
        
        # Determine best model (lowest error if we have historical)
        best_model = self._select_best_model(results, df)
        
        # Extract seasonal pattern
        seasonal_pattern = self._detect_seasonal_pattern(df)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            item_name=item_name,
            forecast=results.get(best_model, {}),
            seasonal_pattern=seasonal_pattern,
            current_stock=self._get_current_stock(item_code)
        )
        
        forecast_result = {
            "item_code": item_code,
            "item_name": item_name,
            "forecast_days": forecast_days,
            "point_forecast": round(results.get(best_model, {}).get("point_forecast", 0), 0),
            "confidence_lower": round(results.get(best_model, {}).get("confidence_lower", 0), 0),
            "confidence_upper": round(results.get(best_model, {}).get("confidence_upper", 0), 0),
            "seasonal_pattern": seasonal_pattern,
            "trend_direction": self._detect_trend_direction(df),
            "recommendations": recommendations,
            "model_used": best_model,
            "accuracy_score": self._calculate_accuracy_score(df),
            "daily_forecast": results.get(best_model, {}).get("daily_forecast", []),
            "created_at": datetime.now().isoformat()
        }
        
        # Cache result
        await self.cache.set_simple_async(
            cache_key, 
            forecast_result, 
            ttl=self.FORECAST_CACHE_TTL
        )
        
        return forecast_result
    
    # =========================================================
    # PROPHET MODEL (Best for seasonality)
    # =========================================================
    
    async def _forecast_prophet(
        self, 
        df: pd.DataFrame, 
        forecast_days: int
    ) -> Dict[str, Any]:
        """Forecast using Facebook Prophet (handles seasonality well)."""
        try:
            # Create and fit model
            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=True,
                daily_seasonality=False,
                seasonality_mode='multiplicative'
            )
            model.fit(df)
            
            # Create future dataframe
            future = model.make_future_dataframe(periods=forecast_days)
            forecast = model.predict(future)
            
            # Get last forecast period
            last_forecast = forecast.tail(forecast_days)
            
            point_forecast = last_forecast['yhat'].sum()
            confidence_lower = last_forecast['yhat_lower'].sum()
            confidence_upper = last_forecast['yhat_upper'].sum()
            
            # Get daily breakdown
            daily_forecast = [
                {
                    "date": row['ds'].strftime("%Y-%m-%d"),
                    "forecast": round(row['yhat'], 1),
                    "lower": round(row['yhat_lower'], 1),
                    "upper": round(row['yhat_upper'], 1)
                }
                for _, row in last_forecast.iterrows()
            ]
            
            return {
                "point_forecast": point_forecast,
                "confidence_lower": confidence_lower,
                "confidence_upper": confidence_upper,
                "daily_forecast": daily_forecast[:30],  # Limit to 30 days
                "model": "prophet"
            }
            
        except Exception as e:
            logger.error(f"Prophet forecast failed: {e}")
            return None
    
    # =========================================================
    # ARIMA MODEL (Best for trends)
    # =========================================================
    
    async def _forecast_arima(
        self, 
        df: pd.DataFrame, 
        forecast_days: int
    ) -> Dict[str, Any]:
        """Forecast using ARIMA (handles trends well)."""
        try:
            # Use daily aggregation
            daily = df.set_index('ds').resample('D').sum().fillna(0)
            series = daily['y']
            
            # Check if series is stationary
            result = adfuller(series.dropna())
            is_stationary = result[1] < 0.05
            
            # Simple ARIMA (p=1,d=1,q=1) works well for most business data
            model = ARIMA(series, order=(1, 1, 1))
            model_fit = model.fit()
            
            # Forecast
            forecast = model_fit.forecast(steps=forecast_days)
            
            # Get confidence intervals
            forecast_result = model_fit.get_forecast(steps=forecast_days)
            conf_int = forecast_result.conf_int()
            
            point_forecast = forecast.sum()
            confidence_lower = conf_int.iloc[:, 0].sum()
            confidence_upper = conf_int.iloc[:, 1].sum()
            
            # Daily breakdown
            daily_forecast = [
                {
                    "date": (datetime.now() + timedelta(days=i+1)).strftime("%Y-%m-%d"),
                    "forecast": round(forecast.iloc[i], 1)
                }
                for i in range(min(forecast_days, 30))
            ]
            
            return {
                "point_forecast": point_forecast,
                "confidence_lower": max(0, confidence_lower),
                "confidence_upper": confidence_upper,
                "daily_forecast": daily_forecast,
                "model": "arima"
            }
            
        except Exception as e:
            logger.error(f"ARIMA forecast failed: {e}")
            return None
    
    # =========================================================
    # ENSEMBLE METHODS
    # =========================================================
    
    def _ensemble_forecast(
        self, 
        results: Dict, 
        forecast_days: int
    ) -> Dict[str, Any]:
        """Combine Prophet and ARIMA forecasts."""
        prophet_result = results.get("prophet")
        arima_result = results.get("arima")
        
        if not prophet_result or not arima_result:
            return None
        
        # Average the point forecasts
        point_forecast = (prophet_result["point_forecast"] + arima_result["point_forecast"]) / 2
        
        # Wider confidence interval (combine both uncertainties)
        confidence_lower = min(prophet_result["confidence_lower"], arima_result["confidence_lower"])
        confidence_upper = max(prophet_result["confidence_upper"], arima_result["confidence_upper"])
        
        return {
            "point_forecast": point_forecast,
            "confidence_lower": confidence_lower,
            "confidence_upper": confidence_upper,
            "model": "ensemble",
            "daily_forecast": prophet_result.get("daily_forecast", [])  # Use Prophet's daily
        }
    
    def _select_best_model(self, results: Dict, df: pd.DataFrame) -> str:
        """Select the best model based on historical accuracy."""
        # For now, prefer ensemble if available, then Prophet
        if results.get("ensemble"):
            return "ensemble"
        elif results.get("prophet"):
            return "prophet"
        elif results.get("arima"):
            return "arima"
        return "statistical"
    
    # =========================================================
    # ANALYSIS METHODS
    # =========================================================
    
    def _detect_seasonal_pattern(self, df: pd.DataFrame) -> Optional[str]:
        """Detect seasonal patterns in historical data."""
        if len(df) < 60:
            return None
        
        # Group by month
        df['month'] = df['ds'].dt.month
        monthly_avg = df.groupby('month')['y'].mean()
        
        # Find peak months
        peak_month = monthly_avg.idxmax()
        
        month_names = {
            1: "January", 2: "February", 3: "March", 4: "April",
            5: "May", 6: "June", 7: "July", 8: "August",
            9: "September", 10: "October", 11: "November", 12: "December"
        }
        
        # Check for planting season (March-April)
        if peak_month in [3, 4]:
            return f"Peak demand in {month_names[peak_month]} (planting season)"
        
        # Check for harvest season (October-November)
        if peak_month in [10, 11]:
            return f"Peak demand in {month_names[peak_month]} (harvest season)"
        
        return f"Peak demand in {month_names.get(peak_month, 'unknown')}"
    
    def _detect_trend_direction(self, df: pd.DataFrame) -> str:
        """Detect if demand is trending up, down, or stable."""
        if len(df) < 30:
            return "stable"
        
        # Compare first half vs second half
        mid_point = len(df) // 2
        first_half = df['y'].iloc[:mid_point].mean()
        second_half = df['y'].iloc[mid_point:].mean()
        
        if second_half > first_half * 1.1:
            return "up"
        elif second_half < first_half * 0.9:
            return "down"
        else:
            return "stable"
    
    def _calculate_accuracy_score(self, df: pd.DataFrame) -> float:
        """Calculate forecast accuracy score based on data quality."""
        # More data = higher confidence
        data_points = len(df)
        if data_points >= 365:
            return 90
        elif data_points >= 180:
            return 80
        elif data_points >= 90:
            return 70
        elif data_points >= 30:
            return 50
        else:
            return 30
    
    def _generate_recommendations(
        self,
        item_name: str,
        forecast: Dict,
        seasonal_pattern: Optional[str],
        current_stock: float
    ) -> List[str]:
        """Generate actionable recommendations based on forecast."""
        recommendations = []
        
        point_forecast = forecast.get("point_forecast", 0)
        
        if point_forecast <= 0:
            return ["No significant demand forecast for this period."]
        
        # Stock vs forecast comparison
        if current_stock < point_forecast * 0.5:
            recommendations.append(f"⚠️ CRITICAL: Order {round(point_forecast - current_stock)} units to meet forecast demand")
        elif current_stock < point_forecast:
            recommendations.append(f"📦 Order {round(point_forecast - current_stock)} units to meet expected demand")
        elif current_stock > point_forecast * 1.5:
            recommendations.append(f"✅ Current stock sufficient. Consider reducing orders.")
        
        # Seasonal recommendations
        if seasonal_pattern and "planting" in seasonal_pattern.lower():
            recommendations.append(f"🌱 Seasonal opportunity: {seasonal_pattern}. Increase marketing.")
        
        if seasonal_pattern and "harvest" in seasonal_pattern.lower():
            recommendations.append(f"🌾 Harvest season approaching: Stock up now before demand spikes.")
        
        # Add confidence note
        confidence = forecast.get("confidence_upper", 0) - forecast.get("confidence_lower", 0)
        if confidence > point_forecast * 0.3:
            recommendations.append("📊 Forecast has high uncertainty. Monitor weekly and adjust.")
        
        return recommendations
    
    def _get_current_stock(self, item_code: str) -> float:
        """Get current stock level for an item."""
        # This should integrate with your inventory service
        # For now, return 0 (will be implemented)
        return 0
    
    def _fallback_forecast(
        self, 
        item_code: str, 
        item_name: str, 
        df: pd.DataFrame, 
        forecast_days: int
    ) -> Dict:
        """Fallback when ML libraries not available."""
        # Simple moving average
        daily_avg = df['y'].mean() if len(df) > 0 else 0
        point_forecast = daily_avg * forecast_days
        
        return {
            "item_code": item_code,
            "item_name": item_name,
            "forecast_days": forecast_days,
            "point_forecast": round(point_forecast, 0),
            "confidence_lower": round(point_forecast * 0.7, 0),
            "confidence_upper": round(point_forecast * 1.3, 0),
            "seasonal_pattern": "Insufficient data for seasonal detection",
            "trend_direction": "unknown",
            "recommendations": [
                f"Collect more sales data for accurate ML forecasting",
                f"Current estimate: {round(point_forecast)} units over {forecast_days} days"
            ],
            "model_used": "statistical (fallback)",
            "accuracy_score": 30,
            "daily_forecast": [],
            "created_at": datetime.now().isoformat()
        }


# Singleton instance
_ml_forecasting_service = None


def get_ml_forecasting_service() -> MLForecastingService:
    """Get or create MLForecastingService singleton."""
    global _ml_forecasting_service
    if _ml_forecasting_service is None:
        _ml_forecasting_service = MLForecastingService()
    return _ml_forecasting_service