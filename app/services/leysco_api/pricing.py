"""Pricing operations for items"""

import logging
from typing import Dict, Optional

from .cache import cache_api_result
from .constants import PRICE_CACHE_TTL
from .utils import safe_float

logger = logging.getLogger(__name__)


class PricingHandler:
    """Handles price lookup operations"""
    
    def __init__(self, parent):
        self.parent = parent
        self.session = parent.session
        self.base_url = parent.base_url
        self.auth_handler = parent.auth_handler
        self._pricing_service = None
    
    def _record_cache_hit(self):
        """Record cache hit for statistics."""
        if hasattr(self.parent, '_record_cache_hit'):
            self.parent._record_cache_hit()
    
    def _record_cache_miss(self):
        """Record cache miss for statistics."""
        if hasattr(self.parent, '_record_cache_miss'):
            self.parent._record_cache_miss()
    
    @property
    def pricing_service(self):
        """Lazy load pricing service with user token."""
        if self._pricing_service is None:
            from app.services.pricing_service import create_pricing_service
            # Pass the user token from parent
            user_token = self.auth_handler.user_token if self.auth_handler else None
            self._pricing_service = create_pricing_service(user_token=user_token)
        return self._pricing_service
    
    @cache_api_result(ttl_seconds=PRICE_CACHE_TTL, key_prefix="item_price")
    def get_item_price(
        self, 
        item_code: str, 
        customer_name: Optional[str] = None,
        sap_list_num: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Get price for a specific item code using the Pricing Service.
        
        Args:
            item_code: The ItemCode from SAP
            customer_name: Optional customer name for customer-specific pricing
            sap_list_num: Optional SAP price list number (overrides customer lookup)
        
        Returns:
            Dictionary with price information
        """
        try:
            # If customer name is provided, try to resolve customer and get their price list
            customer = None
            if customer_name and not sap_list_num:
                customer = self.parent.business_partners.resolve_customer(customer_name)
                if customer:
                    logger.info(f"✅ Resolved customer: {customer.get('CardName')}")
            
            # Use pricing service to get price
            if customer and not sap_list_num:
                price_result = self.pricing_service.get_price_for_customer(
                    item_code=item_code,
                    customer=customer
                )
            else:
                list_num = sap_list_num or 1
                price_result = self.pricing_service.get_price(
                    item_code=item_code,
                    sap_list_num=list_num
                )
            
            if price_result and price_result.get("found") and price_result.get("price", 0) > 0:
                return {
                    "found": True,
                    "item_code": item_code,
                    "price": safe_float(price_result.get("price")),
                    "currency": price_result.get("currency", "KES"),
                    "price_list_name": price_result.get("price_list_name", ""),
                    "is_gross_price": price_result.get("is_gross_price", False),
                    "uom_entry": price_result.get("uom_entry"),
                    "note": price_result.get("note", ""),
                    "sap_list_num": price_result.get("sap_list_num"),
                    "chain_walked": price_result.get("chain_walked", [])
                }
            else:
                return {
                    "found": False,
                    "item_code": item_code,
                    "price": 0,
                    "message": price_result.get("note", "No price configured for this item"),
                    "price_list_name": price_result.get("price_list_name", ""),
                    "chain_walked": price_result.get("chain_walked", [])
                }
                
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to get item price for {item_code}: {e}")
            return {
                "found": False,
                "item_code": item_code,
                "price": 0,
                "error": str(e),
                "message": "Could not retrieve price at this time"
            }
    
    def get_item_price_any_list(self, item_code: str) -> Optional[Dict]:
        """Try all price lists to find a price for an item"""
        try:
            price_result = self.pricing_service.get_price_any_list(item_code=item_code)
            
            if price_result and price_result.get("found") and price_result.get("price", 0) > 0:
                return {
                    "found": True,
                    "item_code": item_code,
                    "price": safe_float(price_result.get("price")),
                    "currency": price_result.get("currency", "KES"),
                    "price_list_name": price_result.get("price_list_name", ""),
                    "is_gross_price": price_result.get("is_gross_price", False),
                    "uom_entry": price_result.get("uom_entry"),
                    "note": price_result.get("note", ""),
                    "sap_list_num": price_result.get("sap_list_num")
                }
            else:
                return {
                    "found": False,
                    "item_code": item_code,
                    "price": 0,
                    "message": price_result.get("note", "No price found on any list")
                }
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to get price from any list for {item_code}: {e}")
            return {
                "found": False,
                "item_code": item_code,
                "price": 0,
                "error": str(e),
                "message": "Could not retrieve price at this time"
            }