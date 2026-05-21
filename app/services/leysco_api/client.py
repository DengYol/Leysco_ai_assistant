"""Main LeyscoAPIService class - orchestrates all handlers

FIXED: base_url is now a parameter, not a hardcoded setting.
       Every service instance resolves its backend URL from the
       authenticated user's session, so dev100 tokens always talk
       to dev100-be, dev109 tokens always talk to dev109-be, etc.
"""

import logging
import os
from typing import Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests

from .constants import DEFAULT_TIMEOUT, DEFAULT_RETRY_TOTAL, DEFAULT_RETRY_BACKOFF
from .auth import AuthHandler
from .cache import CacheManager
from .business_partners import BusinessPartnerHandler
from .inventory import InventoryHandler
from .pricing import PricingHandler
from .orders import OrdersHandler
from .deliveries import DeliveriesHandler
from .analytics import AnalyticsHandler

logger = logging.getLogger(__name__)


class LeyscoAPIService:
    """
    Main API Service for Leysco Sales System.

    base_url is resolved per-tenant at construction time so that tokens
    issued by dev100-be are always validated and used against dev100-be,
    never accidentally against dev109-be or any other tenant's backend.
    """

    def __init__(self, user_token: str = None, base_url: str = None, company_code: str = None):
        """
        Initialize API service with user token and tenant-specific base URL.

        Args:
            user_token: Bearer token from the authenticated user.
            base_url:   Backend base URL for this tenant, e.g.
                        'https://dev100-be.leysco100.com'.
                        Falls back to settings / env var if omitted.
            company_code: Company code for multi-tenant URL resolution.
        """
        self.user_token = user_token
        self.company_code = company_code
        self.base_url = self._resolve_base_url(base_url, user_token, company_code)
        self.timeout = DEFAULT_TIMEOUT

        # Initialize session with connection pooling
        self.session = requests.Session()

        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=Retry(
                total=DEFAULT_RETRY_TOTAL,
                backoff_factor=DEFAULT_RETRY_BACKOFF,
                status_forcelist=[429, 500, 502, 503, 504],
            ),
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update({"Content-Type": "application/json"})

        # Initialize handlers
        self.auth_handler = AuthHandler(self.session, self.base_url, self.timeout)
        if user_token:
            self.auth_handler.set_user_token(user_token)

        self.cache_manager = CacheManager()
        self.business_partners = BusinessPartnerHandler(self)
        self.inventory = InventoryHandler(self)
        self.pricing = PricingHandler(self)
        self.orders = OrdersHandler(self)
        self.deliveries = DeliveriesHandler(self)
        self.analytics = AnalyticsHandler(self)

        self._stats = {"api_calls": 0, "errors": 0}

        logger.info(
            f"LeyscoAPIService initialized | backend: {self.base_url} | "
            f"company: {company_code} | token: {self._mask_token(user_token)}"
        )

    # ------------------------------------------------------------------
    # Base-URL resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_base_url(explicit_url: Optional[str], user_token: Optional[str], company_code: Optional[str] = None) -> str:
        """
        Resolve the backend base URL with the following priority:

        1. Explicit base_url argument passed by the caller            ← best
        2. Company code resolution (if company_code provided)         ← multi-tenant
        3. backend_url stored in the user's cached session            ← automatic
        4. LEYSCO_API_BASE_URL env var / settings                     ← fallback
        5. Hard error so misconfiguration is caught immediately
        """
        # 1. Caller supplied it explicitly
        if explicit_url:
            return explicit_url.rstrip("/")

        # 2. Company code resolution (multi-tenant)
        if company_code:
            try:
                from app.core.config import get_leysco_api_base_url
                url = get_leysco_api_base_url(company_code)
                if url:
                    logger.debug(f"🔀 base_url from company_code {company_code}: {url}")
                    return url.rstrip("/")
            except Exception as e:
                logger.debug(f"Could not resolve base_url from company_code: {e}")

        # 3. Look it up from the token session cache
        if user_token:
            try:
                from app.api.dependencies import UserSessionManager
                session = UserSessionManager.get(user_token)
                if session and session.get("backend_url"):
                    url = session["backend_url"].rstrip("/")
                    logger.debug(f"🔀 base_url from session cache: {url}")
                    return url
            except Exception as e:
                logger.debug(f"Could not read session cache for base_url: {e}")

        # 4. Global env / settings fallback
        try:
            from app.core.config import settings
            url = getattr(settings, "LEYSCO_API_BASE_URL", None)
        except Exception:
            url = None

        url = url or os.getenv("LEYSCO_API_BASE_URL")

        if url:
            logger.debug(f"🔀 base_url from settings/env: {url}")
            return url.rstrip("/")

        # 5. Nothing configured
        raise RuntimeError(
            "LeyscoAPIService: cannot resolve backend URL. "
            "Pass base_url explicitly, provide company_code, ensure the user session is cached, "
            "or set LEYSCO_API_BASE_URL in your environment."
        )

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------

    def _mask_token(self, token: str = None) -> str:
        t = token or self.auth_handler.user_token
        if not t:
            return "***NO_TOKEN***"
        if len(t) <= 12:
            return "***MASKED***"
        return f"{t[:8]}...{t[-4:]}"

    def set_user_token(self, token: str):
        self.user_token = token
        self.auth_handler.set_user_token(token)
        logger.debug(f"User token updated: {self._mask_token(token)}")
    
    def set_company_code(self, company_code: str):
        """Update company code and re-resolve base URL."""
        self.company_code = company_code
        if company_code:
            try:
                from app.core.config import get_leysco_api_base_url
                new_base_url = get_leysco_api_base_url(company_code).rstrip("/")
                if new_base_url != self.base_url:
                    self.base_url = new_base_url
                    logger.info(f"Base URL updated to: {self.base_url} for company {company_code}")
            except Exception as e:
                logger.error(f"Failed to update base URL for company {company_code}: {e}")

    # ------------------------------------------------------------------
    # Stats / cache
    # ------------------------------------------------------------------

    def _record_api_call(self):
        self._stats["api_calls"] += 1

    def _record_error(self):
        self._stats["errors"] += 1

    def _record_cache_hit(self):
        self.cache_manager.record_hit()

    def _record_cache_miss(self):
        self.cache_manager.record_miss()

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            **self.cache_manager.get_stats(),
            **self.auth_handler.get_auth_stats(),
        }

    def clear_cache(self):
        self.cache_manager.clear()
        logger.info("LeyscoAPIService cache cleared")

    def _debug_response(self, name: str, resp: requests.Response):
        try:
            logger.warning(f"\n========== LEYSCO API DEBUG: {name} ==========")
            logger.warning(f"URL: {resp.url}")
            logger.warning(f"STATUS: {resp.status_code}")
            logger.warning(f"RESPONSE: {resp.text[:1500]}")
            logger.warning("=============================================\n")
        except Exception as e:
            logger.error(f"Debug logging failed: {e}")

    # ------------------------------------------------------------------
    # Backward-compatible alias methods
    # ------------------------------------------------------------------

    def get_customers(self, search: str = "", limit: Optional[int] = None) -> list:
        return self.business_partners.get_customers(search, limit)

    def get_all_customers(self, search: str = "", limit: Optional[int] = None) -> list:
        return self.business_partners.get_all_customers(search, limit)

    def get_vendors(self, search: str = "", limit: Optional[int] = None) -> list:
        return self.business_partners.get_vendors(search, limit)

    def get_leads(self, search: str = "", limit: Optional[int] = None) -> list:
        return self.business_partners.get_leads(search, limit)

    def get_all_business_partners(self, search: str = "", limit: Optional[int] = None) -> list:
        return self.business_partners.get_all_business_partners(search, limit)

    def resolve_customer(self, name: str) -> Optional[Dict]:
        return self.business_partners.resolve_customer(name)

    def get_items(self, search: str = "", limit: Optional[int] = None) -> list:
        return self.inventory.get_items(search, limit)

    def get_item_by_name(self, name: str) -> Optional[Dict]:
        return self.inventory.get_item_by_name(name)

    def get_item_by_code(self, item_code: str) -> Optional[Dict]:
        return self.inventory.get_item_by_code(item_code)

    def get_inventory_report(self, search: str = "", limit: Optional[int] = None) -> list:
        return self.inventory.get_inventory_report(search, limit)

    def get_warehouses(self, search: str = "", limit: Optional[int] = None) -> list:
        return self.inventory.get_warehouses(search, limit)

    def get_item_price(self, item_code: str, customer_name: str = None, sap_list_num: int = None) -> Optional[Dict]:
        return self.pricing.get_item_price(item_code, customer_name, sap_list_num)

    def get_item_price_any_list(self, item_code: str) -> Optional[Dict]:
        return self.pricing.get_item_price_any_list(item_code)

    def get_open_sales_orders(self, customer_code: str = None, limit: int = 100) -> list:
        return self.orders.get_open_sales_orders(customer_code, limit)

    def get_customer_orders(self, customer_code: str = None, customer_name: str = None,
                            limit: int = 50, doc_status: str = "all",
                            from_date: str = None, to_date: str = None) -> list:
        return self.orders.get_customer_orders(
            customer_code, customer_name, limit, doc_status, from_date, to_date
        )

    def get_outstanding_deliveries(self, customer_code: str = None,
                                   customer_name: str = None, limit: int = 100) -> list:
        return self.deliveries.get_outstanding_deliveries(customer_code, customer_name, limit)

    def get_sales_analytics(self, period: str = "last_30_days", limit: int = 100,
                            customer_code: str = None, item_code: str = None) -> list:
        return self.analytics.get_sales_analytics(period, limit, customer_code, item_code)

    def get_top_selling_items(self, limit: int = 10, days: int = 30) -> list:
        return self.analytics.get_top_selling_items(limit, days)

    def get_slow_moving_items(self, limit: int = 10, days: int = 90,
                              turnover_threshold: float = 0.5) -> list:
        if hasattr(self.analytics, "get_slow_moving_items"):
            return self.analytics.get_slow_moving_items(limit, days, turnover_threshold)
        return []

    def validate_token(self):
        return self.auth_handler.validate_token()

    def login(self, username: str, password: str) -> bool:
        return self.auth_handler.login(username, password)


# ------------------------------------------------------------------
# Factory helpers
# ------------------------------------------------------------------

def create_api_service(user_token: str, base_url: str = None, company_code: str = None) -> LeyscoAPIService:
    """
    Create a LeyscoAPIService for the given user token.

    Preferred call sites should pass base_url pulled from the user session:

        session  = UserSessionManager.get(token)
        base_url = session.get("backend_url") if session else None
        service  = create_api_service(user_token=token, base_url=base_url)

    Or pass company_code for multi-tenant resolution:

        service = create_api_service(user_token=token, company_code="TEST001")

    If both base_url and company_code are omitted the service falls back to 
    the session cache automatically.

    Args:
        user_token: The authenticated user's Bearer token
        base_url: Direct base URL (overrides company_code)
        company_code: Company code for multi-tenant URL resolution

    Returns:
        Configured LeyscoAPIService instance
    """
    if not user_token:
        logger.warning("Creating API service without user token — data access will fail")
    return LeyscoAPIService(user_token=user_token, base_url=base_url, company_code=company_code)


def create_api_service_from_context(context: Dict[str, Any]) -> LeyscoAPIService:
    """
    Convenience factory that accepts a get_conversation_context() dict.
    This is the recommended call pattern inside route handlers:

        @router.get("/api/ai/chat")
        async def chat(ctx: Dict = Depends(get_conversation_context)):
            api = create_api_service_from_context(ctx)
            ...
    """
    token = context.get("_token")
    company_code = context.get("company_code") or context.get("company")
    
    # backend_url is stored in the session cache; _resolve_base_url picks it up
    # automatically, but passing it explicitly is faster (no cache lookup).
    session = _UserSessionManager_get(token)
    base_url = session.get("backend_url") if session else None
    
    return LeyscoAPIService(user_token=token, base_url=base_url, company_code=company_code)


def _UserSessionManager_get(token):
    """Safe import wrapper used by create_api_service_from_context."""
    try:
        from app.api.dependencies import UserSessionManager
        return UserSessionManager.get(token) or {}
    except Exception:
        return {}


# patch the reference above
UserSessionManager_get = _UserSessionManager_get