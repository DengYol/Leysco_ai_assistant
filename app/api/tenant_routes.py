"""
app/api/tenant_routes.py
========================
Tenant-aware API routes that match Flutter app expectations.
Translates Flutter route patterns to Leysco API calls.

UPDATED FOR PHASE 2: Added delivery endpoints (outstanding, history, track)
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from pydantic import BaseModel

from app.api.dependencies import get_token_from_header
from app.core.tenant_context import TenantContext, set_current_tenant, clear_current_tenant
from app.services.leysco_api_service import create_api_service
from app.services.pricing_service import create_pricing_service
from app.services.db_query_service import create_db_query_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Tenant API"])


# =========================================================
# Request/Response Models
# =========================================================

class LoginRequest(BaseModel):
    username: str
    password: str
    tenant_id: str


class ExpenseRequest(BaseModel):
    amount: float
    category: str
    description: str
    date: str
    payment_method: str = "cash"
    reference: Optional[str] = None


class QuotationRequest(BaseModel):
    customer_code: str
    customer_name: Optional[str] = None
    items: List[Dict]  # [{"item_code": "XXX", "quantity": 10, "price": 100}]
    valid_until: Optional[str] = None
    remarks: Optional[str] = None


# =========================================================
# Helper to set tenant context from path
# =========================================================

async def set_tenant_context(tenant_id: str, user_token: str) -> TenantContext:
    """Create and set tenant context from path parameter"""
    tenant = TenantContext(
        company_code=tenant_id.upper(),
        company_id=0,  # Will be resolved from token
        user_id=0,
        user_email="",
        user_role="user",
        user_token=user_token
    )
    set_current_tenant(tenant)
    return tenant


# =========================================================
# 1. LOGIN ENDPOINT
# =========================================================

@router.post("/login")
async def login(request: LoginRequest):
    """
    Authenticate user and return token.
    Matches Flutter's POST /login endpoint.
    """
    try:
        # Create temporary API service
        api_service = create_api_service(user_token=None)
        
        # Authenticate with Leysco
        success = api_service.login(request.username, request.password)
        
        if not success:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Return token in format Flutter expects
        return {
            "success": True,
            "access_token": api_service.user_token,
            "token_type": "bearer",
            "tenant_id": request.tenant_id,
            "user": {
                "username": request.username,
                "role": "user"
            }
        }
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=401, detail=str(e))


# =========================================================
# 2. ITEMS ENDPOINT - /{tenant_id}/items
# =========================================================

@router.get("/{tenant_id}/items")
async def get_items(
    tenant_id: str = Path(..., description="Tenant ID"),
    search: Optional[str] = Query(None, description="Search term"),
    limit: int = Query(50, ge=1, le=200, description="Max items to return"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Get items for specific tenant.
    Flutter route: GET /{tenantId}/items
    Maps to: Leysco /item_masterdata
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # Create API service with user token
        api_service = create_api_service(user_token=user_token)
        
        # Fetch items
        items = api_service.get_items(search=search or "", limit=limit)
        
        # Transform to Flutter-friendly format
        formatted_items = []
        for item in items:
            formatted_items.append({
                "id": item.get("id"),
                "item_code": item.get("ItemCode"),
                "item_name": item.get("ItemName"),
                "description": item.get("ItemDesc", ""),
                "group": (item.get("item_group") or {}).get("ItmsGrpNam", ""),
                "sell_item": item.get("SellItem") == "Y",
                "purchase_item": item.get("PrchseItem") == "Y",
                "inventory_item": item.get("InvntItem") == "Y",
                "on_hand": float(item.get("OnHand", 0)),
                "is_committed": float(item.get("IsCommited", 0)),
                "available": float(item.get("OnHand", 0)) - float(item.get("IsCommited", 0))
            })
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "total": len(formatted_items),
            "items": formatted_items
        }
        
    except Exception as e:
        logger.error(f"Error in get_items: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


# =========================================================
# 3. INVENTORY ENDPOINT - /{tenant_id}/inventory/
# =========================================================

@router.get("/{tenant_id}/inventory/")
async def get_inventory(
    tenant_id: str = Path(..., description="Tenant ID"),
    search: Optional[str] = Query(None, description="Search term"),
    warehouse: Optional[str] = Query(None, description="Warehouse code"),
    limit: int = Query(100, ge=1, le=500, description="Max items to return"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Get inventory for specific tenant.
    Flutter route: GET /{tenantId}/inventory/
    Maps to: Leysco /inventory/report
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # Create API service with user token
        api_service = create_api_service(user_token=user_token)
        
        # Fetch inventory
        inventory = api_service.get_inventory_report(search=search or "", limit=limit)
        
        # Filter by warehouse if specified
        if warehouse:
            inventory = [i for i in inventory if i.get("WhsCode") == warehouse]
        
        # Transform to Flutter-friendly format
        formatted_inventory = []
        for item in inventory:
            on_hand = float(item.get("CurrentOnHand", 0))
            committed = float(item.get("CurrentIsCommited", 0))
            formatted_inventory.append({
                "item_code": item.get("ItemCode"),
                "item_name": item.get("ItemName"),
                "warehouse": item.get("WhsCode", "MAIN"),
                "on_hand": round(on_hand, 1),
                "committed": round(committed, 1),
                "available": round(on_hand - committed, 1),
                "last_transaction": item.get("LastTransactionDate", ""),
                "period_out_qty": float(item.get("PeriodOutQty", 0))
            })
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "total": len(formatted_inventory),
            "inventory": formatted_inventory
        }
        
    except Exception as e:
        logger.error(f"Error in get_inventory: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


# =========================================================
# 4. ORDERS ENDPOINT - /{tenant_id}/orders
# =========================================================

@router.get("/{tenant_id}/orders")
async def get_orders(
    tenant_id: str = Path(..., description="Tenant ID"),
    customer_code: Optional[str] = Query(None, description="Filter by customer code"),
    customer_name: Optional[str] = Query(None, description="Filter by customer name"),
    status: Optional[str] = Query(None, description="Order status (open, closed, all)"),
    from_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=200, description="Max orders to return"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Get orders for specific tenant.
    Flutter route: GET /{tenantId}/orders
    Maps to: Leysco /marketing/docs/17
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # Create API service with user token
        api_service = create_api_service(user_token=user_token)
        
        # Use the enhanced get_customer_orders method
        orders = api_service.get_customer_orders(
            customer_code=customer_code,
            customer_name=customer_name,
            limit=limit,
            doc_status=status or "all",
            from_date=from_date,
            to_date=to_date
        )
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "total": len(orders),
            "orders": orders
        }
        
    except Exception as e:
        logger.error(f"Error in get_orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


# =========================================================
# 5. CUSTOMERS ENDPOINT - /{tenant_id}/customers/
# =========================================================

@router.get("/{tenant_id}/customers/")
async def get_customers(
    tenant_id: str = Path(..., description="Tenant ID"),
    search: Optional[str] = Query(None, description="Search term"),
    limit: int = Query(50, ge=1, le=200, description="Max customers to return"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Get customers for specific tenant.
    Flutter route: GET /{tenantId}/customers/
    Maps to: Leysco /bp_masterdata
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # Create API service with user token
        api_service = create_api_service(user_token=user_token)
        
        # Fetch customers
        customers = api_service.get_customers(search=search or "", limit=limit)
        
        # Transform to Flutter-friendly format
        formatted_customers = []
        for customer in customers:
            formatted_customers.append({
                "code": customer.get("CardCode"),
                "name": customer.get("CardName"),
                "phone": customer.get("Phone1", ""),
                "email": customer.get("EmailAddress", ""),
                "city": customer.get("City", ""),
                "country": customer.get("Country", ""),
                "credit_limit": float(customer.get("CreditLimit", 0)),
                "balance": float(customer.get("CurrentBalance", 0)),
                "is_active": customer.get("Active", "Y") == "Y"
            })
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "total": len(formatted_customers),
            "customers": formatted_customers
        }
        
    except Exception as e:
        logger.error(f"Error in get_customers: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


# =========================================================
# 6. CUSTOMER DETAILS ENDPOINT - /{tenant_id}/customers/{customer_code}
# =========================================================

@router.get("/{tenant_id}/customers/{customer_code}")
async def get_customer_details(
    tenant_id: str = Path(..., description="Tenant ID"),
    customer_code: str = Path(..., description="Customer code"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Get customer details for specific customer.
    Flutter route: GET /{tenantId}/customers/{customerCode}
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # Create API service with user token
        api_service = create_api_service(user_token=user_token)
        
        # Search for customer by code
        customers = api_service.get_customers(search=customer_code, limit=5)
        
        # Find exact match
        customer = None
        for c in customers:
            if c.get("CardCode") == customer_code:
                customer = c
                break
        
        if not customer:
            raise HTTPException(status_code=404, detail=f"Customer {customer_code} not found")
        
        # Get orders for this customer
        db_service = create_db_query_service(user_token=user_token)
        orders = db_service.query(
            intent="GET_CUSTOMER_ORDERS",
            entities={"customer_name": customer.get("CardName")},
            language="en"
        )
        
        # Transform to Flutter-friendly format
        result = {
            "success": True,
            "tenant_id": tenant_id,
            "customer": {
                "code": customer.get("CardCode"),
                "name": customer.get("CardName"),
                "phone": customer.get("Phone1", ""),
                "email": customer.get("EmailAddress", ""),
                "city": customer.get("City", ""),
                "country": customer.get("Country", ""),
                "address": customer.get("Address", ""),
                "tax_id": customer.get("FederalTaxID", ""),
                "credit_limit": float(customer.get("CreditLimit", 0)),
                "balance": float(customer.get("CurrentBalance", 0)),
                "payment_terms": (customer.get("octg") or {}).get("PymntGroup", ""),
                "territory": (customer.get("territory") or {}).get("descript", "")
            },
            "orders": orders if orders else []
        }
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_customer_details: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


# =========================================================
# 7. DELIVERIES ENDPOINTS (NEW FOR PHASE 2)
# =========================================================

@router.get("/{tenant_id}/deliveries/outstanding")
async def get_outstanding_deliveries(
    tenant_id: str = Path(..., description="Tenant ID"),
    customer_code: Optional[str] = Query(None, description="Filter by customer code"),
    customer_name: Optional[str] = Query(None, description="Filter by customer name"),
    limit: int = Query(100, ge=1, le=500, description="Max deliveries to return"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Get outstanding deliveries for specific tenant.
    Flutter route: GET /{tenantId}/deliveries/outstanding
    
    Returns deliveries that are pending (not yet fully delivered).
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # Create API service with user token
        api_service = create_api_service(user_token=user_token)
        
        # Fetch outstanding deliveries
        deliveries = api_service.get_outstanding_deliveries(
            customer_code=customer_code,
            customer_name=customer_name,
            limit=limit
        )
        
        # Transform to Flutter-friendly format with summary
        total_value = sum(float(d.get("LineTotal", d.get("DocTotal", 0))) for d in deliveries)
        total_items = len(deliveries)
        
        # Group by document for summary
        documents = {}
        for d in deliveries:
            doc_num = d.get("DocNum")
            if doc_num not in documents:
                documents[doc_num] = {
                    "doc_num": doc_num,
                    "doc_date": d.get("DocDate", ""),
                    "customer_code": d.get("CardCode"),
                    "customer_name": d.get("CardName"),
                    "total_value": 0,
                    "items": []
                }
            documents[doc_num]["total_value"] += float(d.get("LineTotal", 0))
            documents[doc_num]["items"].append({
                "item_code": d.get("ItemCode"),
                "item_name": d.get("ItemName"),
                "quantity": d.get("OpenQty", 0),
                "price": d.get("Price", 0),
                "line_total": float(d.get("LineTotal", 0))
            })
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "summary": {
                "total_documents": len(documents),
                "total_items": total_items,
                "total_value": round(total_value, 2),
                "customers_affected": len(set(d.get("CardCode") for d in deliveries if d.get("CardCode")))
            },
            "documents": list(documents.values()),
            "deliveries": deliveries
        }
        
    except Exception as e:
        logger.error(f"Error in get_outstanding_deliveries: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


@router.get("/{tenant_id}/deliveries/history")
async def get_delivery_history(
    tenant_id: str = Path(..., description="Tenant ID"),
    customer_code: Optional[str] = Query(None, description="Filter by customer code"),
    customer_name: Optional[str] = Query(None, description="Filter by customer name"),
    from_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=500, description="Max deliveries to return"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Get delivery history for specific tenant.
    Flutter route: GET /{tenantId}/deliveries/history
    
    Returns completed/delivered deliveries (history).
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # Create API service with user token
        api_service = create_api_service(user_token=user_token)
        
        # Use marketing/docs/15 for deliveries (document type 15)
        url = f"{api_service.base_url}/marketing/docs/15"
        params = {
            "isDoc": 1,
            "page": 1,
            "per_page": limit,
            "DocStatus": 2,  # 2 = Closed/Completed
            "IsICT": "N",
            "created_by": "",
        }
        
        if customer_code:
            params["CardCode"] = customer_code
        if from_date:
            params["FromDate"] = from_date
        if to_date:
            params["ToDate"] = to_date
        
        # Resolve customer name to code if provided
        if customer_name and not customer_code:
            customer = api_service.resolve_customer(customer_name)
            if customer:
                params["CardCode"] = customer.get("CardCode")
        
        api_service._record_api_call()
        resp = api_service.session.get(url, params=params, timeout=30)
        
        if resp.status_code != 200:
            logger.warning(f"Delivery history API error: {resp.status_code}")
            return {
                "success": True,
                "tenant_id": tenant_id,
                "total": 0,
                "deliveries": [],
                "message": "No delivery history found"
            }
        
        data = resp.json()
        
        # Parse deliveries
        deliveries = []
        if data.get("ResultState") and data.get("ResponseData"):
            response_data = data["ResponseData"]
            if isinstance(response_data, dict):
                if "data" in response_data:
                    deliveries = response_data["data"]
                elif "DocumentLines" in response_data:
                    deliveries = [response_data]
            elif isinstance(response_data, list):
                deliveries = response_data
        
        # Transform to Flutter-friendly format
        formatted_deliveries = []
        for delivery in deliveries:
            formatted_deliveries.append({
                "doc_num": delivery.get("DocNum"),
                "doc_date": delivery.get("DocDate", ""),
                "customer_code": delivery.get("CardCode"),
                "customer_name": delivery.get("CardName", "Unknown"),
                "status": "Delivered",
                "total_value": float(delivery.get("DocTotal", 0)),
                "items_count": len(delivery.get("DocumentLines", []))
            })
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "total": len(formatted_deliveries),
            "deliveries": formatted_deliveries
        }
        
    except Exception as e:
        logger.error(f"Error in get_delivery_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


@router.get("/{tenant_id}/deliveries/{delivery_number}")
async def track_delivery(
    tenant_id: str = Path(..., description="Tenant ID"),
    delivery_number: str = Path(..., description="Delivery document number"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Track a specific delivery by document number.
    Flutter route: GET /{tenantId}/deliveries/{deliveryNumber}
    
    Returns detailed tracking information for a specific delivery.
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # Create API service with user token
        api_service = create_api_service(user_token=user_token)
        
        # Fetch delivery details from marketing/docs/15 endpoint
        url = f"{api_service.base_url}/marketing/docs/15/{delivery_number}"
        params = {"isDoc": 1}
        
        api_service._record_api_call()
        resp = api_service.session.get(url, params=params, timeout=30)
        
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Delivery {delivery_number} not found")
        
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Failed to fetch delivery: {resp.status_code}")
        
        data = resp.json()
        
        # Parse delivery details
        delivery = None
        if data.get("ResultState") and data.get("ResponseData"):
            delivery = data["ResponseData"]
            if isinstance(delivery, dict):
                pass
            elif isinstance(delivery, list) and delivery:
                delivery = delivery[0]
        
        if not delivery:
            raise HTTPException(status_code=404, detail=f"Delivery {delivery_number} not found")
        
        # Parse line items
        items = []
        line_items = delivery.get("DocumentLines", [])
        for item in line_items:
            items.append({
                "item_code": item.get("ItemCode"),
                "item_name": item.get("ItemName"),
                "quantity": float(item.get("Quantity", 0)),
                "delivered_quantity": float(item.get("Quantity", 0)) - float(item.get("OpenQty", 0)),
                "open_quantity": float(item.get("OpenQty", 0)),
                "price": float(item.get("Price", 0)),
                "line_total": float(item.get("LineTotal", 0))
            })
        
        # Determine delivery status
        status = "Completed"
        has_open = any(i.get("open_quantity", 0) > 0 for i in items)
        if has_open:
            status = "Partially Delivered"
        
        result = {
            "success": True,
            "tenant_id": tenant_id,
            "delivery": {
                "doc_num": delivery.get("DocNum"),
                "doc_entry": delivery.get("DocEntry"),
                "doc_date": delivery.get("DocDate", ""),
                "due_date": delivery.get("DocDueDate", ""),
                "customer_code": delivery.get("CardCode"),
                "customer_name": delivery.get("CardName", "Unknown"),
                "status": status,
                "total_value": float(delivery.get("DocTotal", 0)),
                "remarks": delivery.get("Comments", ""),
                "items": items,
                "items_count": len(items)
            }
        }
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in track_delivery: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


# =========================================================
# 8. EXPENSES ENDPOINT - /{tenant_id}/expenses
# =========================================================

@router.post("/{tenant_id}/expenses")
async def create_expense(
    tenant_id: str = Path(..., description="Tenant ID"),
    expense: ExpenseRequest = None,
    user_token: str = Depends(get_token_from_header)
):
    """
    Create an expense record.
    Flutter route: POST /{tenantId}/expenses
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # TODO: Implement actual expense creation in Leysco
        # For now, return success with placeholder
        
        logger.info(f"Expense created for tenant {tenant_id}: {expense.dict() if expense else 'No data'}")
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "expense": {
                "id": f"EXP_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "amount": expense.amount if expense else 0,
                "category": expense.category if expense else "unknown",
                "description": expense.description if expense else "",
                "date": expense.date if expense else datetime.now().strftime("%Y-%m-%d"),
                "payment_method": expense.payment_method if expense else "cash",
                "reference": expense.reference if expense else None,
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            },
            "message": "Expense recorded successfully"
        }
        
    except Exception as e:
        logger.error(f"Error creating expense: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


@router.get("/{tenant_id}/expenses")
async def get_expenses(
    tenant_id: str = Path(..., description="Tenant ID"),
    from_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=200, description="Max expenses to return"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Get expenses for specific tenant.
    Flutter route: GET /{tenantId}/expenses
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # TODO: Implement actual expense retrieval from Leysco
        # For now, return empty list with placeholder
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "total": 0,
            "expenses": [],
            "message": "Expense history feature coming soon"
        }
        
    except Exception as e:
        logger.error(f"Error getting expenses: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


# =========================================================
# 9. PRICE CHECK ENDPOINT - /{tenant_id}/price
# =========================================================

@router.get("/{tenant_id}/price")
async def check_price(
    tenant_id: str = Path(..., description="Tenant ID"),
    item_code: str = Query(..., description="Item code"),
    customer_code: Optional[str] = Query(None, description="Customer code for special pricing"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Check price for an item.
    Flutter route: GET /{tenantId}/price?item_code=XXX&customer_code=YYY
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # Create pricing service
        pricing_service = create_pricing_service(user_token=user_token)
        
        # Get price
        if customer_code:
            # Get customer details first
            api_service = create_api_service(user_token=user_token)
            customers = api_service.get_customers(search=customer_code, limit=5)
            customer = None
            for c in customers:
                if c.get("CardCode") == customer_code:
                    customer = c
                    break
            
            if customer:
                price_result = pricing_service.get_price_for_customer(
                    item_code=item_code,
                    customer=customer
                )
            else:
                price_result = pricing_service.get_price(item_code=item_code)
        else:
            price_result = pricing_service.get_price(item_code=item_code)
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "item_code": item_code,
            "price": price_result.get("price"),
            "currency": price_result.get("currency", "KES"),
            "price_list": price_result.get("price_list_name"),
            "found": price_result.get("found", False),
            "message": price_result.get("note", "")
        }
        
    except Exception as e:
        logger.error(f"Error checking price: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


# =========================================================
# 10. QUOTATIONS ENDPOINTS (NEW FOR PHASE 2)
# =========================================================

@router.post("/{tenant_id}/quotations")
async def create_quotation(
    tenant_id: str = Path(..., description="Tenant ID"),
    quotation: QuotationRequest = None,
    user_token: str = Depends(get_token_from_header)
):
    """
    Create a quotation for a customer.
    Flutter route: POST /{tenantId}/quotations
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        if not quotation:
            raise HTTPException(status_code=400, detail="Quotation data required")
        
        if not quotation.items:
            raise HTTPException(status_code=400, detail="At least one item is required")
        
        # Create API service
        api_service = create_api_service(user_token=user_token)
        
        # Build quotation payload
        payload = {
            "CardCode": quotation.customer_code,
            "CardName": quotation.customer_name or "",
            "DocDate": datetime.now().strftime("%Y-%m-%d"),
            "DocDueDate": quotation.valid_until or (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            "Comments": quotation.remarks or "",
            "DocumentLines": []
        }
        
        # Add items
        for item in quotation.items:
            payload["DocumentLines"].append({
                "ItemCode": item.get("item_code"),
                "Quantity": float(item.get("quantity", 1)),
                "Price": float(item.get("price", 0)),
                "UnitPrice": float(item.get("price", 0)),
                "LineTotal": float(item.get("quantity", 1)) * float(item.get("price", 0))
            })
        
        # Try to create quotation via API
        url = f"{api_service.base_url}/marketing/docs/23"
        api_service._record_api_call()
        resp = api_service.session.post(url, json=payload, timeout=30)
        
        if resp.status_code == 200 or resp.status_code == 201:
            data = resp.json()
            return {
                "success": True,
                "tenant_id": tenant_id,
                "quotation": {
                    "doc_num": data.get("DocNum") or data.get("ResponseData", {}).get("DocNum"),
                    "customer_code": quotation.customer_code,
                    "customer_name": quotation.customer_name,
                    "items": quotation.items,
                    "total_amount": sum(i.get("quantity", 1) * i.get("price", 0) for i in quotation.items),
                    "valid_until": quotation.valid_until,
                    "created_at": datetime.now().isoformat(),
                    "status": "Draft"
                },
                "message": "Quotation created successfully"
            }
        else:
            logger.error(f"Failed to create quotation: {resp.status_code} - {resp.text[:500]}")
            raise HTTPException(status_code=resp.status_code, detail="Failed to create quotation")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating quotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


@router.get("/{tenant_id}/quotations")
async def get_quotations(
    tenant_id: str = Path(..., description="Tenant ID"),
    customer_code: Optional[str] = Query(None, description="Filter by customer code"),
    status: Optional[str] = Query(None, description="Quotation status (draft, sent, accepted, expired)"),
    limit: int = Query(50, ge=1, le=200, description="Max quotations to return"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Get quotations for specific tenant.
    Flutter route: GET /{tenantId}/quotations
    """
    try:
        # Set tenant context
        await set_tenant_context(tenant_id, user_token)
        
        # Create API service
        api_service = create_api_service(user_token=user_token)
        
        # Fetch quotations from marketing/docs/23
        url = f"{api_service.base_url}/marketing/docs/23"
        params = {
            "page": 1,
            "per_page": limit,
            "isDoc": 1
        }
        
        if customer_code:
            params["CardCode"] = customer_code
        
        api_service._record_api_call()
        resp = api_service.session.get(url, params=params, timeout=30)
        
        if resp.status_code != 200:
            return {
                "success": True,
                "tenant_id": tenant_id,
                "total": 0,
                "quotations": [],
                "message": "No quotations found"
            }
        
        data = resp.json()
        
        # Parse quotations
        quotations = []
        if data.get("ResultState") and data.get("ResponseData"):
            response_data = data["ResponseData"]
            if isinstance(response_data, dict):
                if "data" in response_data:
                    quotations = response_data["data"]
                elif "DocumentLines" in response_data:
                    quotations = [response_data]
            elif isinstance(response_data, list):
                quotations = response_data
        
        # Transform to Flutter-friendly format
        formatted_quotations = []
        for q in quotations:
            formatted_quotations.append({
                "doc_num": q.get("DocNum"),
                "doc_date": q.get("DocDate", ""),
                "valid_until": q.get("DocDueDate", ""),
                "customer_code": q.get("CardCode"),
                "customer_name": q.get("CardName", "Unknown"),
                "total_amount": float(q.get("DocTotal", 0)),
                "status": "Draft",
                "items_count": len(q.get("DocumentLines", []))
            })
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "total": len(formatted_quotations),
            "quotations": formatted_quotations
        }
        
    except Exception as e:
        logger.error(f"Error getting quotations: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        clear_current_tenant()


# =========================================================
# 11. HEALTH CHECK FOR TENANT
# =========================================================

@router.get("/{tenant_id}/health")
async def tenant_health_check(
    tenant_id: str = Path(..., description="Tenant ID"),
    user_token: str = Depends(get_token_from_header)
):
    """
    Health check for specific tenant.
    """
    try:
        await set_tenant_context(tenant_id, user_token)
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "status": "healthy",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "success": False,
            "tenant_id": tenant_id,
            "status": "unhealthy",
            "error": str(e)
        }
    finally:
        clear_current_tenant()