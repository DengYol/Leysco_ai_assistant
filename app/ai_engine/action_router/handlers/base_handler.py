"""Base handler class for all intent handlers"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    """Base class for all intent handlers"""
    
    def __init__(self, action_router):
        """Initialize with reference to parent action router"""
        self.router = action_router
        self.api = action_router.api
        self.pricing = action_router.pricing
        self.warehouse = action_router.warehouse
        self.recommender = action_router.recommender
        self.delivery = action_router.delivery
        self.quotation = action_router.quotation
        self.health = action_router.health
        self.cache = action_router.cache
        self.customer_orders = action_router.customer_orders
        self.quotation_intelligence = action_router.quotation_intelligence
    
    @abstractmethod
    def handle(self, entities: dict, message: str, language: str) -> dict:
        """Handle the intent - to be implemented by subclasses"""
        pass
    
    def _missing(self, what: str, language: str = "en") -> dict:
        """Return missing parameter message"""
        if language == "sw":
            swahili_what = {
                "an item name": "jina la bidhaa",
                "a customer name": "jina la mteja",
                "a warehouse name": "jina la ghala",
                "a delivery number": "namba ya usafirishaji",
                "the item you want details for": "bidhaa unayotaka maelezo yake",
            }.get(what, what)
            return {"message": f"Tafadhali taja {swahili_what}.", "data": []}
        return {"message": f"Please specify {what}.", "data": []}
    
    def _not_found(self, what: str, value: str, language: str = "en") -> dict:
        """Return not found message"""
        if language == "sw":
            swahili_what = {"Warehouse": "Ghala", "Order": "Oda", "Quotation": "Nukuu"}.get(what, what)
            return {"message": f"{swahili_what} '{value}' haipatikani.", "data": []}
        return {"message": f"{what} '{value}' not found.", "data": []}