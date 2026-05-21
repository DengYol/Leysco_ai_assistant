"""Demand forecasting and sales trend analysis"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from .constants import THRESHOLDS, CACHE_TTL
from .utils import (
    mean, std_dev, sqrt, confidence_score, calculate_trend,
    detect_seasonality, calculate_coverage_days, get_stock_recommendation
)
from .cache import cached

logger = logging.getLogger(__name__)


class ForecastingAnalyzer:
    """Handles demand forecasting and sales trend analysis"""
    
    def __init__(self, parent):
        self.parent = parent
        self.api = parent.api
    
    @cached("demand_forecast")
    def forecast_demand(
        self, 
        item_name: str, 
        days_ahead: int = 30, 
        confidence_level: float = 0.95
    ) -> Dict[str, Any]:
        """Demand forecast based on real sales history."""
        
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
                    "error": "Insufficient sales history",
                    "current_stock": self._get_current_stock(item_code),
                    "message": "No sales data available for the last 90 days",
                }

            window = min(30, len(sales_history))
            recent = sales_history[-window:]
            avg_daily = mean(recent)
            std_daily = std_dev(recent) if len(recent) > 1 else avg_daily * 0.3
            current_stk = self._get_current_stock(item_code)

            trend_slope = calculate_trend(sales_history)
            seasonal_factor = detect_seasonality(sales_history) if len(sales_history) >= 60 else 1.0

            z_score = 1.96 if confidence_level >= 0.95 else 1.645
            
            base_forecast = avg_daily * days_ahead
            trend_adjustment = trend_slope * days_ahead * days_ahead / 2
            seasonal_adjustment = base_forecast * (seasonal_factor - 1)
            point_forecast = base_forecast + trend_adjustment + seasonal_adjustment
            
            forecast_std = std_daily * sqrt(days_ahead)
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
                "coverage_days": calculate_coverage_days(current_stk, avg_daily),
                "recommendation": get_stock_recommendation(avg_daily, std_daily, days_ahead, current_stk),
                "data_points": len(sales_history),
                "confidence_score": confidence_score(len(sales_history)),
            }

            # Add trend direction
            if len(sales_history) >= 30:
                first_half = sales_history[:15]
                second_half = sales_history[-15:]
                first_avg = mean(first_half)
                second_avg = mean(second_half)

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
                    forecast["trend"] = "📊 Insufficient data"

            return forecast
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Error in forecast_demand: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Demand forecast failed: {str(e)}"
            }
    
    @cached("sales_trend")
    def get_sales_trend(self, days: int = 90) -> Dict[str, Any]:
        """Get sales trend analysis."""
        
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Try to get time series data
            try:
                time_series = self.api.get_crm_time_series(
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                    granularity="weekly"
                )
                
                if time_series:
                    return {
                        "analysis_type": "sales_trend",
                        "period_days": days,
                        "start_date": start_date.strftime("%Y-%m-%d"),
                        "end_date": end_date.strftime("%Y-%m-%d"),
                        "data": time_series,
                        "message": f"Sales trend analysis for the last {days} days"
                    }
            except Exception as e:
                logger.warning(f"Could not fetch time series data: {e}")
            
            # Fallback to summary data
            summary = self.api.get_crm_data_summary(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )
            
            return {
                "analysis_type": "sales_trend",
                "period_days": days,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "summary": summary,
                "message": f"Sales trend analysis for the last {days} days"
            }
            
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Error getting sales trend: {e}", exc_info=True)
            return {
                "error": True,
                "message": f"Could not retrieve sales trend data: {str(e)}"
            }
    
    def _get_sales_history(self, item_code: str, days: int = 90) -> List[float]:
        """Get sales history for an item."""
        try:
            history = self.api.get_sales_history(item_code=item_code, days=days)
            daily_qty = [float(r.get("Quantity") or r.get("quantity") or r.get("qty") or 0) for r in history]
            return [q for q in daily_qty if q >= 0]
        except Exception as e:
            logger.debug(f"Sales history unavailable for {item_code}: {e}")
            return []
    
    def _get_current_stock(self, item_code: str) -> float:
        """Get current stock level for an item."""
        try:
            inventory = self.api.get_inventory_report(search=item_code, limit=1)
            if inventory:
                return float(inventory[0].get("CurrentOnHand") or inventory[0].get("OnHand", 0) or 0)
        except Exception:
            pass
        return 0.0