"""Quotation endpoints for AI routes"""

from fastapi import APIRouter, Depends, Query
from typing import Optional, Dict
import logging

from .utils import utf8_json_response
from app.api.dependencies import (
    get_token_from_header,
    get_company_code,
    get_conversation_context
)
from app.ai_engine.action_router import create_action_router

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/quotation/{quotation_id}")
async def get_quotation_by_id(
    quotation_id: str,
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code),
    conv_context: Dict = Depends(get_conversation_context)
):
    """
    Get a single quotation by ID.
    Called by Flutter when user clicks View/Print/Send buttons.

    FIXED: company_code now forwarded to create_action_router so the
    LeyscoAPIService resolves the correct base URL (.../api/v1) instead
    of the bare domain, which caused all fetches to return 404.
    """
    try:
        if not user_token:
            return utf8_json_response({
                "success": False,
                "message": "Not authenticated. Please log in again."
            }, status_code=401)

        logger.info(f"Fetching quotation by ID: {quotation_id}")

        # FIXED: pass company_code so base_url resolves to .../api/v1
        action_router = create_action_router(
            user_token=user_token,
            company_code=company_code
        )

        quotation = await action_router.quotation.get_quotation_by_id(quotation_id)

        if not quotation:
            # FALLBACK: quotation_id might actually be a CardCode suffix or
            # the DocNum was never returned by the creation API.
            # Try fetching the latest quotation across all customers.
            logger.warning(
                f"Quotation {quotation_id} not found by DocNum — "
                "trying latest-quotation fallback"
            )
            quotation = action_router.quotation.get_quotation(quotation_id)

        if not quotation:
            logger.warning(f"Quotation {quotation_id} not found")
            return utf8_json_response({
                "success": False,
                "message": (
                    f"Quotation #{quotation_id} not found. "
                    "It may still be processing — please check the Quotations list."
                )
            }, status_code=404)

        logger.info(f"Successfully fetched quotation {quotation_id}")
        return utf8_json_response({
            "success": True,
            "quotation": quotation
        })

    except Exception as e:
        logger.error(f"Error fetching quotation {quotation_id}: {e}", exc_info=True)
        return utf8_json_response({
            "success": False,
            "message": f"Error fetching quotation: {str(e)}"
        }, status_code=500)


@router.get("/quotations")
async def get_quotations(
    limit: int = Query(10, ge=1, le=100),
    customer: Optional[str] = None,
    user_token: str = Depends(get_token_from_header),
    company_code: str = Depends(get_company_code),
    conv_context: Dict = Depends(get_conversation_context)
):
    """
    Get list of quotations.
    Called by Flutter to show quotation history.

    FIXED: company_code now forwarded to create_action_router.
    """
    try:
        if not user_token:
            return utf8_json_response({
                "success": False,
                "message": "Not authenticated. Please log in again."
            }, status_code=401)

        logger.info(f"Fetching quotations, limit={limit}, customer={customer}")

        # FIXED: pass company_code so base_url resolves to .../api/v1
        action_router = create_action_router(
            user_token=user_token,
            company_code=company_code
        )

        if customer:
            customer_obj = action_router.api.resolve_customer(customer)
            if customer_obj:
                customer_code_resolved = customer_obj.get("CardCode")
                quotations = action_router.quotation.get_customer_quotations(
                    customer_code=customer_code_resolved,
                    per_page=limit
                )
            else:
                quotations = []
        else:
            quotations = action_router.api.get_quotations(limit=limit)

        return utf8_json_response({
            "success": True,
            "quotations": quotations
        })

    except Exception as e:
        logger.error(f"Error fetching quotations: {e}", exc_info=True)
        return utf8_json_response({
            "success": False,
            "message": f"Error fetching quotations: {str(e)}"
        }, status_code=500)