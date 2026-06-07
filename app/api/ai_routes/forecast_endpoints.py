"""
app/api/ai_routes/forecast_endpoints.py (P1.4 - Gated Sample Data)
====================================================================
ML Forecasting endpoints with feature-gated mock data.

CHANGE:
- ALLOW_SAMPLE_DATA flag controls mock data fallback
- Production: Returns error if no real data (no fallback to mock)
- Testing: Can use mock data with ALLOW_SAMPLE_DATA=true
- All data sources logged for audit trail
"""

from fastapi import APIRouter, Depends, Query
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import logging
import os

from .utils import utf8_json_response
from app.api.dependencies import require_manager_role, get_token_from_header, get_company_code
from app.ml.forecasting_service import get_ml_forecasting_service
from app.services.cache_service import get_cache_service
from app.services.leysco_api.client import create_api_service

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# FEATURE GATE: Allow sample data (default: false for production)
# ============================================================================

ALLOW_SAMPLE_DATA = os.getenv("ALLOW_SAMPLE_DATA", "false").lower() == "true"

if not ALLOW_SAMPLE_DATA:
    logger.warning("⚠️ ALLOW_SAMPLE_DATA is disabled. Mock data will NOT be used.")
else:
    logger.info("✅ ALLOW_SAMPLE_DATA is enabled. Mock data will be used as fallback.")


@router.post("/forecast/ml")
async def ml_forecast_demand(
    item_code: str,
    item_name: str = None,
    forecast_days: int = Query(30, ge=7, le=90),
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    ML-powered demand forecast.
    Manager-only endpoint.
    
    PRODUCTION BEHAVIOR:
    - Uses only real historical sales data
    - Returns error if insufficient data
    - No fallback to mock data
    
    TEST BEHAVIOR (ALLOW_SAMPLE_DATA=true):
    - Falls back to mock data if needed
    - Clearly marks mock data source
    """
    ml_service = get_ml_forecasting_service()
    
    historical_sales = await _get_historical_sales(
        item_code=item_code,
        days=365,
        user_token=user_token,
        company_code=company_code
    )
    
    if not historical_sales:
        # ===== PRODUCTION: No fallback to mock =====
        return utf8_json_response({
            "success": False,
            "error": "INSUFFICIENT_DATA",
            "message": (
                f"No historical sales data for item {item_code}. "
                f"Need at least 90 days of real transaction data to generate forecasts. "
                f"Configure ALLOW_SAMPLE_DATA=true to use test data."
            ),
            "recommendation": "Check that sales orders exist in ERP for this item, or contact system administrator."
        }, status_code=422)
    
    forecast = await ml_service.forecast_demand(
        item_code=item_code,
        item_name=item_name or item_code,
        historical_sales=historical_sales,
        forecast_days=forecast_days
    )
    
    # ===== DETERMINE DATA SOURCE FOR AUDIT =====
    is_mock = any(
        sale.get("item_code") == "MOCK_ITEM" or sale.get("source") == "mock"
        for sale in (historical_sales or [])
    )
    
    # ===== WARN IF USING MOCK DATA =====
    if is_mock:
        logger.warning(f"⚠️ Forecast for {item_code} using MOCK data (ALLOW_SAMPLE_DATA={ALLOW_SAMPLE_DATA})")
    
    return utf8_json_response({
        "success": True,
        **forecast,
        "data_source": "mock" if is_mock else "real",
        "warning": "⚠️ This forecast uses SAMPLE DATA for testing purposes" if is_mock else None
    })


@router.get("/forecast/seasonal")
async def get_seasonal_forecast(
    item_code: str = None,
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Get seasonal forecast insights.
    Manager-only endpoint.
    
    Requires real historical data. Returns error if none available and ALLOW_SAMPLE_DATA=false.
    """
    historical_sales = await _get_historical_sales(
        item_code=item_code,
        days=365,
        user_token=user_token,
        company_code=company_code
    )
    
    if not historical_sales:
        return utf8_json_response({
            "success": False,
            "error": "INSUFFICIENT_DATA",
            "message": (
                f"No historical sales data for item {item_code}. "
                f"Cannot detect seasonal patterns without real sales data. "
                f"Configure ALLOW_SAMPLE_DATA=true to use test data."
            )
        }, status_code=422)
    
    from collections import defaultdict
    monthly_totals = defaultdict(float)
    
    for sale in historical_sales:
        try:
            date = datetime.strptime(sale["date"], "%Y-%m-%d")
            month = date.month
            monthly_totals[month] += sale["quantity"]
        except:
            pass
    
    if not monthly_totals:
        return utf8_json_response({
            "success": True,
            "message": "Insufficient data for seasonal detection",
            "seasonal_pattern": None,
            "data_source": "unknown"
        })
    
    peak_month = max(monthly_totals, key=monthly_totals.get)
    
    month_names = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December"
    }
    
    seasonal_pattern = None
    if peak_month in [3, 4]:
        seasonal_pattern = f"Peak demand in {month_names[peak_month]} (planting season)"
    elif peak_month in [10, 11]:
        seasonal_pattern = f"Peak demand in {month_names[peak_month]} (harvest season)"
    else:
        seasonal_pattern = f"Peak demand in {month_names[peak_month]}"
    
    # ===== DETERMINE DATA SOURCE =====
    is_mock = any(
        sale.get("source") == "mock" 
        for sale in (historical_sales or [])
    )
    
    return utf8_json_response({
        "success": True,
        "item_code": item_code or "ALL",
        "seasonal_pattern": seasonal_pattern,
        "peak_month": month_names.get(peak_month, "Unknown"),
        "monthly_distribution": {month_names.get(m, str(m)): round(qty, 0) for m, qty in monthly_totals.items()},
        "data_source": "mock" if is_mock else "real",
        "warning": "⚠️ This uses SAMPLE DATA" if is_mock else None
    })


# ============================================================================
# PRIVATE: Fetch historical sales (with gated mock fallback)
# ============================================================================

async def _get_historical_sales(
    item_code: str = None,
    days: int = 365,
    user_token: str = None,
    company_code: str = None
) -> List[Dict]:
    """
    Fetch historical sales data from ERP API.
    
    PRODUCTION (ALLOW_SAMPLE_DATA=false):
    - Returns None if no real data (no fallback to mock)
    
    TESTING (ALLOW_SAMPLE_DATA=true):
    - Falls back to mock data if ERP has nothing
    """
    from collections import defaultdict
    from datetime import datetime, timedelta
    
    cache_key = f"historical_sales:{item_code or 'all'}:{days}"
    cache = get_cache_service()
    cached = await cache.get_simple_async(cache_key)
    if cached:
        logger.info(f"✅ Historical sales cache hit for {item_code or 'all'}")
        return cached
    
    try:
        api_service = create_api_service(user_token=user_token)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        url = f"{api_service.base_url}/marketing/docs/17"
        params = {"page": 1, "per_page": 100, "isDoc": 1}
        
        all_orders = []
        page = 1
        total_pages = 1
        
        # Fetch sales orders from ERP
        while page <= total_pages:
            params["page"] = page
            api_service._record_api_call()
            resp = api_service.session.get(url, params=params, timeout=30)
            
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch sales orders: {resp.status_code}")
                break
            
            data = resp.json()
            response_data = data.get("ResponseData", {})
            orders = response_data.get("data", [])
            all_orders.extend(orders)
            
            total = response_data.get("total", 0)
            per_page = response_data.get("per_page", 100)
            total_pages = (total + per_page - 1) // per_page if total > 0 else 1
            page += 1
            
            if len(all_orders) >= 500:
                break
        
        # Process real orders
        if all_orders:
            daily_totals = defaultdict(float)
            
            for order in all_orders:
                doc_date = order.get("DocDate", "")
                if not doc_date:
                    continue
                
                try:
                    order_date = datetime.strptime(doc_date, "%Y-%m-%d")
                    if order_date < start_date or order_date > end_date:
                        continue
                except:
                    pass
                
                lines = order.get("document_lines", [])
                for line in lines:
                    line_item_code = line.get("ItemCode", "")
                    if item_code and line_item_code != item_code:
                        continue
                    
                    quantity = float(line.get("Quantity", 0))
                    if quantity > 0:
                        daily_totals[doc_date] += quantity
            
            result = [
                {"date": date, "quantity": qty, "item_code": item_code or "ALL", "source": "real"}
                for date, qty in sorted(daily_totals.items())
            ]
            
            logger.info(f"✅ Retrieved {len(result)} days of REAL sales data for {item_code or 'all items'}")
            await cache.set_simple_async(cache_key, result, ttl=86400)
            return result
        
        # ===== NO REAL DATA: Check ALLOW_SAMPLE_DATA flag =====
        logger.warning(f"⚠️ No real sales data found for {item_code or 'all items'}")
        
        if not ALLOW_SAMPLE_DATA:
            logger.error(f"🚫 Mock data disabled (ALLOW_SAMPLE_DATA=false). Returning None.")
            return None
        
        # Fallback to mock data (TESTING ONLY)
        logger.info(f"📊 Falling back to MOCK data for {item_code} (ALLOW_SAMPLE_DATA=true)")
        result = _generate_mock_sales_data(item_code, days)
        
        # Mark as mock
        for item in result:
            item["source"] = "mock"
        
        await cache.set_simple_async(cache_key, result, ttl=3600)
        return result
        
    except Exception as e:
        logger.error(f"Error fetching historical sales: {e}", exc_info=True)
        
        # ===== EXCEPTION: Check ALLOW_SAMPLE_DATA flag =====
        if not ALLOW_SAMPLE_DATA:
            logger.error(f"🚫 Mock data disabled. Returning None.")
            return None
        
        logger.warning(f"📊 Using MOCK data due to exception (ALLOW_SAMPLE_DATA=true)")
        result = _generate_mock_sales_data(item_code, days)
        for item in result:
            item["source"] = "mock"
        return result


def _generate_mock_sales_data(item_code: str = None, days: int = 365) -> List[Dict]:
    """
    Generate realistic MOCK sales data for TESTING ONLY.
    
    ⚠️ DO NOT USE IN PRODUCTION - use only when ALLOW_SAMPLE_DATA=true
    """
    import random
    from datetime import datetime, timedelta
    
    logger.warning(f"⚠️ Generating MOCK sales data for {item_code} (for testing only)")
    
    data = []
    start_date = datetime.now() - timedelta(days=days)
    
    if item_code:
        item_lower = item_code.lower()
        if "vegimax" in item_lower or "veg" in item_lower:
            base_demand = 500
        elif "seed" in item_lower:
            base_demand = 800
        elif "fert" in item_lower:
            base_demand = 600
        else:
            base_demand = 400
    else:
        base_demand = 500
    
    for i in range(days):
        date = start_date + timedelta(days=i)
        month = date.month
        
        # Seasonal factors
        if month in [3, 4]:
            seasonal_factor = 1.5
        elif month in [10, 11]:
            seasonal_factor = 1.8
        elif month in [12, 1]:
            seasonal_factor = 1.2
        elif month in [7, 8]:
            seasonal_factor = 0.7
        else:
            seasonal_factor = 1.0
        
        # Weekday factors
        weekday = date.weekday()
        weekday_factor = 0.6 if weekday >= 5 else 1.0
        
        quantity = base_demand * seasonal_factor * weekday_factor
        quantity += random.uniform(-50, 50)
        quantity = max(0, round(quantity))
        
        data.append({
            "date": date.strftime("%Y-%m-%d"),
            "quantity": quantity,
            "item_code": item_code or "MOCK_ITEM",
            "source": "mock"
        })
    
    logger.warning(f"⚠️ Generated {len(data)} days of MOCK sales data")
    return data