"""Anomaly detection endpoints for AI routes (Manager only)"""

from fastapi import APIRouter, Depends, Query
from typing import Dict, Optional
from datetime import datetime
import logging

from .utils import utf8_json_response
from app.api.dependencies import require_manager_role, get_token_from_header, get_company_code
from app.services.anomaly_detection_service import get_anomaly_detection_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/anomalies/scan")
async def scan_anomalies(
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Run anomaly detection scan.
    Manager-only endpoint.
    """
    anomaly_service = get_anomaly_detection_service()
    
    results = await anomaly_service.scan_all_anomalies(
        tenant_code=company_code,
        user_token=user_token
    )
    
    from dataclasses import asdict
    response = {
        "success": True,
        "sales_anomalies": [asdict(a) for a in results["sales_anomalies"]],
        "stock_anomalies": [asdict(a) for a in results["stock_anomalies"]],
        "pricing_anomalies": [asdict(a) for a in results["pricing_anomalies"]],
        "total_count": len(results["sales_anomalies"]) + len(results["stock_anomalies"]) + len(results["pricing_anomalies"]),
        "timestamp": datetime.now().isoformat()
    }
    
    return utf8_json_response(response)


@router.get("/anomalies/sales")
async def get_sales_anomalies(
    item_code: Optional[str] = None,
    days: int = Query(30, ge=7, le=90),
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Detect sales anomalies.
    Manager-only endpoint.
    """
    anomaly_service = get_anomaly_detection_service()
    
    anomalies = await anomaly_service.detect_sales_anomalies(
        tenant_code=company_code,
        item_code=item_code,
        days=days,
        user_token=user_token
    )
    
    from dataclasses import asdict
    return utf8_json_response({
        "success": True,
        "anomalies": [asdict(a) for a in anomalies],
        "count": len(anomalies),
        "item_code": item_code or "ALL",
        "days_analyzed": days
    })


@router.get("/anomalies/stock")
async def get_stock_anomalies(
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Detect stock anomalies.
    Manager-only endpoint.
    """
    anomaly_service = get_anomaly_detection_service()
    
    anomalies = await anomaly_service.detect_stock_anomalies(
        tenant_code=company_code,
        user_token=user_token
    )
    
    from dataclasses import asdict
    return utf8_json_response({
        "success": True,
        "anomalies": [asdict(a) for a in anomalies],
        "count": len(anomalies)
    })


@router.get("/anomalies/pricing")
async def get_pricing_anomalies(
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Detect pricing anomalies.
    Manager-only endpoint.
    """
    anomaly_service = get_anomaly_detection_service()
    
    anomalies = await anomaly_service.detect_pricing_anomalies(
        tenant_code=company_code,
        user_token=user_token
    )
    
    from dataclasses import asdict
    return utf8_json_response({
        "success": True,
        "anomalies": [asdict(a) for a in anomalies],
        "count": len(anomalies)
    })