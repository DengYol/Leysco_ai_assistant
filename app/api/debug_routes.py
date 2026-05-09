"""
debug_routes.py
===============
Temporary development endpoints for inspecting pricing and API data.

Mount in your main app:
    from app.api.debug_routes import router as debug_router
    app.include_router(debug_router, prefix="/debug", tags=["debug"])

Access from your browser or laptop Postman via:
    http://<your-backend-ip>:8000/debug/...

⚠  REMOVE or gate behind an env flag before production.

MODIFIED FOR PHASE 1: Added user token support for all debug endpoints
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request, Depends
from fastapi.responses import JSONResponse

from app.services.leysco_api_service import LeyscoAPIService, create_api_service
from app.services.pricing_service import PricingService, create_pricing_service
from app.api.dependencies import get_token_from_header

logger = logging.getLogger(__name__)
router = APIRouter()


# ------------------------------------------------------------------
# Helper to get authenticated services
# ------------------------------------------------------------------

async def get_authenticated_api_service(request: Request):
    """Get authenticated LeyscoAPIService from request token."""
    token = await get_token_from_header(request)
    if token:
        return create_api_service(token)
    return LeyscoAPIService()


async def get_authenticated_pricing_service(request: Request):
    """Get authenticated PricingService from request token."""
    token = await get_token_from_header(request)
    if token:
        return create_pricing_service(token)
    return PricingService()


# ------------------------------------------------------------------
# PRICING DEBUG
# ------------------------------------------------------------------

@router.get("/price/{item_code}")
async def debug_price(
    request: Request,
    item_code: str,
    sap_list_num: Optional[int] = Query(None, description="Specific SAP ListNum to query"),
):
    """
    Get the price of an item across all price lists.

    Examples:
        /debug/price/FGHY0478
        /debug/price/FGHY0478?sap_list_num=17
    """
    svc = await get_authenticated_pricing_service(request)

    if sap_list_num:
        result = svc.get_price(item_code=item_code, sap_list_num=sap_list_num)
    else:
        result = svc.get_price_any_list(item_code=item_code)

    return {
        "item_code":   item_code,
        "result":      result,
        "price_lists_loaded": len(svc._list_by_sap_num),
        "sap_to_api_map": {
            sap_num: pl.get("id")
            for sap_num, pl in svc._list_by_sap_num.items()
        },
    }


@router.get("/price-lists")
async def debug_price_lists(request: Request):
    """
    Show all loaded price lists with their SAP ListNum → API id mapping.
    Useful for understanding which lists are active and which 500.

    Example: /debug/price-lists
    """
    svc = await get_authenticated_pricing_service(request)
    lists = sorted(svc._list_by_sap_num.values(), key=lambda x: x.get("id", 0))
    return {
        "total": len(lists),
        "sap_to_api_map": {
            sap_num: {
                "api_id":      pl.get("id"),
                "name":        pl.get("ListName"),
                "base_num":    pl.get("BASE_NUM"),
                "is_gross":    pl.get("isGrossPrc"),
                "currency":    pl.get("PrimCurr"),
            }
            for sap_num, pl in svc._list_by_sap_num.items()
        },
        "lists": [
            {
                "api_id":   pl.get("id"),
                "sap_num":  pl.get("ListNum"),
                "name":     pl.get("ListName"),
                "base_num": pl.get("BASE_NUM"),
                "is_gross": pl.get("isGrossPrc"),
            }
            for pl in lists
        ],
    }


@router.get("/price-list/{api_id}")
async def debug_price_list_items(
    request: Request,
    api_id: int,
    search: Optional[str] = Query(None, description="Item code or name to search"),
    per_page: int = Query(20, description="Records per page"),
):
    """
    Inspect raw records from a price list endpoint.
    Confirms whether ?search= filters server-side.

    Examples:
        /debug/price-list/13?search=FGHY0478
        /debug/price-list/13?per_page=5
    """
    import requests
    from app.core.config import settings

    # Get token from request
    token = await get_token_from_header(request)
    if not token:
        return JSONResponse(
            status_code=401,
            content={"error": "Authentication required. Please provide a valid Bearer token."}
        )

    url    = f"{settings.LEYSCO_API_BASE_URL.rstrip('/')}/item/base-prices/price-list/{api_id}"
    params = {"per_page": per_page}
    if search:
        params["search"] = search

    headers = {"Authorization": f"Bearer {token}"}
    resp    = requests.get(url, params=params, headers=headers, timeout=20)

    return {
        "url":         str(resp.url),
        "status_code": resp.status_code,
        "body":        resp.json() if resp.ok else resp.text,
    }


# ------------------------------------------------------------------
# CUSTOMER DEBUG
# ------------------------------------------------------------------

@router.get("/customer/{name}")
async def debug_customer(request: Request, name: str):
    """
    Look up a customer and show their full pricing context.

    Examples:
        /debug/customer/magomano
        /debug/customer/SMD
    """
    api = await get_authenticated_api_service(request)
    svc = await get_authenticated_pricing_service(request)

    customer = api.get_customer_by_name(name)
    if not customer:
        return {"error": f"Customer '{name}' not found"}

    # Extract price list info
    direct_list  = customer.get("PriceListNum")
    octg         = customer.get("octg") or {}
    octg_list    = octg.get("ListNum")
    resolved_num = int(direct_list or octg_list or 1)
    pl_record    = svc._list_by_sap_num.get(resolved_num)

    return {
        "CardCode":          customer.get("CardCode"),
        "CardName":          customer.get("CardName"),
        "PriceListNum":      direct_list,
        "octg_ListNum":      octg_list,
        "resolved_sap_num":  resolved_num,
        "price_list": {
            "api_id":   pl_record.get("id")   if pl_record else None,
            "name":     pl_record.get("ListName") if pl_record else None,
            "base_num": pl_record.get("BASE_NUM") if pl_record else None,
            "is_gross": pl_record.get("isGrossPrc") if pl_record else None,
        } if pl_record else "NOT FOUND IN PRICE LIST MAP",
        "raw_octg": octg,
    }


@router.get("/customer-price/{customer_name}/{item_code}")
async def debug_customer_price(request: Request, customer_name: str, item_code: str):
    """
    Full pricing resolution for a customer + item.
    Shows the exact chain walked and where the price was found.

    Example:
        /debug/customer-price/magomano/FGHY0478
    """
    api = await get_authenticated_api_service(request)
    svc = await get_authenticated_pricing_service(request)
    customer = api.get_customer_by_name(customer_name)

    if not customer:
        return {"error": f"Customer '{customer_name}' not found"}

    result = svc.get_price_for_customer(
        item_code=item_code,
        customer=customer,
    )

    return {
        "customer": {
            "CardCode": customer.get("CardCode"),
            "CardName": customer.get("CardName"),
        },
        "item_code":  item_code,
        "pricing":    result,
    }


# ------------------------------------------------------------------
# SPECIAL PRICES PROBE
# ------------------------------------------------------------------

@router.get("/probe-special-prices")
async def probe_special_prices(request: Request):
    """
    Test all known candidate endpoints for special/customer-specific prices.
    Returns the status code of each so we know which endpoints exist.

    Example: /debug/probe-special-prices
    """
    import requests
    from app.core.config import settings

    # Get token from request
    token = await get_token_from_header(request)
    if not token:
        return JSONResponse(
            status_code=401,
            content={"error": "Authentication required. Please provide a valid Bearer token."}
        )

    base    = settings.LEYSCO_API_BASE_URL.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    timeout = 8

    candidates = [
        "/special_prices",
        "/bp_special_prices",
        "/item/special-prices",
        "/pricing/special",
        "/customer_prices",
        "/price_exceptions",
        "/discount_groups",
        "/volume_discounts",
        "/uom_groups",
        "/uoms/groups",
    ]

    results = {}
    for path in candidates:
        url = base + path
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            results[path] = {
                "status": r.status_code,
                "preview": r.text[:200] if r.status_code != 404 else "404 Not Found",
            }
        except Exception as e:
            results[path] = {"status": "ERROR", "preview": str(e)}

    return results


# ------------------------------------------------------------------
# WAREHOUSE DEBUG
# ------------------------------------------------------------------

@router.get("/warehouses")
async def debug_warehouses(request: Request):
    """
    Show all warehouses with full details from the API.
    Reveals what fields are available for warehouse features.
    
    Example: /debug/warehouses
    """
    api = await get_authenticated_api_service(request)
    warehouses = api.get_warehouses()
    
    return {
        "total": len(warehouses),
        "warehouses": warehouses,
        "sample_fields": list(warehouses[0].keys()) if warehouses else [],
    }


@router.get("/warehouse/{whscode}/stock")
async def debug_warehouse_stock(request: Request, whscode: str):
    """
    Show all items in a specific warehouse with stock levels.
    
    Example: /debug/warehouse/KDISPAT1/stock
    """
    api = await get_authenticated_api_service(request)
    
    # Get inventory report filtered by warehouse
    inventory = api.get_inventory_report(search="")
    
    # Filter to this warehouse
    wh_items = [
        itm for itm in inventory 
        if (itm.get("WhsCode") or "").upper() == whscode.upper()
    ]
    
    if not wh_items:
        return {"error": f"No inventory found for warehouse {whscode}"}
    
    # Aggregate by item
    items_map = {}
    for itm in wh_items:
        code = itm.get("ItemCode")
        if code not in items_map:
            items_map[code] = {
                "ItemCode": code,
                "ItemName": itm.get("ItemName"),
                "OnHand": itm.get("CurrentOnHand", 0),
                "Committed": itm.get("CurrentIsCommited", 0),
                "Available": itm.get("CurrentOnHand", 0) - itm.get("CurrentIsCommited", 0),
            }
    
    items = sorted(items_map.values(), key=lambda x: x["OnHand"], reverse=True)
    
    return {
        "warehouse": whscode,
        "total_items": len(items),
        "total_units": sum(i["OnHand"] for i in items),
        "total_committed": sum(i["Committed"] for i in items),
        "items": items[:50],  # Top 50 by quantity
    }


# ------------------------------------------------------------------
# HEALTH CHECK
# ------------------------------------------------------------------

@router.get("/health")
async def debug_health(request: Request):
    """
    Check if API service is properly authenticated.
    
    Example: /debug/health
    """
    token = await get_token_from_header(request)
    if token:
        return {
            "authenticated": True,
            "token_preview": f"{token[:15]}...{token[-5:]}" if len(token) > 20 else "***",
            "message": "Token present - API calls will be authenticated"
        }
    else:
        return {
            "authenticated": False,
            "token_preview": None,
            "message": "No token found - API calls will fail"
        }