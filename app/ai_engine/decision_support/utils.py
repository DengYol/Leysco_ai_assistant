"""Utility functions for Decision Support"""

import math
from typing import List, Optional
from datetime import datetime, timedelta


def mean(values: List[float]) -> float:
    """Safe mean — returns 0 if list is empty."""
    return sum(values) / len(values) if values else 0.0


def std_dev(values: List[float]) -> float:
    """Safe standard deviation — returns 0 if fewer than 2 values."""
    if len(values) < 2:
        return 0.0
    m = mean(values)
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def sqrt(value: float) -> float:
    """Safe square root with max(0)."""
    return math.sqrt(max(0, value))


def confidence_score(data_points: int) -> float:
    """Calculate confidence score based on data volume."""
    if data_points >= 90:
        return 1.0
    elif data_points >= 60:
        return 0.9
    elif data_points >= 30:
        return 0.75
    elif data_points >= 14:
        return 0.6
    elif data_points >= 7:
        return 0.4
    elif data_points > 0:
        return 0.2
    return 0.0


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert to float."""
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def calculate_trend(values: List[float]) -> float:
    """Calculate trend slope using linear regression."""
    if len(values) < 2:
        return 0.0
    n = len(values)
    x = list(range(n))
    y = values
    x_mean = mean(x)
    y_mean = mean(y)
    numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
    denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
    return numerator / denominator if denominator != 0 else 0


def detect_seasonality(values: List[float]) -> float:
    """Detect seasonal pattern by comparing recent weeks."""
    if len(values) < 14:
        return 1.0
    recent = values[-14:]
    week1_avg = mean(recent[:7])
    week2_avg = mean(recent[7:])
    if week1_avg > 0 and week2_avg > 0:
        return week2_avg / week1_avg
    return 1.0


def calculate_coverage_days(stock: float, daily_rate: float) -> str:
    """Calculate how many days stock will last."""
    if daily_rate <= 0:
        return "No sales data"
    days = stock / daily_rate
    if days < 1:
        return "Less than 1 day"
    elif days < 7:
        return f"{round(days, 1)} days"
    elif days < 30:
        return f"{round(days / 7, 1)} weeks"
    else:
        return f"{round(days / 30, 1)} months"


def get_rfm_segment(rfm_total: int) -> str:
    """Get RFM segment based on total score."""
    from .constants import RFM_SEGMENTS
    for (low, high), segment in RFM_SEGMENTS.items():
        if low <= rfm_total <= high:
            return segment
    return "Unknown"


def get_health_rating(score: int) -> str:
    """Get health rating based on score."""
    from .constants import HEALTH_RATINGS
    for (low, high), rating in HEALTH_RATINGS.items():
        if low <= score <= high:
            return rating
    return "Unknown"


def get_competitor_recommendation(position: str, leysco_price: float, avg_price: float) -> str:
    """Get recommendation based on competitive position."""
    from .constants import COMPETITOR_RECOMMENDATIONS
    base = COMPETITOR_RECOMMENDATIONS.get(position, "Review pricing strategy based on market conditions.")
    
    if position in ["VERY_COMPETITIVE", "COMPETITIVE"] and leysco_price > 0:
        return f"{base} (Your price: KES {leysco_price:,.2f} vs market avg: KES {avg_price:,.2f})"
    return base


def get_stock_recommendation(avg_daily: float, std_daily: float, days_ahead: int, current_stock: float) -> str:
    """Generate stock recommendation based on forecast."""
    expected_demand = avg_daily * days_ahead
    safety_buffer = std_daily * sqrt(days_ahead) * 1.65
    
    if current_stock <= 0:
        return "🚨 OUT OF STOCK - Order immediately!"
    elif current_stock < expected_demand:
        return f"⚠️ Low stock - Order {round(expected_demand - current_stock)} units to cover {days_ahead} days"
    elif current_stock > expected_demand * 2:
        return f"📦 Overstock - Consider reducing orders or running promotion"
    else:
        return f"✅ Adequate stock for {days_ahead} days"


def calculate_days_of_stock(available: float, daily_velocity: float) -> float:
    """Calculate how many days of stock are available."""
    if daily_velocity <= 0:
        return float("inf")
    return available / daily_velocity