"""Main ActionRouter class - coordinates all intent handlers

OPTIMIZED: Services are now initialized lazily (only when first used).
This eliminates the ~10s startup cost on every request caused by eager
initialization of PricingService, WarehouseService, CustomerHealthService,
and QuotationIntelligence — each of which made blocking HTTP calls on __init__.
"""

from typing import Dict, Any, Optional
import logging
import random
from datetime import datetime

from .constants import DATA_INTENTS, GREETING_RESPONSES, SMALL_TALK_RESPONSES
from .handlers.item_handler import ItemHandler
from .handlers.customer_handler import CustomerHandler
from .handlers.pricing_handler import PricingHandler
from .handlers.quotation_handler import QuotationHandler
from .handlers.delivery_handler import DeliveryHandler
from .handlers.recommendation_handler import RecommendationHandler
from .handlers.knowledge_handler import KnowledgeHandler
from .handlers.analytics_handler import AnalyticsHandler
from .handlers.decision_handler import DecisionHandler
from .handlers.training_handler import TrainingHandler
from .utils.helpers import resolve_customer
from app.services.leysco_api.client import LeyscoAPIService, create_api_service
from app.services.pricing_service import PricingService, create_pricing_service
from app.services.warehouse_service import WarehouseService, create_warehouse_service
from app.services.recommendation_service import RecommendationService
from app.services.delivery_tracking_service import DeliveryTrackingService
from app.services.quotation_service import QuotationService
from app.services.customer_orders_service import CustomerOrdersService
from app.services.customer_health_service import CustomerHealthService, create_customer_health_service
from app.services.quotation_intelligence import create_quotation_intelligence
from app.services.cache_service import get_cache_service
from app.ai_engine.conversation_enhancer import ConversationEnhancer
from app.ai_engine.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class ActionRouter:
    def __init__(self, user_token: str = None, company_code: str = None):
        """
        Initialize ActionRouter with user token and company code.

        Services are NOT created here — they are created on first access
        via properties. This eliminates the blocking HTTP calls that were
        happening on every request.

        Args:
            user_token: Bearer token from authenticated user (REQUIRED for data access)
            company_code: Company code for multi-tenant URL resolution
        """
        self.user_token = user_token
        self.company_code = company_code

        if user_token:
            logger.info(f"ActionRouter initialized WITH user token: {user_token[:20]}... [company={company_code}]")
        else:
            logger.warning("ActionRouter initialized WITHOUT user token - API calls will fail")

        # Private backing fields for lazy services — all start as None
        self._api = None
        self._pricing = None
        self._warehouse = None
        self._recommender = None
        self._delivery = None
        self._quotation = None
        self._customer_orders = None
        self._health = None
        self._quotation_intelligence = None

        # Non-HTTP helpers — cheap to create eagerly
        self.cache = get_cache_service()
        self.conversation = ConversationEnhancer()
        self.formatter = ResponseFormatter()

        # Customer resolution cache (in-memory, lightweight)
        self._customer_resolution_cache = {}
        self._customer_cache_ttl = 300  # 5 minutes

        # Handlers are also lazy — they hold a reference to self and only
        # touch services when their handle_* methods are actually called.
        self._item_handler = None
        self._customer_handler = None
        self._pricing_handler = None
        self._quotation_handler = None
        self._delivery_handler = None
        self._recommendation_handler = None
        self._knowledge_handler = None
        self._analytics_handler = None
        self._decision_handler = None
        self._training_handler = None

    # ------------------------------------------------------------------
    # LAZY SERVICE PROPERTIES
    # Each property creates its service on first access and caches it.
    # ------------------------------------------------------------------

    @property
    def api(self) -> LeyscoAPIService:
        if self._api is None:
            # FIXED: company_code must be forwarded so _resolve_base_url
            # returns the correct tenant URL (e.g. .../api/v1).
            # Previously company_code was omitted, causing the URL to
            # resolve without /api/v1 and all /bp_masterdata calls to 404.
            self._api = (
                create_api_service(self.user_token, company_code=self.company_code)
                if self.user_token
                else LeyscoAPIService(company_code=self.company_code)
            )
        return self._api

    @property
    def pricing(self) -> PricingService:
        if self._pricing is None:
            self._pricing = create_pricing_service(
                user_token=self.user_token,
                company_code=self.company_code
            ) if self.user_token else PricingService()
        return self._pricing

    @property
    def warehouse(self) -> WarehouseService:
        if self._warehouse is None:
            self._warehouse = create_warehouse_service(
                user_token=self.user_token,
                company_code=self.company_code
            ) if self.user_token else WarehouseService()
        return self._warehouse

    @property
    def recommender(self) -> RecommendationService:
        if self._recommender is None:
            self._recommender = RecommendationService(self.api)
        return self._recommender

    @property
    def delivery(self) -> DeliveryTrackingService:
        if self._delivery is None:
            self._delivery = DeliveryTrackingService(self.api)
        return self._delivery

    @property
    def quotation(self) -> QuotationService:
        if self._quotation is None:
            self._quotation = QuotationService(self.api)
        return self._quotation

    @property
    def customer_orders(self) -> CustomerOrdersService:
        if self._customer_orders is None:
            self._customer_orders = CustomerOrdersService(self.api, self.pricing)
        return self._customer_orders

    @property
    def health(self) -> CustomerHealthService:
        if self._health is None:
            self._health = create_customer_health_service(
                user_token=self.user_token,
                company_code=self.company_code
            )
        return self._health

    @health.setter
    def health(self, value):
        """Allow set_user_token to replace the instance."""
        self._health = value

    @property
    def quotation_intelligence(self):
        if self._quotation_intelligence is None:
            self._quotation_intelligence = create_quotation_intelligence(
                user_token=self.user_token,
                company_code=self.company_code
            )
        return self._quotation_intelligence

    @quotation_intelligence.setter
    def quotation_intelligence(self, value):
        """Allow set_user_token to replace the instance."""
        self._quotation_intelligence = value

    # ------------------------------------------------------------------
    # LAZY HANDLER PROPERTIES
    # ------------------------------------------------------------------

    @property
    def item_handler(self) -> ItemHandler:
        if self._item_handler is None:
            self._item_handler = ItemHandler(self)
        return self._item_handler

    @property
    def customer_handler(self) -> CustomerHandler:
        if self._customer_handler is None:
            self._customer_handler = CustomerHandler(self.api, self.pricing, self.warehouse)
            self._customer_handler.router = self
        return self._customer_handler

    @property
    def pricing_handler(self) -> PricingHandler:
        if self._pricing_handler is None:
            self._pricing_handler = PricingHandler(self)
        return self._pricing_handler

    @property
    def quotation_handler(self) -> QuotationHandler:
        if self._quotation_handler is None:
            self._quotation_handler = QuotationHandler(self)
        return self._quotation_handler

    @property
    def delivery_handler(self) -> DeliveryHandler:
        if self._delivery_handler is None:
            self._delivery_handler = DeliveryHandler(self)
        return self._delivery_handler

    @property
    def recommendation_handler(self) -> RecommendationHandler:
        if self._recommendation_handler is None:
            self._recommendation_handler = RecommendationHandler(self)
        return self._recommendation_handler

    @property
    def knowledge_handler(self) -> KnowledgeHandler:
        if self._knowledge_handler is None:
            self._knowledge_handler = KnowledgeHandler(self)
        return self._knowledge_handler

    @property
    def analytics_handler(self) -> AnalyticsHandler:
        if self._analytics_handler is None:
            self._analytics_handler = AnalyticsHandler(self)
        return self._analytics_handler

    @property
    def decision_handler(self) -> DecisionHandler:
        if self._decision_handler is None:
            self._decision_handler = DecisionHandler(self)
        return self._decision_handler

    @property
    def training_handler(self) -> TrainingHandler:
        if self._training_handler is None:
            self._training_handler = TrainingHandler(self)
        return self._training_handler

    # ------------------------------------------------------------------
    # TOKEN MANAGEMENT
    # ------------------------------------------------------------------

    def set_user_token(self, token: str):
        """
        Update user token for all already-created services.
        Services that haven't been created yet will pick up the new token
        automatically when they are first accessed.
        """
        self.user_token = token

        # Only update services that have already been instantiated
        if self._api is not None:
            self._api.set_user_token(token)
        if self._pricing is not None:
            self._pricing.set_user_token(token)
        if self._warehouse is not None:
            self._warehouse.set_user_token(token)

        # Health and quotation_intelligence hold a token reference internally;
        # easiest to drop and recreate on next access.
        self._health = None
        self._quotation_intelligence = None

        logger.info(f"ActionRouter user token updated: {token[:20]}...")

    def set_company_code(self, company_code: str):
        """
        Update company code and recreate services that depend on it.
        """
        self.company_code = company_code
        # Drop ALL services that depend on company_code so they get
        # recreated with the correct base URL on next access.
        self._api = None
        self._pricing = None
        self._warehouse = None
        self._health = None
        self._quotation_intelligence = None
        # Drop the customer_handler too — it holds a reference to the
        # old api instance.
        self._customer_handler = None
        logger.info(f"ActionRouter company code updated to: {company_code}")

    # ------------------------------------------------------------------
    # CUSTOMER RESOLUTION
    # ------------------------------------------------------------------

    def _resolve_customer(self, customer_name: str, item_name: str = ""):
        """Resolve customer with caching."""
        return resolve_customer(
            customer_name=customer_name,
            item_name=item_name,
            api=self.api,
            cache=self._customer_resolution_cache,
            ttl=self._customer_cache_ttl
        )

    # ------------------------------------------------------------------
    # ROUTING
    # ------------------------------------------------------------------

    def route(self, intent: str, entities: dict, message: str = "", language: str = "en") -> dict:
        """Route intent to appropriate handler."""

        item_name = (entities.get("item_name") or "").strip()
        customer_name = (entities.get("customer_name") or "").strip()
        quantity = entities.get("quantity") or 10

        # Check authentication for data-sensitive intents
        if intent in DATA_INTENTS and not self.user_token:
            logger.warning(f"Intent '{intent}' requires authentication but no token available")
            if language == "sw":
                return {
                    "message": "Samahani, siwezi kupata data bila kuwa umeingia. Tafadhali ingia tena na ujaribu.",
                    "data": []
                }
            return {
                "message": "Sorry, I cannot fetch data without authentication. Please log in again and try.",
                "data": []
            }

        result = None

        handlers = {
            # Conversational
            "GREETING":   lambda: {"message": random.choice(GREETING_RESPONSES.get(language, GREETING_RESPONSES["en"])), "data": []},
            "THANKS":     lambda: {"message": "Karibu! Najulishe kama unahitaji kitu kingine chochote." if language == "sw" else "You're welcome! Let me know if you need anything else.", "data": []},
            "SMALL_TALK": lambda: {"message": random.choice(SMALL_TALK_RESPONSES.get(language, SMALL_TALK_RESPONSES["en"])), "data": []},
            "FAQ":        lambda: self.knowledge_handler.handle_faq(entities, message, language),

            # Training
            "TRAINING_MODULE":     lambda: self.training_handler.handle_module(entities, message, language),
            "TRAINING_VIDEO":      lambda: self.training_handler.handle_video(entities, message, language),
            "TRAINING_GUIDE":      lambda: self.training_handler.handle_guide(entities, message, language),
            "TRAINING_FAQ":        lambda: self.training_handler.handle_faq(entities, message, language),
            "TRAINING_GLOSSARY":   lambda: self.training_handler.handle_glossary(entities, message, language),
            "TRAINING_WEBINAR":    lambda: self.training_handler.handle_webinar(entities, message, language),
            "TRAINING_ONBOARDING": lambda: {"message": self.training_handler.handle_onboarding(language), "data": []},

            # Items
            "GET_ITEMS":             lambda: self.item_handler.get_items(item_name, quantity, language),
            "GET_SELLABLE_ITEMS":    lambda: self.item_handler.get_sellable_items(item_name, quantity, language),
            "GET_PURCHASABLE_ITEMS": lambda: self.item_handler.get_purchasable_items(item_name, quantity, language),
            "GET_INVENTORY_ITEMS":   lambda: self.item_handler.get_inventory_items(item_name, quantity, language),
            "GET_ITEMS_ADVANCED":    lambda: self.item_handler.get_items_advanced(item_name, quantity, warehouse_name=entities.get("warehouse", ""), language=language),
            "GET_ITEM_DETAILS":      lambda: self.item_handler.get_item_details(item_name, language),

            # Customers
            "GET_CUSTOMERS":            lambda: self.customer_handler.handle_get_customers(entities, message, language),
            "GET_CUSTOMER_DETAILS":     lambda: self.customer_handler.handle_get_customer_details(entities, message, language),
            "GET_CUSTOMER_HEALTH":      lambda: self.customer_handler.handle_get_customer_health(entities, message, language),
            "GET_CUSTOMER_ORDERS":      lambda: self.customer_handler.get_customer_orders(customer_name, quantity, language),
            "GET_CUSTOMER_INVOICES":    lambda: self.customer_handler.get_customer_invoices(customer_name, quantity, language),
            "GET_OUTSTANDING_INVOICES": lambda: self.customer_handler.get_customer_invoices(customer_name, quantity, language),

            # Pricing
            "GET_ITEM_PRICE":     lambda: self.pricing_handler.get_item_price(item_name, language),
            "GET_CUSTOMER_PRICE": lambda: self.pricing_handler.get_customer_price(item_name, customer_name, language),

            # Quotations
            "CREATE_QUOTATION":     lambda: self.quotation_handler.create_quotation(entities, message, language),
            "GET_QUOTATIONS":       lambda: self.quotation_handler.get_quotations(customer_name, quantity, language),
            "FOLLOW_UP_QUOTATIONS": lambda: self.quotation_handler.follow_up_quotations(entities, language),

            # Deliveries
            "GET_OUTSTANDING_DELIVERIES": lambda: self.delivery_handler.get_outstanding_deliveries(customer_name, quantity, language),
            "TRACK_DELIVERY":             lambda: self.delivery_handler.track_delivery(item_name, language),
            "GET_DELIVERY_HISTORY":       lambda: self.delivery_handler.get_delivery_history(customer_name, quantity, language),

            # Recommendations
            "RECOMMEND_ITEMS":              lambda: self.recommendation_handler.recommend_items(item_name, customer_name, quantity, language),
            "RECOMMEND_CUSTOMERS":          lambda: self.recommendation_handler.recommend_customers(item_name, customer_name, quantity, language),
            "GET_CROSS_SELL":               lambda: self.recommendation_handler.get_cross_sell(item_name, quantity, language),
            "GET_UPSELL":                   lambda: self.recommendation_handler.get_upsell(item_name, quantity, language),
            "GET_SEASONAL_RECOMMENDATIONS": lambda: self.recommendation_handler.get_seasonal(message, quantity, language),
            "GET_TRENDING_PRODUCTS":        lambda: self.recommendation_handler.get_trending(message, quantity, language),
            "FIND_CUSTOMERS_BY_ITEM":       lambda: self.recommendation_handler.find_customers_by_item(item_name, quantity, language),

            # Analytics
            "GET_TOP_SELLING_ITEMS": lambda: self.analytics_handler.get_top_selling_items(message, quantity, language),
            "GET_SLOW_MOVING_ITEMS": lambda: self.analytics_handler.get_slow_moving_items(message, quantity, language),
            "GET_SALES_ANALYTICS":   lambda: self.analytics_handler.get_sales_analytics(entities, message, language),

            # Decision Support
            "ANALYZE_INVENTORY_HEALTH":      lambda: self.decision_handler.analyze_inventory_health(entities, language),
            "GET_REORDER_DECISIONS":         lambda: self.decision_handler.get_reorder_decisions(entities, language),
            "ANALYZE_PRICING_OPPORTUNITIES": lambda: self.decision_handler.analyze_pricing_opportunities(entities, language),
            "ANALYZE_CUSTOMER_BEHAVIOR":     lambda: self.decision_handler.analyze_customer_behavior(customer_name, language),
            "FORECAST_DEMAND":               lambda: self.decision_handler.forecast_demand(item_name, quantity, language),

            # Knowledge Base
            "COMPANY_INFO":    lambda: self.knowledge_handler.company_info(language),
            "PRODUCT_INFO":    lambda: self.knowledge_handler.product_info(language),
            "HOW_TO_ORDER":    lambda: self.knowledge_handler.how_to_order(language),
            "PAYMENT_METHODS": lambda: self.knowledge_handler.payment_methods(language),
            "CONTACT_INFO":    lambda: self.knowledge_handler.contact_info(language),
            "POLICY_QUESTION": lambda: self.knowledge_handler.policy_question(language),

            # Warehouses
            "GET_WAREHOUSES":       lambda: self.item_handler.get_warehouses(entities.get("warehouse", ""), language),
            "GET_WAREHOUSE_STOCK":  lambda: self.item_handler.get_warehouse_stock(entities.get("warehouse", ""), language),
            "GET_LOW_STOCK_ALERTS": lambda: self.item_handler.get_low_stock_alerts(entities.get("warehouse", ""), language),

            # Stock
            "GET_STOCK_LEVELS": lambda: self.item_handler.get_items(item_name, quantity, language),
        }

        handler = handlers.get(intent)

        if handler:
            try:
                result = handler()
            except Exception as e:
                logger.error(f"Error in handler for {intent}: {e}", exc_info=True)
                if language == "sw":
                    result = {"message": f"Samahani, nilikumbana na hitilafu: {str(e)}", "data": []}
                else:
                    result = {"message": f"Sorry, I encountered an error: {str(e)}", "data": []}
        else:
            logger.warning(f"Intent '{intent}' not recognized")
            if language == "sw":
                result = {"message": "Samahani, sikuelewi. Tafadhali jaribu kuuliza swali tofauti.", "data": []}
            else:
                result = {"message": "Sorry, I don't understand that. Please try asking something else.", "data": []}

        # Apply conversation enhancer
        if result and "message" in result:
            enhanced_message = self.conversation.enhance(
                intent=intent,
                original_message=result.get("message", ""),
                data=result.get("data"),
                user_message=message
            )
            result["message"] = enhanced_message
            result["language"] = language

        return result

    def clear_cache(self):
        """Clear all caches in the action router."""
        self._customer_resolution_cache.clear()
        logger.info("ActionRouter cache cleared")