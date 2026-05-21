"""Constants for Decision Support Module"""

# Decision thresholds (tunable)
THRESHOLDS = {
    "critical_stock_days": 3,
    "low_stock_days": 7,
    "optimal_stock_days": 30,
    "max_stock_days": 60,
    "reorder_point_multiplier": 1.5,
    "price_drop_threshold": 0.15,
    "price_hike_threshold": 0.20,
    "slow_mover_days": 90,
    "fast_mover_days": 30,
    "churn_risk_days": 60,
    "high_value_threshold": 50000,
    "bulk_discount_threshold": 100,
}

# Competitor price comparison messages
COMPETITOR_RECOMMENDATIONS = {
    "VERY_COMPETITIVE": "✅ Your price is very competitive! Consider increasing marketing to capture market share.",
    "COMPETITIVE": "✅ Good pricing position. Monitor competitors and consider loyalty programs.",
    "MARKET_AVERAGE": "📊 You're at market average. Highlight quality/service differences to stand out.",
    "SLIGHTLY_HIGH": "🟠 Your price is above average. Consider adding value or bundling to justify premium.",
    "HIGH": "🔴 Your price is significantly higher than competitors. Urgently review pricing strategy.",
    "NO_PRICE": "⚠️ No price configured. Set up pricing to enable sales.",
    "NO_COMPETITOR_DATA": "📊 No competitor data available. Monitor market manually."
}

# RFM Score segments
RFM_SEGMENTS = {
    (13, 15): "⭐ Champions",
    (10, 12): "💎 Loyal Customers",
    (7, 9): "📈 Potential Loyalists",
    (4, 6): "⚠️ At Risk",
    (0, 3): "❌ Lost"
}

# Health ratings
HEALTH_RATINGS = {
    (90, 100): "Excellent",
    (75, 89): "Good",
    (60, 74): "Fair",
    (40, 59): "Poor",
    (0, 39): "Critical"
}

# Stock status messages
STOCK_STATUS = {
    "OUT_OF_STOCK": {"action": "ORDER IMMEDIATELY", "priority": "CRITICAL"},
    "CRITICAL": {"action": "URGENT - Order within 24 hours", "priority": "CRITICAL"},
    "LOW": {"action": "Order this week", "priority": "HIGH"},
    "MEDIUM": {"action": "Plan order for next week", "priority": "MEDIUM"},
    "HEALTHY": {"action": "Monitor stock levels", "priority": "LOW"},
    "OVERSTOCK": {"action": "Consider promotion or reduced ordering", "priority": "MEDIUM"},
}

# Cache TTLs
CACHE_TTL = {
    "inventory_health": 120,      # 2 minutes
    "reorder_decisions": 180,     # 3 minutes
    "pricing_opportunities": 300, # 5 minutes
    "customer_behavior": 1800,    # 30 minutes
    "demand_forecast": 3600,      # 1 hour
    "sales_trend": 3600,          # 1 hour
    "inventory_turnover": 3600,   # 1 hour
    "competitor_price": 3600,     # 1 hour
    "customer_segmentation": 300, # 5 minutes
}

# Default values
DEFAULT_LIMIT = 500
DEFAULT_DAYS_AHEAD = 14
DEFAULT_FORECAST_DAYS = 30
DEFAULT_SALES_HISTORY_DAYS = 90