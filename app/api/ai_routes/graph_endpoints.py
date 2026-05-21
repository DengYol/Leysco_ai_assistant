"""Knowledge Graph endpoints for AI routes (Manager only)"""

from fastapi import APIRouter, Depends, Query
from typing import Dict
import logging

from .utils import utf8_json_response
from app.api.dependencies import require_manager_role, get_token_from_header, get_company_code
from app.services.knowledge_graph import get_knowledge_graph
from app.services.leysco_api.client import create_api_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/graph/build")
async def build_knowledge_graph(
    context: Dict = Depends(require_manager_role),
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code)
):
    """
    Build knowledge graph from sales data.
    Manager-only endpoint.
    """
    api_service = create_api_service(user_token=user_token)
    kg_service = get_knowledge_graph()
    
    logger.info("Fetching data for knowledge graph...")
    
    items = api_service.get_items(limit=1000)
    logger.info(f"Loaded {len(items)} items")
    
    customers = api_service.get_customers(limit=500)
    logger.info(f"Loaded {len(customers)} customers")
    
    orders = []
    for customer in customers[:50]:
        customer_orders = api_service.get_customer_orders(
            customer_code=customer.get("CardCode"),
            limit=50
        )
        orders.extend(customer_orders)
    logger.info(f"Loaded {len(orders)} orders")
    
    warehouses = api_service.get_warehouses()
    logger.info(f"Loaded {len(warehouses)} warehouses")
    
    await kg_service.build_from_sales_data(
        orders=orders,
        items=items,
        customers=customers,
        warehouses=warehouses
    )
    
    stats = kg_service.get_graph_stats()
    
    return utf8_json_response({
        "success": True,
        "message": "Knowledge graph built successfully",
        "stats": stats
    })


@router.get("/graph/recommendations/cross-sell/{product_code}")
async def get_cross_sell_recommendations_graph(
    product_code: str,
    limit: int = Query(5, ge=1, le=20),
    context: Dict = Depends(require_manager_role)
):
    """
    Get cross-sell recommendations from knowledge graph.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    recommendations = await kg_service.get_cross_sell_recommendations(
        product_code=product_code,
        limit=limit
    )
    
    return utf8_json_response({
        "success": True,
        "product_code": product_code,
        "recommendations": recommendations,
        "source": "knowledge_graph"
    })


@router.get("/graph/recommendations/upsell/{product_code}")
async def get_upsell_recommendations_graph(
    product_code: str,
    limit: int = Query(5, ge=1, le=20),
    context: Dict = Depends(require_manager_role)
):
    """
    Get upsell recommendations from knowledge graph.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    recommendations = await kg_service.get_upsell_recommendations(
        product_code=product_code,
        limit=limit
    )
    
    return utf8_json_response({
        "success": True,
        "product_code": product_code,
        "recommendations": recommendations,
        "source": "knowledge_graph"
    })


@router.get("/graph/customer/{customer_code}")
async def get_customer_graph_insights(
    customer_code: str,
    context: Dict = Depends(require_manager_role)
):
    """
    Get customer insights from knowledge graph.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    insights = await kg_service.get_customer_purchase_pattern(customer_code)
    
    return utf8_json_response({
        "success": True,
        **insights,
        "source": "knowledge_graph"
    })


@router.get("/graph/substitutes/{product_code}")
async def get_product_substitutes(
    product_code: str,
    limit: int = Query(5, ge=1, le=20),
    context: Dict = Depends(require_manager_role)
):
    """
    Find substitute products from knowledge graph.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    substitutes = await kg_service.find_substitutes(product_code, limit)
    
    return utf8_json_response({
        "success": True,
        "product_code": product_code,
        "substitutes": substitutes,
        "source": "knowledge_graph"
    })


@router.get("/graph/complements/{product_code}")
async def get_product_complements(
    product_code: str,
    limit: int = Query(5, ge=1, le=20),
    context: Dict = Depends(require_manager_role)
):
    """
    Find complementary products from knowledge graph.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    complements = await kg_service.find_complements(product_code, limit)
    
    return utf8_json_response({
        "success": True,
        "product_code": product_code,
        "complements": complements,
        "source": "knowledge_graph"
    })


@router.get("/graph/stats")
async def get_graph_stats(
    context: Dict = Depends(require_manager_role)
):
    """
    Get knowledge graph statistics.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    stats = kg_service.get_graph_stats()
    
    return utf8_json_response({
        "success": True,
        **stats
    })


@router.get("/graph/export")
async def export_knowledge_graph(
    format: str = Query("json", pattern="^(json|cypher)$"),
    context: Dict = Depends(require_manager_role)
):
    """
    Export knowledge graph for visualization.
    Manager-only endpoint.
    """
    kg_service = get_knowledge_graph()
    
    if format == "json":
        export_data = await kg_service.export_graph("json")
        return utf8_json_response({
            "success": True,
            "format": "json",
            **export_data
        })
    else:
        return utf8_json_response({
            "success": True,
            "message": "Cypher export not implemented yet",
            "format": "cypher"
        })