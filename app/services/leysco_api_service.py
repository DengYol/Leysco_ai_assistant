"""
app/services/leysco_api_service.py
===================================
Leysco API Service - Enhanced with Business Partner Type Filtering and Pagination
Optimized with connection pooling, Redis caching, and async support

MODIFIED FOR PHASE 1: Removed static token, uses per-request user token only
MODIFIED FOR PHASE 2: Added Sales Analytics, Customer Orders, and Outstanding Deliveries APIs
UPDATED: get_sales_analytics now properly fetches real data from sales orders endpoint
ADDED: Enhanced debugging for sales analytics to track API response
FIXED: None value handling in DocTotal and other numeric fields
ADDED: Sales orders-based top selling items calculation with proper item name resolution
ADDED: Sales orders-based slow moving items calculation
FIXED: Formatting error in sales analytics logging (invalid f-string format specifier)
FIXED: Unknown item names in top selling items - now resolves from item masterdata
"""

import requests
import logging
from typing import List, Dict, Optional, Any
from app.core.config import settings
from datetime import datetime, timedelta
import json
import hashlib
from functools import lru_cache, wraps
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# -------------------------------------------------
# BUSINESS PARTNER TYPES
# -------------------------------------------------
BP_TYPES = {
    "CUSTOMER": "C",
    "VENDOR": "V",
    "LEAD": "L",
    "ALL": None
}

# -------------------------------------------------
# SEARCH TERM CLEANER
# -------------------------------------------------
STRIP_FROM_SEARCH = {
    "suppliers", "supplier", "vendor", "vendors", "traders", "trader",
    "enterprises", "enterprise", "company", "co", "ltd", "limited",
    "inc", "group", "associates", "agency", "agencies",
    "industries", "industry", "international", "brothers", "bros",
    "holdings", "services", "distributors", "distributor",
}

# Cache TTLs
CUSTOMER_CACHE_TTL = 300  # 5 minutes
ITEM_CACHE_TTL = 300       # 5 minutes
INVENTORY_CACHE_TTL = 120  # 2 minutes
PRICE_CACHE_TTL = 300      # 5 minutes
DELIVERY_CACHE_TTL = 60    # 1 minute
ANALYTICS_CACHE_TTL = 3600  # 1 hour for analytics (less frequent changes)


def clean_customer_search_term(name: str) -> str:
    """
    Strip generic business suffix words before API search.
    e.g. 'magomano suppliers' → 'magomano'
    Falls back to original if stripping would leave nothing.
    """
    if not name:
        return name
    tokens = name.lower().split()
    cleaned = [t for t in tokens if t not in STRIP_FROM_SEARCH]
    result = " ".join(cleaned).strip()
    if result and result != name.lower():
        logger.info(f"Search term cleaned: '{name}' → '{result}'")
    return result or name


def cache_api_result(ttl_seconds: int = 300, key_prefix: str = ""):
    """Decorator to cache API results."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Skip caching if no user token (security)
            if not self.user_token:
                logger.debug("Skipping cache - no user token")
                return func(self, *args, **kwargs)
            
            cache = get_cache_service()
            
            # Generate cache key with tenant context
            func_name = func.__name__
            cache_str = f"{key_prefix or func_name}:{str(args)}:{str(sorted(kwargs.items()))}"
            cache_key = hashlib.md5(cache_str.encode()).hexdigest()
            
            # Check cache
            cached = cache.get_simple(cache_key)
            if cached is not None:
                logger.info(f"⚡ API cache hit: {func_name}")
                return cached
            
            # Execute function
            result = func(self, *args, **kwargs)
            
            # Cache result
            if result:
                cache.set_simple(cache_key, result, ttl=ttl_seconds)
            
            return result
        return wrapper
    return decorator


class LeyscoAPIService:
    """
    Service to interact with Leysco Sales System APIs
    MODIFIED: Uses per-request user token instead of static token.
    No token storage - token must be provided per instance.
    """

    # Document type mapping for easy reference (based on Sales App)
    DOC_TYPES = {
        13: "Invoices",
        14: "Credit Notes",
        15: "Deliveries",
        16: "Returns",
        17: "Sales Orders",
        20: "Returns / Credit Notes",
        22: "Purchase Orders",
        23: "Quotations",
        1470000113: "Custom Document Type",
        540000006:  "Custom Document Type",
    }

    # Enhanced status mapping for documents
    STATUS_MAP = {
        "open": "Pending",
        "Open": "Pending",
        "OPEN": "Pending",
        "bost_Open": "Pending",
        1: "Pending",
        "1": "Pending",
        "closed": "Completed",
        "Closed": "Completed",
        "CLOSED": "Completed",
        "completed": "Completed",
        "Completed": "Completed",
        "COMPLETED": "Completed",
        "delivered": "Completed",
        "Delivered": "Completed",
        "DELIVERED": "Completed",
        "bost_Close": "Completed",
        2: "Completed",
        "2": "Completed",
        "cancelled": "Cancelled",
        "Cancelled": "Cancelled",
        "CANCELLED": "Cancelled",
        3: "Cancelled",
        "3": "Cancelled",
        "in_transit": "In Transit",
        "In Transit": "In Transit",
        "partial": "Partially Delivered",
        "Partially Delivered": "Partially Delivered",
    }

    DOC_STATUS_MAP = {
        "open": 1,
        "pending": 1,
        "closed": 2,
        "completed": 2,
        "all": None
    }

    ENDPOINT_PATTERNS = {
        "quotations": [
            "/documents/quotation",
            "/documents/quotations",
            "/quotations",
            "/sales/quotations",
            "/marketing/quotation",
            "/quotation/create",
            "/marketing/docs/23",
        ],
        "orders": [
            "/orders",
            "/sales/orders",
            "/marketing/orders",
            "/marketing/docs/17",
        ],
        "invoices": [
            "/invoices",
            "/sales/invoices",
            "/marketing/invoices",
            "/marketing/docs/13",
        ],
        "deliveries": [
            "/deliveries",
            "/sales/deliveries",
            "/marketing/docs/15",
        ],
        "documents": [
            "/documents/quotation",
            "/documents/quotations",
            "/documents/order",
            "/documents/invoice",
            "/documents/delivery",
        ],
    }

    KNOWN_POST_ENDPOINTS = {
        "quotations": [
            "/documents/quotation",
            "/documents/quotations",
            "/quotations",
        ],
        "orders": [
            "/documents/order",
            "/orders",
        ],
    }

    def __init__(self, user_token: str = None):
        """
        Initialize API service with user token from request.
        
        Args:
            user_token: Bearer token from the authenticated user (required for data access)
        """
        self.base_url = settings.LEYSCO_API_BASE_URL.rstrip("/")
        self.user_token = user_token
        
        # Initialize headers WITHOUT static token
        self.headers = {
            "Content-Type": "application/json"
        }
        
        # Add user token if provided
        if self.user_token:
            self.headers["Authorization"] = f"Bearer {self.user_token}"
            logger.debug("API Service initialized with user token")
        else:
            logger.warning("API Service initialized WITHOUT user token - data access will fail")
        
        # Configure session with connection pooling
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Connection pooling for better performance
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=Retry(
                total=2,  # Reduced from 3 - don't retry auth failures
                backoff_factor=0.3,
                status_forcelist=[429, 500, 502, 503, 504]  # 401 removed - don't retry
            )
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        self.timeout = 30
        self._is_authenticated = bool(self.user_token)
        
        self._endpoint_cache = {}
        self._last_discovery = None
        
        # Caches for different business partner types
        self._customer_cache = {}
        self._customer_cache_time = {}
        self._vendor_cache = {}
        self._vendor_cache_time = {}
        self._lead_cache = {}
        self._lead_cache_time = {}
        
        # Stats tracking
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "errors": 0,
            "auth_errors": 0
        }
        
        # Initialize pricing service lazily to avoid circular imports
        self._pricing_service = None

    @property
    def pricing_service(self):
        """Lazy load pricing service."""
        if self._pricing_service is None:
            from app.services.pricing_service import get_pricing_service
            self._pricing_service = get_pricing_service()
        return self._pricing_service

    # -------------------------------------------------
    # TOKEN MANAGEMENT (NEW FOR PHASE 1)
    # -------------------------------------------------
    
    def set_user_token(self, token: str):
        """Update user token for this instance (used when re-authenticating)"""
        self.user_token = token
        self.headers["Authorization"] = f"Bearer {token}"
        self.session.headers.update(self.headers)
        self._is_authenticated = True
        logger.debug("User token updated")
    
    def _mask_token(self, token: str = None) -> str:
        """Mask token for logging security"""
        t = token or self.user_token
        if not t:
            return "***NO_TOKEN***"
        if len(t) <= 12:
            return "***MASKED***"
        return f"{t[:8]}...{t[-4:]}"
    
    # -------------------------------------------------
    # TOKEN VALIDATION (NEW FOR PHASE 1)
    # -------------------------------------------------
    
    async def validate_token(self) -> Optional[Dict]:
        """
        Validate the current user token with Leysco API.
        Returns user and tenant information if valid.
        """
        if not self.user_token:
            logger.error("Cannot validate token - no token provided")
            return {"valid": False, "error": "No token provided"}
        
        try:
            url = f"{self.base_url}/auth/validate"
            self._record_api_call()
            resp = self.session.get(url, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("valid") or data.get("ResultState"):
                    logger.info(f"✅ Token validated successfully for user")
                    return {
                        "valid": True,
                        "user_id": data.get("user_id") or data.get("id"),
                        "email": data.get("email"),
                        "role": data.get("role") or data.get("user_role", "user"),
                        "company_code": data.get("company_code") or data.get("tenant_code"),
                        "company_id": data.get("company_id") or data.get("tenant_id", 0)
                    }
            
            logger.warning(f"Token validation failed: HTTP {resp.status_code}")
            return {"valid": False, "error": f"HTTP {resp.status_code}"}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Token validation request error: {e}")
            return {"valid": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return {"valid": False, "error": str(e)}

    # -------------------------------------------------
    # AUTHENTICATION HELPERS (MODIFIED)
    # -------------------------------------------------
    
    def _check_auth(self, response: requests.Response) -> bool:
        """Check if response indicates authentication failure."""
        if response.status_code == 401:
            self._stats["auth_errors"] += 1
            logger.warning(f"Authentication failed (401) - token may be invalid or expired")
            self._is_authenticated = False
            return False
        
        if response.status_code == 302:
            self._stats["auth_errors"] += 1
            logger.warning(f"Authentication redirect (302) - possible session expiry")
            self._is_authenticated = False
            return False
        
        return True
    
    # -------------------------------------------------
    # HTML RESPONSE DETECTION (FIXED - ADDED METHOD)
    # -------------------------------------------------
    def _is_html_response(self, text: str) -> bool:
        """Check if response is HTML (login page) instead of JSON."""
        if not text:
            return False
        text_lower = text.lower().strip()
        html_indicators = [
            '<html', '<!doctype html', '<!DOCTYPE HTML',
            'welcome back', 'sign in', 'login', 'signin',
            'username', 'password', 'enter your credentials'
        ]
        return any(indicator in text_lower for indicator in html_indicators)
    
    def _ensure_auth(self) -> bool:
        """Ensure we have valid authentication (token present)."""
        if not self.user_token:
            logger.warning("No user token available for API call")
            return False
        return True

    # -------------------------------------------------
    # STATS HELPERS
    # -------------------------------------------------
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return self._stats.copy()
    
    def _record_cache_hit(self):
        self._stats["cache_hits"] += 1
    
    def _record_cache_miss(self):
        self._stats["cache_misses"] += 1
    
    def _record_api_call(self):
        self._stats["api_calls"] += 1
    
    def _record_error(self):
        self._stats["errors"] += 1

    # -------------------------------------------------
    # BUSINESS PARTNER TYPE DETECTION (IMPROVED)
    # -------------------------------------------------
    def _get_business_partner_type(self, business_partner: Dict) -> str:
        """
        Determine business partner type from the data.
        Checks multiple possible fields and values.
        """
        card_type = business_partner.get("CardType") or business_partner.get("card_type") or business_partner.get("Type") or business_partner.get("type")
        card_name = business_partner.get("CardName", "").lower()
        
        if any(word in card_name for word in ["vendor", "supplier"]):
            return "V"
        if any(word in card_name for word in ["lead", "prospect"]):
            return "L"
        
        if card_type:
            card_type_str = str(card_type).upper()
            if card_type_str in ["C", "CUSTOMER"]:
                return "C"
            elif card_type_str in ["V", "VENDOR", "SUPPLIER"]:
                return "V"
            elif card_type_str in ["L", "LEAD"]:
                return "L"
        
        group_code = business_partner.get("GroupCode") or business_partner.get("group_code")
        if group_code:
            try:
                gc = int(group_code)
                if 1 <= gc <= 100:
                    return "C"
                elif 101 <= gc <= 200:
                    return "V"
                elif 201 <= gc <= 300:
                    return "L"
            except:
                pass
        
        return "C"
    
    def _is_customer(self, business_partner: Dict) -> bool:
        return self._get_business_partner_type(business_partner) == "C"
    
    def _is_vendor(self, business_partner: Dict) -> bool:
        return self._get_business_partner_type(business_partner) == "V"
    
    def _is_lead(self, business_partner: Dict) -> bool:
        return self._get_business_partner_type(business_partner) == "L"
    
    def _filter_by_bp_type(self, business_partners: List[Dict], bp_type: str) -> List[Dict]:
        if not business_partners or bp_type is None:
            return business_partners
        
        filtered = []
        for bp in business_partners:
            if bp_type == "C" and self._is_customer(bp):
                filtered.append(bp)
            elif bp_type == "V" and self._is_vendor(bp):
                filtered.append(bp)
            elif bp_type == "L" and self._is_lead(bp):
                filtered.append(bp)
        
        logger.info(f"Filtered {len(filtered)}/{len(business_partners)} business partners for type {bp_type}")
        return filtered

    # -------------------------------------------------
    # DEBUG LOGGER
    # -------------------------------------------------
    def _debug_response(self, name: str, resp: requests.Response):
        try:
            logger.warning(f"\n========== LEYSCO API DEBUG: {name} ==========")
            logger.warning(f"URL: {resp.url}")
            logger.warning(f"STATUS: {resp.status_code}")
            logger.warning(f"RESPONSE: {resp.text[:1500]}")
            logger.warning("=============================================\n")
        except Exception as e:
            logger.error(f"Debug logging failed: {e}")

    # -------------------------------------------------
    # ENHANCED STATUS HELPER
    # -------------------------------------------------
    def _normalize_status(self, status: Any) -> str:
        if status is None:
            return "Unknown"
        
        if status in self.STATUS_MAP:
            return self.STATUS_MAP[status]
        
        if isinstance(status, (int, float)):
            status_str = str(int(status))
            if status_str in self.STATUS_MAP:
                return self.STATUS_MAP[status_str]
        
        if isinstance(status, str):
            status_lower = status.lower().strip()
            for key, value in self.STATUS_MAP.items():
                if isinstance(key, str) and key.lower() == status_lower:
                    return value
        
        if isinstance(status, str):
            status_lower = status.lower()
            if "close" in status_lower or "complete" in status_lower or "deliver" in status_lower:
                return "Completed"
            if "open" in status_lower or "pend" in status_lower:
                return "Pending"
            if "cancel" in status_lower:
                return "Cancelled"
            if "transit" in status_lower or "partial" in status_lower:
                return "In Transit"
        
        return str(status)

    # -------------------------------------------------
    # RESPONSE NORMALIZER
    # -------------------------------------------------
    def _normalize(self, data):
        if not isinstance(data, dict):
            return data if isinstance(data, list) else []

        response_data = data.get("ResponseData") or data.get("responseData")

        if isinstance(response_data, dict) and "stocks" in response_data:
            stocks = response_data["stocks"]
            if isinstance(stocks, dict) and "data" in stocks:
                return stocks["data"]
        
        if isinstance(response_data, dict):
            records = response_data.get("data")
            if isinstance(records, list):
                return records

        if isinstance(response_data, list):
            return response_data

        if isinstance(data.get("data"), list):
            return data["data"]
        
        if isinstance(data.get("items"), list):
            return data["items"]
        
        if isinstance(data.get("ResponseData"), list):
            return data["ResponseData"]

        return []

    def _normalize_warehouse_response(self, data: dict) -> List[Dict]:
        """Normalize warehouse response from the /warehouse endpoint."""
        try:
            # Check if response is in the standard Leysco format
            if data.get("ResultState") and data.get("ResponseData"):
                response_data = data["ResponseData"]
                if isinstance(response_data, dict):
                    # Check for data array
                    if "data" in response_data:
                        return response_data["data"]
                    # Check for warehouses array
                    elif "warehouses" in response_data:
                        return response_data["warehouses"]
                elif isinstance(response_data, list):
                    return response_data
            
            # Check for direct data array
            if isinstance(data.get("data"), list):
                return data["data"]
            
            # Check if the response itself is a list
            if isinstance(data, list):
                return data
            
            # If we got here, return empty list
            logger.warning(f"Unknown warehouse response format: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            return []
            
        except Exception as e:
            logger.error(f"Error normalizing warehouse response: {e}")
            return []

    def _apply_limit(self, records: List[Dict], limit: Optional[int]) -> List[Dict]:
        return records[:limit] if limit and isinstance(limit, int) and limit > 0 else records

    def _match_by_name(self, records: List[Dict], search: str, keys: List[str]) -> Optional[Dict]:
        search = search.lower()
        for r in records:
            for k in keys:
                if search in str(r.get(k, "")).lower():
                    return r
        return None

    # -------------------------------------------------
    # AUTHENTICATION (MODIFIED - No static token)
    # -------------------------------------------------
    def login(self, username: str, password: str) -> bool:
        """
        Authenticate with the API and store token.
        NOTE: This is for system-level authentication only.
        For user authentication, the token should come from the request.
        """
        try:
            url = f"{self.base_url}/auth/login"
            payload = {"username": username, "password": password}
            self._record_api_call()
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            self._debug_response("LOGIN", resp)

            if resp.status_code == 200:
                data = resp.json()
                token = data.get("token") or data.get("access_token")
                if token:
                    self.user_token = token
                    self.headers["Authorization"] = f"Bearer {token}"
                    self.session.headers.update(self.headers)
                    self._is_authenticated = True
                    logger.info("✅ Successfully authenticated with CRM")
                    return True
            logger.error(f"❌ Login failed: {resp.status_code}")
            self._is_authenticated = False
            return False
        except Exception as e:
            self._record_error()
            logger.error(f"❌ Login error: {e}")
            self._is_authenticated = False
            return False

    # -------------------------------------------------
    # ENHANCED CUSTOMER/VENDOR/LEAD METHODS WITH PAGINATION
    # -------------------------------------------------
    
    @cache_api_result(ttl_seconds=CUSTOMER_CACHE_TTL)
    def get_customers(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get customers only (excludes vendors and leads) with caching."""
        try:
            if not self._ensure_auth():
                return []
                
            if search and search.lower() in ["all", "all customers", "customers", "customer", "show", "list", "display"]:
                search = ""
            
            cleaned_search = clean_customer_search_term(search) if search else ""
            
            all_customers = []
            page = 1
            per_page = 200
            
            while True:
                url = f"{self.base_url}/bp_masterdata"
                params = {"page": page, "per_page": per_page}
                if cleaned_search:
                    params["search"] = cleaned_search
                
                logger.info(f"📄 Fetching customers page {page}")
                self._record_api_call()
                resp = self.session.get(url, params=params, timeout=30)
                
                if not self._check_auth(resp):
                    # Don't retry on auth failure - just return empty
                    logger.warning("Authentication failed, stopping customer fetch")
                    break
                
                if resp.status_code != 200:
                    logger.error(f"Failed to fetch customers page {page}: {resp.status_code}")
                    break
                
                try:
                    data = resp.json()
                except Exception as e:
                    logger.error(f"Failed to parse customers JSON: {e}")
                    break
                
                if data.get("ResultState") and data.get("ResponseData"):
                    response_data = data["ResponseData"]
                    if isinstance(response_data, dict):
                        partners = response_data.get("data", [])
                        pagination = {
                            "current_page": response_data.get("current_page", 1),
                            "last_page": response_data.get("last_page", 1),
                            "total": response_data.get("total", 0)
                        }
                    else:
                        partners = response_data if isinstance(response_data, list) else []
                        pagination = {"current_page": page, "last_page": 1, "total": len(partners)}
                else:
                    partners = self._normalize(data)
                    pagination = {"current_page": page, "last_page": 1, "total": len(partners)}
                
                if not partners:
                    logger.info(f"No more customers on page {page}")
                    break
                
                page_customers = [p for p in partners if self._is_customer(p)]
                all_customers.extend(page_customers)
                logger.info(f"Page {page}: Found {len(page_customers)} customers (total: {len(all_customers)})")
                
                if page >= pagination.get("last_page", 1):
                    break
                page += 1
                
                if limit and len(all_customers) >= limit:
                    all_customers = all_customers[:limit]
                    break
            
            all_customers.sort(key=lambda x: x.get("CardName", ""))
            logger.info(f"✅ Retrieved {len(all_customers)} total customers")
            return all_customers
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch customers: {e}", exc_info=True)
            return []
    
    def get_all_customers(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """
        Get all customers (alias for get_customers).
        Used by entity extractor for customer name resolution.
        """
        return self.get_customers(search=search, limit=limit)
    
    def get_vendors(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get vendors only."""
        try:
            if not self._ensure_auth():
                return []
            
            all_vendors = []
            page = 1
            per_page = 200
            
            while True:
                url = f"{self.base_url}/bp_masterdata"
                params = {"page": page, "per_page": per_page}
                if search:
                    params["search"] = search
                
                self._record_api_call()
                resp = self.session.get(url, params=params, timeout=30)
                
                if not self._check_auth(resp):
                    break
                
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                partners = self._normalize(data)
                
                if not partners:
                    break
                
                page_vendors = [p for p in partners if self._is_vendor(p)]
                all_vendors.extend(page_vendors)
                
                if len(partners) < per_page:
                    break
                page += 1
                
                if limit and len(all_vendors) >= limit:
                    all_vendors = all_vendors[:limit]
                    break
            
            return all_vendors
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch vendors: {e}")
            return []
    
    def get_leads(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get leads only."""
        try:
            if not self._ensure_auth():
                return []
            
            all_leads = []
            page = 1
            per_page = 200
            
            while True:
                url = f"{self.base_url}/bp_masterdata"
                params = {"page": page, "per_page": per_page}
                if search:
                    params["search"] = search
                
                self._record_api_call()
                resp = self.session.get(url, params=params, timeout=30)
                
                if not self._check_auth(resp):
                    break
                
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                partners = self._normalize(data)
                
                if not partners:
                    break
                
                page_leads = [p for p in partners if self._is_lead(p)]
                all_leads.extend(page_leads)
                
                if len(partners) < per_page:
                    break
                page += 1
                
                if limit and len(all_leads) >= limit:
                    all_leads = all_leads[:limit]
                    break
            
            return all_leads
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch leads: {e}")
            return []

    def get_all_business_partners(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get all business partners (customers, vendors, leads)."""
        try:
            if not self._ensure_auth():
                return []
            
            all_partners = []
            page = 1
            per_page = 200
            
            while True:
                url = f"{self.base_url}/bp_masterdata"
                params = {"page": page, "per_page": per_page}
                if search:
                    params["search"] = search
                
                self._record_api_call()
                resp = self.session.get(url, params=params, timeout=30)
                
                if not self._check_auth(resp):
                    break
                
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                partners = self._normalize(data)
                
                if not partners:
                    break
                
                all_partners.extend(partners)
                
                if len(partners) < per_page:
                    break
                page += 1
                
                if limit and len(all_partners) >= limit:
                    all_partners = all_partners[:limit]
                    break
            
            return all_partners
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch business partners: {e}")
            return []

    def resolve_customer(self, name: str) -> Optional[Dict]:
        """
        Resolve customer by name - returns the best matching customer.
        Tries exact match first, then fuzzy match.
        """
        if not name:
            return None
        
        # Try exact match first
        customers = self.get_customers(search=name, limit=10)
        if customers:
            name_lower = name.lower()
            for customer in customers:
                customer_name = customer.get("CardName", "").lower()
                if customer_name == name_lower:
                    logger.info(f"✅ Exact match found for customer: {customer.get('CardName')}")
                    return customer
            
            # Return first match if no exact match
            logger.info(f"✅ Returning first match for customer: {customers[0].get('CardName')}")
            return customers[0]
        
        # Try with cleaned search term
        cleaned = clean_customer_search_term(name)
        if cleaned != name:
            customers = self.get_customers(search=cleaned, limit=5)
            if customers:
                logger.info(f"✅ Found customer using cleaned term '{cleaned}': {customers[0].get('CardName')}")
                return customers[0]
        
        logger.warning(f"❌ No customer found for: {name}")
        return None

    # -------------------------------------------------
    # ITEMS
    # -------------------------------------------------
    @cache_api_result(ttl_seconds=ITEM_CACHE_TTL)
    def get_items(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        try:
            if not self._ensure_auth():
                return []
                
            url = f"{self.base_url}/item_masterdata"
            params = {"page": 1, "per_page": 50, "search": search}
            self._record_api_call()
            resp = self.session.get(url, params=params, timeout=15)
            
            if not self._check_auth(resp):
                return []
            
            self._debug_response("ITEMS", resp)
            if resp.status_code == 200:
                return self._apply_limit(self._normalize(resp.json()), limit)
            return []
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch items: {e}")
            return []

    def get_item_by_name(self, name: str) -> Optional[Dict]:
        """Get a single item by name."""
        items = self.get_items(search=name, limit=1)
        return items[0] if items else None

    # =========================================================
    # GET ITEM BY CODE - FIXED for quotation validation
    # =========================================================
    def get_item_by_code(self, item_code: str) -> Optional[Dict]:
        """
        Get a single item by its code.
        Used by quotation service to validate items.
        """
        try:
            if not self._ensure_auth():
                return None
            
            # Search for the item by code
            items = self.get_items(search=item_code, limit=5)
            
            if items:
                # Find exact match by code
                for item in items:
                    if item.get("ItemCode") == item_code:
                        logger.info(f"✅ Found item by code: {item_code} - {item.get('ItemName')}")
                        return item
            
            logger.warning(f"❌ Item not found by code: {item_code}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting item by code {item_code}: {e}")
            return None

    # -------------------------------------------------
    # ITEM PRICE LOOKUP - INTEGRATED WITH PRICING SERVICE
    # -------------------------------------------------
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
            Dictionary with price information following the format expected by db_query_service
        """
        try:
            # If customer name is provided, try to resolve customer and get their price list
            customer = None
            if customer_name and not sap_list_num:
                customer = self.resolve_customer(customer_name)
                if customer:
                    logger.info(f"✅ Resolved customer: {customer.get('CardName')} (Code: {customer.get('CardCode')})")
            
            # Use pricing service to get price
            if customer and not sap_list_num:
                # Customer-specific pricing
                price_result = self.pricing_service.get_price_for_customer(
                    item_code=item_code,
                    customer=customer
                )
            else:
                # Default pricing with optional specific price list
                list_num = sap_list_num or 1  # Default to price list 1
                price_result = self.pricing_service.get_price(
                    item_code=item_code,
                    sap_list_num=list_num
                )
            
            # Transform pricing service result to the format expected by db_query_service
            if price_result and price_result.get("found") and price_result.get("price", 0) > 0:
                return {
                    "found": True,
                    "item_code": item_code,
                    "price": price_result.get("price"),
                    "currency": price_result.get("currency", "KES"),
                    "price_list_name": price_result.get("price_list_name", ""),
                    "is_gross_price": price_result.get("is_gross_price", False),
                    "uom_entry": price_result.get("uom_entry"),
                    "note": price_result.get("note", ""),
                    "sap_list_num": price_result.get("sap_list_num"),
                    "chain_walked": price_result.get("chain_walked", [])
                }
            else:
                # Item exists but has no price configured
                return {
                    "found": False,
                    "item_code": item_code,
                    "price": 0,
                    "message": price_result.get("note", "No price configured for this item"),
                    "price_list_name": price_result.get("price_list_name", ""),
                    "chain_walked": price_result.get("chain_walked", [])
                }
                
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to get item price for {item_code}: {e}")
            # Return fallback structure
            return {
                "found": False,
                "item_code": item_code,
                "price": 0,
                "error": str(e),
                "message": "Could not retrieve price at this time"
            }

    def get_item_price_any_list(self, item_code: str) -> Optional[Dict]:
        """
        Try all price lists to find a price for an item.
        Useful when you don't know which price list the item belongs to.
        """
        try:
            price_result = self.pricing_service.get_price_any_list(item_code=item_code)
            
            if price_result and price_result.get("found") and price_result.get("price", 0) > 0:
                return {
                    "found": True,
                    "item_code": item_code,
                    "price": price_result.get("price"),
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
            self._record_error()
            logger.error(f"Failed to get price from any list for {item_code}: {e}")
            return {
                "found": False,
                "item_code": item_code,
                "price": 0,
                "error": str(e),
                "message": "Could not retrieve price at this time"
            }

    # -------------------------------------------------
    # INVENTORY REPORT - IMPROVED
    # -------------------------------------------------
    @cache_api_result(ttl_seconds=INVENTORY_CACHE_TTL)
    def get_inventory_report(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get inventory report with proper authentication handling."""
        try:
            if not self._ensure_auth():
                logger.warning("Not authenticated, cannot fetch inventory report")
                return []
            
            all_items = []
            page = 1
            per_page = min(limit, 500) if limit else 100
            
            while True:
                params = {"page": page, "per_page": per_page}
                if search:
                    params["search"] = search
                    
                url = f"{self.base_url}/inventory/report"
                self._record_api_call()
                resp = self.session.get(url, params=params, timeout=15)
                
                if not self._check_auth(resp):
                    logger.warning("Authentication failed during inventory fetch")
                    break
                
                self._debug_response("INVENTORY REPORT", resp)
                
                if resp.status_code != 200:
                    logger.error(f"Inventory report API error: {resp.status_code}")
                    break
                
                try:
                    data = resp.json()
                except Exception as e:
                    logger.error(f"Failed to parse inventory report JSON: {e}")
                    break
                
                # Parse the response
                items = self._parse_inventory_response_data(data)
                
                if not items:
                    break
                
                for item in items:
                    processed_item = {
                        "ItemCode": item.get("ItemCode") or item.get("item_code", ""),
                        "ItemName": item.get("ItemName") or item.get("item_name", ""),
                        "WhsCode": item.get("WhsCode") or item.get("whs_code", ""),
                        "CurrentOnHand": float(item.get("CurrentOnHand") or item.get("OnHand") or 0),
                        "CurrentIsCommited": float(item.get("CurrentIsCommited") or item.get("IsCommited") or 0),
                        "LastTransactionDate": item.get("LastTransactionDate", ""),
                        "PeriodOutQty": float(item.get("PeriodOutQty", 0)),
                        "Available": float(item.get("CurrentOnHand") or item.get("OnHand") or 0) - 
                                     float(item.get("CurrentIsCommited") or item.get("IsCommited") or 0)
                    }
                    all_items.append(processed_item)
                
                if len(items) < per_page:
                    break
                page += 1
                
                if limit and len(all_items) >= limit:
                    all_items = all_items[:limit]
                    break
            
            logger.info(f"✅ Retrieved {len(all_items)} inventory items")
            return all_items
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch inventory report: {e}", exc_info=True)
            return []

    def _parse_inventory_response_data(self, data: dict) -> List[Dict]:
        """Parse inventory response from various possible formats."""
        try:
            if data.get("ResultState") and data.get("ResponseData"):
                response_data = data["ResponseData"]
                
                if isinstance(response_data, dict) and "stocks" in response_data:
                    stocks = response_data["stocks"]
                    if isinstance(stocks, dict) and "data" in stocks:
                        return stocks["data"]
                elif isinstance(response_data, dict) and "data" in response_data:
                    return response_data["data"]
                elif isinstance(response_data, list):
                    return response_data
            else:
                # Try direct data array
                if isinstance(data.get("data"), list):
                    return data["data"]
            
            return []
        except Exception as e:
            logger.error(f"Error parsing inventory response: {e}")
            return []

    # -------------------------------------------------
    # WAREHOUSES - FIXED ENDPOINT
    # -------------------------------------------------
    def get_warehouses(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        """Get warehouses from the correct API endpoint: /warehouse (singular, not /warehouses)."""
        try:
            if not self._ensure_auth():
                logger.warning("Not authenticated, cannot fetch warehouses")
                return []
            
            # Use the correct endpoint - /warehouse (not /warehouses)
            url = f"{self.base_url}/warehouse"
            params = {"page": 1, "per_page": 100}
            if search:
                params["search"] = search
            
            logger.info(f"🏭 Fetching warehouses from: {url}")
            self._record_api_call()
            resp = self.session.get(url, params=params, timeout=15)
            
            if not self._check_auth(resp):
                logger.warning("Authentication failed during warehouse fetch")
                return []
            
            self._debug_response("WAREHOUSES", resp)
            
            if resp.status_code == 200:
                data = resp.json()
                warehouses = self._normalize_warehouse_response(data)
                return self._apply_limit(warehouses, limit)
            else:
                logger.error(f"Warehouse API error: {resp.status_code}")
                return []
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch warehouses: {e}")
            return []

    # =========================================================
    # FIXED: GET OPEN SALES ORDERS (for outstanding deliveries)
    # =========================================================
    @cache_api_result(ttl_seconds=DELIVERY_CACHE_TTL)
    def get_open_sales_orders(self, customer_code: str = None, limit: int = 100) -> List[Dict]:
        """
        Fetch open sales orders with outstanding quantities from SAP Business One.
        Uses the confirmed working endpoint: /marketing/docs/17 with isDoc=1 and DocStatus=1.
        
        Args:
            customer_code: Optional customer code to filter by
            limit: Maximum number of orders to return
        
        Returns:
            List of open orders with outstanding delivery quantities
        """
        try:
            if not self._ensure_auth():
                logger.warning("Not authenticated, cannot fetch open sales orders")
                return []

            url = f"{self.base_url}/marketing/docs/17"
            params = {
                "isDoc": 1,
                "page": 1,
                "per_page": limit,
                "DocStatus": 1,   # 1 = Open / outstanding
                "IsICT": "N",
                "created_by": "",
            }
            if customer_code:
                params["CardCode"] = customer_code

            logger.info(f"📦 Fetching open sales orders from: {url} | params: {params}")
            self._record_api_call()
            resp = self.session.get(url, params=params, timeout=30)

            if not self._check_auth(resp):
                logger.warning("Authentication failed fetching open sales orders")
                return []

            if resp.status_code != 200:
                logger.error(f"Open sales orders API error: {resp.status_code}")
                return []

            if self._is_html_response(resp.text):
                logger.warning("Received HTML response for open sales orders - token may be expired")
                return []

            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse open sales orders JSON: {e}")
                return []

            # Parse orders from standard Leysco response envelope
            orders = []
            if data.get("ResultState") and data.get("ResponseData"):
                response_data = data["ResponseData"]
                if isinstance(response_data, dict):
                    if "data" in response_data:
                        orders = response_data["data"]
                    elif "DocumentLines" in response_data:
                        # Single document returned directly
                        orders = [response_data]
                elif isinstance(response_data, list):
                    orders = response_data
            else:
                orders = self._normalize(data)

            if not orders:
                logger.info("No open sales orders found")
                return []

            # Flatten into line-item records (one row per outstanding item line)
            formatted_orders = []
            for order in orders:
                doc_num     = order.get("DocNum") or order.get("doc_num") or order.get("DocumentNumber")
                doc_entry   = order.get("DocEntry") or order.get("doc_entry") or order.get("DocumentEntry")
                card_code   = order.get("CardCode") or order.get("card_code") or customer_code
                card_name   = order.get("CardName") or order.get("card_name") or "Unknown"
                doc_date    = order.get("DocDate") or order.get("doc_date") or ""
                doc_due_date = order.get("DocDueDate") or order.get("doc_due_date") or ""

                items = (
                    order.get("DocumentLines")
                    or order.get("items")
                    or order.get("Lines")
                    or order.get("document_lines")
                    or []
                )

                # Handle single-item order structures
                if not items and order.get("ItemCode"):
                    items = [order]

                for item in items:
                    item_code  = item.get("ItemCode") or item.get("item_code") or item.get("ProductCode")
                    item_name  = item.get("ItemName") or item.get("item_name") or item.get("ProductName")
                    quantity   = float(item.get("Quantity") or item.get("quantity") or 0)
                    open_qty   = float(item.get("OpenQty") or item.get("open_qty") or item.get("OpenQuantity") or quantity)
                    price      = float(item.get("Price") or item.get("price") or 0)

                    if open_qty > 0:
                        formatted_orders.append({
                            "DocNum":      doc_num,
                            "DocEntry":    doc_entry,
                            "CardCode":    card_code,
                            "CardName":    card_name,
                            "DocDate":     doc_date,
                            "DocDueDate":  doc_due_date,
                            "ItemCode":    item_code,
                            "ItemName":    item_name,
                            "Quantity":    quantity,
                            "OpenQty":     open_qty,
                            "Price":       price,
                            "Status":      "Open",
                        })

                if len(formatted_orders) >= limit:
                    break

            logger.info(f"✅ Processed {len(formatted_orders)} open line items from sales orders")
            return formatted_orders

        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch open sales orders: {e}", exc_info=True)
            return []

    # =========================================================
    # PHASE 2: SALES ANALYTICS API - FIXED None value handling & formatting
    # =========================================================
    
    @cache_api_result(ttl_seconds=ANALYTICS_CACHE_TTL)
    def get_sales_analytics(
        self,
        period: str = "last_30_days",
        limit: int = 100,
        customer_code: str = None,
        item_code: str = None
    ) -> List[Dict]:
        """
        Get real sales analytics data from Leysco API using sales orders endpoint.
        
        Args:
            period: Time period (last_7_days, last_30_days, last_90_days, last_365_days)
            limit: Maximum number of records to return
            customer_code: Optional customer filter
            item_code: Optional item filter
        
        Returns:
            List of sales analytics data with summary and top products
        """
        logger.info("=" * 80)
        logger.info("🔍 SALES ANALYTICS DEBUG - START")
        logger.info(f"   Period: {period}")
        logger.info(f"   Limit: {limit}")
        logger.info(f"   Customer Code: {customer_code}")
        logger.info(f"   Item Code: {item_code}")
        logger.info("=" * 80)
        
        try:
            if not self._ensure_auth():
                logger.warning("Not authenticated, cannot fetch sales analytics")
                return []
            
            # Calculate date range based on period
            end_date = datetime.now()
            if period == "last_7_days":
                start_date = end_date - timedelta(days=7)
                period_days = 7
            elif period == "last_30_days":
                start_date = end_date - timedelta(days=30)
                period_days = 30
            elif period == "last_90_days":
                start_date = end_date - timedelta(days=90)
                period_days = 90
            elif period == "last_365_days":
                start_date = end_date - timedelta(days=365)
                period_days = 365
            else:
                start_date = end_date - timedelta(days=30)
                period_days = 30
            
            logger.info(f"📅 Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
            
            # Use SALES ORDERS endpoint which has data
            url = f"{self.base_url}/marketing/docs/17"
            params = {
                "page": 1,
                "per_page": limit,
                "FromDate": start_date.strftime("%Y-%m-%d"),
                "ToDate": end_date.strftime("%Y-%m-%d")
            }
            
            if customer_code:
                params["CardCode"] = customer_code
            
            logger.info(f"📊 Fetching sales analytics from: {url}")
            logger.info(f"📊 Params: {params}")
            self._record_api_call()
            
            resp = self.session.get(url, params=params, timeout=30)
            
            logger.info(f"📊 Response Status Code: {resp.status_code}")
            logger.info(f"📊 Response Headers: Content-Type: {resp.headers.get('Content-Type', 'Unknown')}")
            
            if not self._check_auth(resp):
                logger.warning("Authentication failed fetching sales analytics")
                return []
            
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch sales analytics: HTTP {resp.status_code}")
                logger.warning(f"Response body preview: {resp.text[:500]}")
                return []
            
            if self._is_html_response(resp.text):
                logger.warning("Received HTML response - authentication may have expired")
                logger.warning(f"HTML preview: {resp.text[:300]}")
                return []
            
            try:
                data = resp.json()
                logger.info(f"📊 Response JSON type: {type(data)}")
                if isinstance(data, dict):
                    logger.info(f"📊 Response keys: {list(data.keys())}")
                else:
                    logger.info(f"📊 Response is not a dict: {type(data)}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse sales analytics JSON: {e}")
                logger.error(f"Raw response (first 500 chars): {resp.text[:500]}")
                return []
            
            # Parse orders from response
            orders = []
            if data.get("ResultState") and data.get("ResponseData"):
                response_data = data["ResponseData"]
                logger.info(f"📊 ResponseData type: {type(response_data)}")
                if isinstance(response_data, dict):
                    if "data" in response_data:
                        orders = response_data["data"]
                        logger.info(f"📊 Orders from 'data' key: {len(orders)}")
                    elif "DocumentLines" in response_data:
                        orders = [response_data]
                        logger.info("📊 Single document found (DocumentLines)")
                    else:
                        logger.info(f"📊 ResponseData dict keys: {list(response_data.keys())}")
                elif isinstance(response_data, list):
                    orders = response_data
                    logger.info(f"📊 Orders from list: {len(orders)}")
                else:
                    logger.info(f"📊 ResponseData is {type(response_data)} - unexpected")
            else:
                orders = self._normalize(data)
                logger.info(f"📊 Orders from normalize(): {len(orders)}")
            
            logger.info(f"📊 Total orders found: {len(orders)}")
            
            # Log first order for debugging (if any)
            if orders and len(orders) > 0:
                try:
                    first_order = orders[0]
                    logger.info(f"📊 First order sample: {json.dumps(first_order, default=str)[:800]}")
                except Exception as e:
                    logger.info(f"📊 Could not log first order: {e}")
            else:
                logger.warning("📊 NO ORDERS FOUND in the response!")
                logger.info(f"📊 Raw response data structure: {json.dumps(data, default=str)[:1000] if data else 'Empty'}")
                return []
            
            logger.info(f"Processing {len(orders)} orders for sales analytics")
            
            # Aggregate sales data
            total_revenue = 0.0
            total_transactions = 0
            unique_customers = set()
            total_items_sold = 0
            product_sales = {}
            customer_sales = {}
            monthly_data = {}
            
            for order in orders:
                # Handle None values in DocTotal
                doc_total_raw = order.get("DocTotal", 0)
                doc_total = float(doc_total_raw) if doc_total_raw is not None else 0.0
                card_code = order.get("CardCode")
                card_name = order.get("CardName", "Unknown")
                doc_date = order.get("DocDate", "")
                
                total_revenue += doc_total
                total_transactions += 1
                
                if card_code:
                    unique_customers.add(card_code)
                    if card_name not in customer_sales:
                        customer_sales[card_name] = {"revenue": 0, "count": 0, "code": card_code}
                    customer_sales[card_name]["revenue"] += doc_total
                    customer_sales[card_name]["count"] += 1
                
                # Monthly aggregation
                if doc_date and len(doc_date) >= 7:
                    month_key = doc_date[:7]
                    if month_key not in monthly_data:
                        monthly_data[month_key] = {"revenue": 0, "count": 0}
                    monthly_data[month_key]["revenue"] += doc_total
                    monthly_data[month_key]["count"] += 1
                
                # Process line items
                items = order.get("document_lines", []) or order.get("DocumentLines", [])
                for item in items:
                    item_code_val = item.get("ItemCode")
                    item_name = item.get("ItemName", "Unknown")
                    
                    # Handle None values in Quantity and Price
                    quantity_raw = item.get("Quantity", 0)
                    price_raw = item.get("Price", 0)
                    
                    quantity = float(quantity_raw) if quantity_raw is not None else 0.0
                    price = float(price_raw) if price_raw is not None else 0.0
                    line_total = quantity * price
                    
                    total_items_sold += quantity
                    
                    # Filter by item code if specified
                    if item_code and item_code_val != item_code:
                        continue
                    
                    # Aggregate product sales
                    if item_name not in product_sales:
                        product_sales[item_name] = {
                            "quantity": 0,
                            "revenue": 0,
                            "code": item_code_val or ""
                        }
                    product_sales[item_name]["quantity"] += quantity
                    product_sales[item_name]["revenue"] += line_total
            
            # Calculate average order value
            avg_order_value = total_revenue / total_transactions if total_transactions > 0 else 0
            
            # Get top products
            top_products = []
            for name, sales in sorted(product_sales.items(), key=lambda x: x[1]["revenue"], reverse=True)[:10]:
                top_products.append({
                    "name": name,
                    "code": sales["code"],
                    "quantity": int(sales["quantity"]),
                    "revenue": round(sales["revenue"], 2)
                })
            
            # Get top customers
            top_customers = []
            for name, sales in sorted(customer_sales.items(), key=lambda x: x[1]["revenue"], reverse=True)[:5]:
                top_customers.append({
                    "name": name,
                    "code": sales["code"],
                    "revenue": round(sales["revenue"], 2),
                    "orders": sales["count"]
                })
            
            # Format monthly data for display
            monthly_summary = []
            for month in sorted(monthly_data.keys())[-6:]:
                monthly_summary.append({
                    "month": month,
                    "revenue": round(monthly_data[month]["revenue"], 2),
                    "orders": monthly_data[month]["count"]
                })
            
            # Determine period description
            if period_days == 7:
                period_desc = "last 7 days"
            elif period_days == 30:
                period_desc = "last 30 days"
            elif period_days == 90:
                period_desc = "last 90 days"
            elif period_days == 365:
                period_desc = "last 365 days"
            else:
                period_desc = f"last {period_days} days"
            
            # Return formatted analytics
            result = [{
                "analysis_type": "sales_analytics",
                "period": period,
                "period_days": period_days,
                "period_description": period_desc,
                "date_range": {
                    "from": start_date.strftime("%Y-%m-%d"),
                    "to": end_date.strftime("%Y-%m-%d")
                },
                "summary": {
                    "total_revenue": round(total_revenue, 2),
                    "total_transactions": total_transactions,
                    "average_order_value": round(avg_order_value, 2),
                    "unique_customers": len(unique_customers),
                    "total_items_sold": int(total_items_sold)
                },
                "top_products": top_products,
                "top_customers": top_customers,
                "monthly_trend": monthly_summary,
                "data_points": len(orders),
                "source": "sales_orders_api",
                "note": f"Sales data for the {period_desc}"
            }]
            
            # FIXED: Properly format logging to avoid f-string condition inside format specifier
            logger.info("=" * 80)
            logger.info(f"✅ SALES ANALYTICS RETRIEVED SUCCESSFULLY:")
            logger.info(f"   Total Revenue: KES {total_revenue:,.2f}")
            logger.info(f"   Total Transactions: {total_transactions}")
            logger.info(f"   Unique Customers: {len(unique_customers)}")
            logger.info(f"   Total Items Sold: {int(total_items_sold)}")
            
            # Safely log top product
            if top_products:
                logger.info(f"   Top Product: {top_products[0]['name']} - KES {top_products[0]['revenue']:,.2f}")
            else:
                logger.info("   Top Product: N/A")
            
            # Safely log top customer
            if top_customers:
                logger.info(f"   Top Customer: {top_customers[0]['name']} - KES {top_customers[0]['revenue']:,.2f}")
            else:
                logger.info("   Top Customer: N/A")
            
            logger.info("=" * 80)
            
            return result
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch sales analytics: {e}", exc_info=True)
            logger.error("=" * 80)
            logger.error("🔍 SALES ANALYTICS DEBUG - FAILED")
            logger.error("=" * 80)
            return []

    # =========================================================
    # PHASE 2: CUSTOMER ORDERS API
    # =========================================================
    
    @cache_api_result(ttl_seconds=DELIVERY_CACHE_TTL)
    def get_customer_orders(
        self,
        customer_code: str = None,
        customer_name: str = None,
        limit: int = 50,
        doc_status: str = "all",
        from_date: str = None,
        to_date: str = None
    ) -> List[Dict]:
        """
        Get customer orders from SAP Business One.
        
        Args:
            customer_code: Customer code filter
            customer_name: Customer name (resolved to code)
            limit: Max orders to return
            doc_status: 'open', 'closed', or 'all'
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
        
        Returns:
            List of orders with line items
        """
        try:
            if not self._ensure_auth():
                return []
            
            # Resolve customer name to code if provided
            if customer_name and not customer_code:
                customer = self.resolve_customer(customer_name)
                if customer:
                    customer_code = customer.get("CardCode")
                    logger.info(f"Resolved customer '{customer_name}' to code: {customer_code}")
                else:
                    logger.warning(f"Could not resolve customer: {customer_name}")
                    return []
            
            # Use marketing docs endpoint for sales orders
            url = f"{self.base_url}/marketing/docs/17"
            params = {"page": 1, "per_page": limit}
            
            if customer_code:
                params["CardCode"] = customer_code
            
            if from_date:
                params["FromDate"] = from_date
            if to_date:
                params["ToDate"] = to_date
            
            logger.info(f"📋 Fetching customer orders from: {url} with params: {params}")
            self._record_api_call()
            resp = self.session.get(url, params=params, timeout=30)
            
            if not self._check_auth(resp):
                return []
            
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch orders: {resp.status_code}")
                return []
            
            if self._is_html_response(resp.text):
                logger.warning("Received HTML response - authentication may have expired")
                return []
            
            try:
                data = resp.json()
            except json.JSONDecodeError:
                logger.error("Failed to parse orders JSON")
                return []
            
            # Parse orders
            orders = []
            if data.get("ResultState") and data.get("ResponseData"):
                response_data = data["ResponseData"]
                if isinstance(response_data, dict):
                    if "data" in response_data:
                        orders = response_data["data"]
                    elif "DocumentLines" in response_data:
                        orders = [response_data]
                elif isinstance(response_data, list):
                    orders = response_data
            
            # Filter by status if needed
            filtered_orders = []
            for order in orders:
                doc_num = order.get("DocNum")
                if not doc_num:
                    continue
                
                # Determine order status
                has_open_items = False
                items = order.get("DocumentLines", [])
                for item in items:
                    if item.get("OpenQty", 0) > 0:
                        has_open_items = True
                        break
                
                order_status = "open" if has_open_items else "closed"
                
                if doc_status != "all" and order_status != doc_status:
                    continue
                
                # Format order
                formatted_order = {
                    "DocNum": doc_num,
                    "DocEntry": order.get("DocEntry"),
                    "DocDate": order.get("DocDate", ""),
                    "DocDueDate": order.get("DocDueDate", ""),
                    "CardCode": order.get("CardCode", customer_code),
                    "CardName": order.get("CardName", "Unknown"),
                    "DocTotal": float(order.get("DocTotal", 0) or 0),
                    "Status": "Open" if has_open_items else "Closed",
                    "Items": []
                }
                
                for item in items:
                    formatted_order["Items"].append({
                        "ItemCode": item.get("ItemCode"),
                        "ItemName": item.get("ItemName"),
                        "Quantity": float(item.get("Quantity", 0) or 0),
                        "OpenQty": float(item.get("OpenQty", 0) or 0),
                        "Price": float(item.get("Price", 0) or 0),
                        "LineTotal": float(item.get("LineTotal", 0) or 0)
                    })
                
                filtered_orders.append(formatted_order)
            
            logger.info(f"✅ Retrieved {len(filtered_orders)} orders for {customer_name or customer_code}")
            return filtered_orders
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch customer orders: {e}")
            return []

    # =========================================================
    # PHASE 2: OUTSTANDING DELIVERIES - FIXED with multiple approaches
    # =========================================================

    @cache_api_result(ttl_seconds=DELIVERY_CACHE_TTL)
    def get_outstanding_deliveries(
        self,
        customer_code: str = None,
        customer_name: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Fetch outstanding deliveries using multiple approaches.
        
        Approach 1: /marketing/docs/17 with DocStatus=1 (open orders)
        Approach 2: /marketing/docs/15 (deliveries endpoint)
        Approach 3: /deliveries endpoint
        """
        try:
            if not self._ensure_auth():
                logger.warning("Not authenticated, cannot fetch outstanding deliveries")
                return []

            # Resolve customer name → code if needed
            if customer_name and not customer_code:
                customer = self.resolve_customer(customer_name)
                if customer:
                    customer_code = customer.get("CardCode")
                    logger.info(f"✅ Resolved customer '{customer_name}' → CardCode: {customer_code}")
                else:
                    logger.warning(f"⚠️ Could not resolve customer name '{customer_name}' to a CardCode")

            # =========================================================
            # APPROACH 1: Sales Orders with DocStatus=1 (Open orders)
            # =========================================================
            url = f"{self.base_url}/marketing/docs/17"
            params = {
                "isDoc": 1,
                "page": 1,
                "per_page": limit,
                "DocStatus": 1,  # 1 = Open/outstanding
                "IsICT": "N",
            }
            if customer_code:
                params["CardCode"] = customer_code

            logger.info(f"📦 Approach 1: Fetching from {url} with params: {params}")
            resp = self.session.get(url, params=params, timeout=30)

            if resp.status_code == 200 and not self._is_html_response(resp.text):
                try:
                    data = resp.json()
                    
                    # Parse orders
                    orders = []
                    if data.get("ResultState") and data.get("ResponseData"):
                        response_data = data["ResponseData"]
                        if isinstance(response_data, dict):
                            orders = response_data.get("data", [])
                        elif isinstance(response_data, list):
                            orders = response_data
                    
                    if orders:
                        logger.info(f"✅ Found {len(orders)} outstanding orders via Approach 1")
                        return self._process_outstanding_orders(orders, customer_code, limit)
                except Exception as e:
                    logger.warning(f"Approach 1 parsing error: {e}")

            # =========================================================
            # APPROACH 2: Deliveries endpoint
            # =========================================================
            logger.info(f"📦 Approach 2: Trying deliveries endpoint")
            url = f"{self.base_url}/marketing/docs/15"
            params = {"page": 1, "per_page": limit}
            if customer_code:
                params["CardCode"] = customer_code
            
            resp = self.session.get(url, params=params, timeout=30)
            
            if resp.status_code == 200 and not self._is_html_response(resp.text):
                try:
                    data = resp.json()
                    deliveries = []
                    if data.get("ResultState") and data.get("ResponseData"):
                        response_data = data["ResponseData"]
                        if isinstance(response_data, dict):
                            deliveries = response_data.get("data", [])
                        elif isinstance(response_data, list):
                            deliveries = response_data
                    
                    if deliveries:
                        logger.info(f"✅ Found {len(deliveries)} deliveries via Approach 2")
                        # Filter for outstanding (not completed)
                        outstanding = [d for d in deliveries if d.get("DocStatus") != "C" and d.get("OpenQty", 0) > 0]
                        if outstanding:
                            return self._process_outstanding_orders(outstanding, customer_code, limit)
                except Exception as e:
                    logger.warning(f"Approach 2 parsing error: {e}")

            # =========================================================
            # APPROACH 3: Direct inventory report for stock (fallback)
            # =========================================================
            logger.info(f"📦 Approach 3: Using inventory report fallback")
            inventory = self.get_inventory_report(limit=limit)
            if inventory:
                # Filter items with committed orders > 0 (pending deliveries)
                outstanding_items = [
                    item for item in inventory 
                    if item.get("CurrentIsCommited", 0) > 0
                ][:limit]
                
                if outstanding_items:
                    logger.info(f"✅ Found {len(outstanding_items)} items with pending commitments")
                    return self._convert_inventory_to_outstanding(outstanding_items, customer_code)
            
            logger.info("No outstanding deliveries found using any approach")
            return []
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch outstanding deliveries: {e}", exc_info=True)
            return []

    def _process_outstanding_orders(self, orders: List[Dict], customer_code: str = None, limit: int = 100) -> List[Dict]:
        """Process raw orders into outstanding delivery format."""
        outstanding = []
        
        for order in orders[:limit]:
            doc_num = order.get("DocNum")
            doc_entry = order.get("DocEntry")
            card_code = order.get("CardCode") or customer_code
            card_name = order.get("CardName", "Unknown")
            doc_date = order.get("DocDate", "")
            doc_due_date = order.get("DocDueDate", "")
            doc_total = float(order.get("DocTotal", 0) or 0)
            
            items = order.get("document_lines", []) or order.get("DocumentLines", [])
            
            for item in items:
                item_code = item.get("ItemCode") or item.get("ProductCode")
                item_name = item.get("ItemName") or item.get("ProductName") or item_code
                quantity = float(item.get("Quantity", 0) or 0)
                open_qty = float(item.get("OpenQty", 0) or item.get("OpenQuantity", 0) or quantity)
                price = float(item.get("Price", 0) or 0)
                
                if open_qty > 0:
                    # Calculate if overdue
                    is_overdue = False
                    if doc_due_date:
                        try:
                            due_date = datetime.strptime(str(doc_due_date)[:10], "%Y-%m-%d")
                            if due_date < datetime.now():
                                is_overdue = True
                        except:
                            pass
                    
                    outstanding.append({
                        "DocNum": doc_num,
                        "DocEntry": doc_entry,
                        "CardCode": card_code,
                        "CardName": card_name,
                        "DocDate": doc_date,
                        "DocDueDate": doc_due_date,
                        "ItemCode": item_code,
                        "ItemName": item_name,
                        "Quantity": quantity,
                        "OpenQty": open_qty,
                        "Price": price,
                        "LineTotal": open_qty * price,
                        "Status": "Overdue" if is_overdue else "Outstanding",
                        "IsOverdue": is_overdue,
                    })
        
        logger.info(f"Processed {len(outstanding)} outstanding line items")
        return outstanding

    def _convert_inventory_to_outstanding(self, inventory_items: List[Dict], customer_code: str = None) -> List[Dict]:
        """Convert inventory items with commitments to outstanding delivery format."""
        outstanding = []
        
        for item in inventory_items[:50]:
            outstanding.append({
                "DocNum": None,
                "DocEntry": None,
                "CardCode": customer_code,
                "CardName": "Pending Delivery",
                "DocDate": datetime.now().strftime("%Y-%m-%d"),
                "DocDueDate": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                "ItemCode": item.get("ItemCode"),
                "ItemName": item.get("ItemName"),
                "Quantity": item.get("CurrentIsCommited", 0),
                "OpenQty": item.get("CurrentIsCommited", 0),
                "Price": 0,
                "LineTotal": 0,
                "Status": "Pending",
                "IsOverdue": False,
                "Note": "Based on inventory commitments"
            })
        
        return outstanding

    # -------------------------------------------------
    # ANALYTICS: TOP SELLING ITEMS - USING SALES ORDERS (FIXED with name resolution)
    # -------------------------------------------------
    @cache_api_result(ttl_seconds=ANALYTICS_CACHE_TTL)
    def get_top_selling_items(self, limit: int = 10, days: int = 30) -> List[Dict]:
        """
        Get top selling items from actual sales orders.
        This is much more accurate than inventory-based calculation.
        """
        try:
            if not self._ensure_auth():
                return []
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Fetch sales orders
            url = f"{self.base_url}/marketing/docs/17"
            params = {
                "page": 1,
                "per_page": 200,
                "FromDate": start_date.strftime("%Y-%m-%d"),
                "ToDate": end_date.strftime("%Y-%m-%d")
            }
            
            logger.info(f"📊 Fetching sales orders for top items from: {url}")
            resp = self.session.get(url, params=params, timeout=30)
            
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch orders: {resp.status_code}, falling back to inventory calculation")
                return self._calculate_top_selling_from_inventory(limit, days)
            
            if self._is_html_response(resp.text):
                logger.warning("Received HTML response, falling back to inventory calculation")
                return self._calculate_top_selling_from_inventory(limit, days)
            
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                return self._calculate_top_selling_from_inventory(limit, days)
            
            # Parse orders
            orders = []
            if data.get("ResultState") and data.get("ResponseData"):
                response_data = data["ResponseData"]
                if isinstance(response_data, dict):
                    orders = response_data.get("data", [])
                elif isinstance(response_data, list):
                    orders = response_data
            else:
                orders = self._normalize(data)
            
            if not orders:
                logger.info(f"No orders found in last {days} days")
                return self._calculate_top_selling_from_inventory(limit, days)
            
            # FIRST PASS: Collect all unique item codes
            item_codes_needed = set()
            for order in orders:
                items = order.get("document_lines", []) or order.get("DocumentLines", [])
                for item in items:
                    item_code = item.get("ItemCode")
                    if item_code:
                        item_codes_needed.add(item_code)
            
            logger.info(f"Found {len(item_codes_needed)} unique item codes in sales orders")
            
            # SECOND PASS: Fetch item names for all needed codes
            item_names = {}
            for item_code in list(item_codes_needed)[:100]:  # Limit to 100 items for performance
                try:
                    item = self.get_item_by_code(item_code)
                    if item:
                        item_names[item_code] = item.get("ItemName", item_code)
                    else:
                        item_names[item_code] = item_code
                except Exception as e:
                    logger.debug(f"Could not fetch item name for {item_code}: {e}")
                    item_names[item_code] = item_code
            
            logger.info(f"Resolved names for {len(item_names)} items")
            
            # THIRD PASS: Aggregate product sales with proper names
            product_sales = {}
            for order in orders:
                items = order.get("document_lines", []) or order.get("DocumentLines", [])
                for item in items:
                    item_code = item.get("ItemCode")
                    if not item_code:
                        continue
                    
                    quantity_raw = item.get("Quantity", 0)
                    quantity = float(quantity_raw) if quantity_raw is not None else 0
                    
                    if quantity > 0:
                        if item_code not in product_sales:
                            product_sales[item_code] = {
                                "name": item_names.get(item_code, item_code),
                                "quantity": 0,
                                "code": item_code
                            }
                        product_sales[item_code]["quantity"] += quantity
            
            if not product_sales:
                logger.info("No product sales found")
                return self._calculate_top_selling_from_inventory(limit, days)
            
            # Sort and return top items
            sorted_items = sorted(product_sales.values(), key=lambda x: x["quantity"], reverse=True)
            result = sorted_items[:limit]
            
            total_quantity = sum(item["quantity"] for item in result)
            
            for i, item in enumerate(result, 1):
                item["rank"] = i
                item["analysis_days"] = days
                item["analysis_period"] = f"Last {days} days"
                item["PopularityScore"] = min(100, round((item["quantity"] / max(1, result[0]["quantity"])) * 100, 1))
                item["percentage_of_top"] = round((item["quantity"] / max(1, total_quantity)) * 100, 1) if total_quantity > 0 else 0
            
            logger.info(f"✅ Found {len(result)} top selling items from sales orders")
            for item in result[:5]:
                logger.info(f"   Top {item['rank']}: {item['name']} - {item['quantity']} units sold")
            
            return result
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in get_top_selling_items: {e}")
            return self._calculate_top_selling_from_inventory(limit, days)

    # -------------------------------------------------
    # ANALYTICS: SLOW MOVING ITEMS - USING SALES ORDERS
    # -------------------------------------------------
    @cache_api_result(ttl_seconds=ANALYTICS_CACHE_TTL)
    def get_slow_moving_items(self, limit: int = 10, days: int = 90, turnover_threshold: float = 0.5) -> List[Dict]:
        """
        Get slow moving items based on actual sales orders.
        Items with low sales volume relative to stock level.
        """
        try:
            if not self._ensure_auth():
                return []
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Fetch sales orders
            url = f"{self.base_url}/marketing/docs/17"
            params = {
                "page": 1,
                "per_page": 200,
                "FromDate": start_date.strftime("%Y-%m-%d"),
                "ToDate": end_date.strftime("%Y-%m-%d")
            }
            
            logger.info(f"📊 Fetching sales orders for slow items from: {url}")
            resp = self.session.get(url, params=params, timeout=30)
            
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch orders: {resp.status_code}, falling back to inventory calculation")
                return self._calculate_slow_moving_from_inventory(limit, days, turnover_threshold)
            
            if self._is_html_response(resp.text):
                logger.warning("Received HTML response, falling back to inventory calculation")
                return self._calculate_slow_moving_from_inventory(limit, days, turnover_threshold)
            
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                return self._calculate_slow_moving_from_inventory(limit, days, turnover_threshold)
            
            # Parse orders
            orders = []
            if data.get("ResultState") and data.get("ResponseData"):
                response_data = data["ResponseData"]
                if isinstance(response_data, dict):
                    orders = response_data.get("data", [])
                elif isinstance(response_data, list):
                    orders = response_data
            else:
                orders = self._normalize(data)
            
            # Get inventory data for stock levels
            inventory = self.get_inventory_report(limit=500)
            inventory_map = {inv.get("ItemCode"): inv for inv in inventory}
            
            # FIRST PASS: Collect unique item codes
            item_codes_needed = set()
            for order in orders:
                order_items = order.get("document_lines", []) or order.get("DocumentLines", [])
                for item in order_items:
                    item_code = item.get("ItemCode")
                    if item_code:
                        item_codes_needed.add(item_code)
            
            # SECOND PASS: Fetch item names
            item_names = {}
            for item_code in list(item_codes_needed)[:100]:
                try:
                    item = self.get_item_by_code(item_code)
                    if item:
                        item_names[item_code] = item.get("ItemName", item_code)
                    else:
                        item_names[item_code] = item_code
                except Exception as e:
                    logger.debug(f"Could not fetch item name for {item_code}: {e}")
                    item_names[item_code] = item_code
            
            # Aggregate product sales with names
            product_sales = {}
            for order in orders:
                order_items = order.get("document_lines", []) or order.get("DocumentLines", [])
                for item in order_items:
                    item_code = item.get("ItemCode")
                    if not item_code:
                        continue
                    
                    quantity_raw = item.get("Quantity", 0)
                    quantity = float(quantity_raw) if quantity_raw is not None else 0
                    
                    if quantity > 0:
                        if item_code not in product_sales:
                            product_sales[item_code] = {
                                "name": item_names.get(item_code, item_code),
                                "quantity": 0,
                                "code": item_code
                            }
                        product_sales[item_code]["quantity"] += quantity
            
            # Calculate turnover and identify slow movers
            slow_items = []
            for item_code, sales_data in product_sales.items():
                inv_data = inventory_map.get(item_code)
                if not inv_data:
                    continue
                
                on_hand = inv_data.get("CurrentOnHand", 0)
                if on_hand <= 0:
                    continue
                
                daily_sales = sales_data["quantity"] / days if days > 0 else 0
                
                if daily_sales > 0:
                    days_of_stock = on_hand / daily_sales
                    turnover_rate = daily_sales * 365 / on_hand if on_hand > 0 else 0
                else:
                    days_of_stock = 999
                    turnover_rate = 0
                
                # Identify slow movers (low turnover or high days of stock)
                if turnover_rate < turnover_threshold or days_of_stock > 180:
                    severity = "critical" if days_of_stock > 365 or turnover_rate < 0.1 else "warning" if days_of_stock > 180 else "monitor"
                    
                    slow_items.append({
                        "ItemCode": item_code,
                        "ItemName": sales_data["name"],
                        "TurnoverRate": round(turnover_rate, 2),
                        "CurrentOnHand": on_hand,
                        "DaysOfStock": round(days_of_stock, 1),
                        "UnitsSold": int(sales_data["quantity"]),
                        "Severity": severity,
                        "Recommendation": self._get_slow_mover_recommendation(severity, days_of_stock, on_hand),
                        "analysis_days": days,
                        "analysis_period": f"Last {days} days",
                        "turnover_threshold": turnover_threshold
                    })
            
            # Sort by severity and turnover rate
            severity_order = {"critical": 0, "warning": 1, "monitor": 2}
            slow_items.sort(key=lambda x: (severity_order.get(x.get("Severity", "monitor"), 3), x.get("TurnoverRate", 999)))
            
            result = slow_items[:limit]
            logger.info(f"✅ Found {len(result)} slow moving items from sales orders")
            
            for i, item in enumerate(result, 1):
                item["rank"] = i
                # Ensure item has proper name
                if item.get("ItemName", "").startswith("Unknown") and item.get("ItemCode"):
                    # Try to get name one more time
                    try:
                        item_details = self.get_item_by_code(item.get("ItemCode"))
                        if item_details and item_details.get("ItemName"):
                            item["ItemName"] = item_details.get("ItemName")
                    except:
                        pass
            
            return result
            
        except Exception as e:
            self._record_error()
            logger.error(f"Error in get_slow_moving_items: {e}")
            return self._calculate_slow_moving_from_inventory(limit, days, turnover_threshold)

    def _get_slow_mover_recommendation(self, severity: str, days_of_stock: float, on_hand: float) -> str:
        """Generate recommendation for slow moving items."""
        if severity == "critical":
            if days_of_stock > 365:
                return "⚠️ CRITICAL: Over 1 year of stock - Consider write-off or deep discount (50%+ off)"
            elif on_hand > 1000:
                return "⚠️ CRITICAL: Large quantity with low turnover - Run clearance sale immediately"
            else:
                return "⚠️ CRITICAL: Very slow moving - Consider bundle with popular items or markdown"
        elif severity == "warning":
            if days_of_stock > 180:
                return "⚠️ WARNING: Over 6 months of stock - Review pricing and consider promotion"
            else:
                return "⚠️ WARNING: Low turnover - Monitor and consider marketing push"
        else:
            return "📊 Monitor: Review sales velocity monthly and consider small promotion"

    # -------------------------------------------------
    # INVENTORY-BASED CALCULATIONS (FALLBACKS)
    # -------------------------------------------------
    
    def _calculate_top_selling_from_inventory(self, limit: int = 20, days: int = 30) -> List[Dict]:
        """
        Calculate top selling items from inventory data using multiple metrics.
        FALLBACK when sales orders API is unavailable.
        """
        try:
            inventory = self.get_inventory_report(limit=1000)
            
            if not inventory:
                logger.warning("No inventory data available for top selling calculation")
                return []
            
            scored_items = []
            
            for item in inventory:
                item_code = item.get("ItemCode", "")
                item_name = item.get("ItemName", "")
                
                if not item_code and not item_name:
                    continue
                
                on_hand = float(item.get("CurrentOnHand", 0))
                committed = float(item.get("CurrentIsCommited", 0))
                period_out_qty = float(item.get("PeriodOutQty", 0))
                last_transaction = item.get("LastTransactionDate", "")
                
                demand_score = 0
                
                if period_out_qty > 0:
                    daily_sales = period_out_qty / days if days > 0 else 0
                    demand_score = min(100, daily_sales * 10)
                elif committed > 0:
                    if on_hand > 0:
                        demand_ratio = min(2.0, committed / on_hand)
                        demand_score = min(100, demand_ratio * 50)
                    else:
                        demand_score = min(100, 50 + (committed / 100))
                elif on_hand > 0:
                    demand_score = 5
                
                recency_bonus = 0
                if last_transaction:
                    try:
                        last_date = datetime.strptime(last_transaction, "%Y-%m-%d")
                        days_ago = (datetime.now() - last_date).days
                        if days_ago < 7:
                            recency_bonus = 30
                        elif days_ago < 30:
                            recency_bonus = 20
                        elif days_ago < 90:
                            recency_bonus = 10
                        else:
                            recency_bonus = 5
                    except:
                        pass
                
                turnover_bonus = 0
                if on_hand > 0 and committed > 0:
                    turnover_ratio = committed / on_hand
                    if turnover_ratio > 2:
                        turnover_bonus = 25
                    elif turnover_ratio > 1:
                        turnover_bonus = 15
                    elif turnover_ratio > 0.5:
                        turnover_bonus = 10
                
                stockout_bonus = 0
                if on_hand > 0 and committed > on_hand:
                    stockout_bonus = 20
                
                total_score = demand_score + recency_bonus + turnover_bonus + stockout_bonus
                
                if total_score >= 80:
                    velocity = "VERY_HIGH"
                elif total_score >= 60:
                    velocity = "HIGH"
                elif total_score >= 40:
                    velocity = "MEDIUM"
                elif total_score >= 20:
                    velocity = "LOW"
                else:
                    velocity = "VERY_LOW"
                
                if total_score > 0 or on_hand > 0:
                    scored_items.append({
                        "ItemCode": item_code,
                        "ItemName": item_name if item_name else item_code,
                        "PopularityScore": round(total_score, 2),
                        "CurrentOnHand": on_hand,
                        "CurrentIsCommited": committed,
                        "Velocity": velocity,
                    })
            
            scored_items.sort(key=lambda x: x["PopularityScore"], reverse=True)
            result = scored_items[:limit]
            
            for i, item in enumerate(result, 1):
                item["rank"] = i
                item["analysis_days"] = days
                item["analysis_period"] = f"Last {days} days"
                item["source"] = "inventory_fallback"
            
            logger.info(f"✅ Calculated {len(result)} top selling items from inventory data (fallback)")
            return result
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to calculate top selling from inventory: {e}")
            return []

    def _calculate_slow_moving_from_inventory(self, limit: int = 20, days: int = 90, turnover_threshold: float = 0.5) -> List[Dict]:
        """Calculate slow moving items from inventory data. FALLBACK."""
        try:
            inventory = self.get_inventory_report(limit=1000)
            
            if not inventory:
                logger.warning("No inventory data available for slow moving calculation")
                return []
            
            slow_items = []
            
            for item in inventory:
                on_hand = float(item.get("CurrentOnHand", 0))
                committed = float(item.get("CurrentIsCommited", 0))
                last_transaction = item.get("LastTransactionDate", "")
                period_out_qty = float(item.get("PeriodOutQty", 0))
                
                if on_hand > 0:
                    if committed > 0:
                        turnover_rate = committed / on_hand
                    elif period_out_qty > 0:
                        turnover_rate = period_out_qty / on_hand / (days / 30)
                    else:
                        turnover_rate = 0.05
                else:
                    turnover_rate = 0
                
                turnover_rate = min(turnover_rate, 5.0)
                
                if turnover_rate < turnover_threshold and on_hand > 0:
                    days_since = None
                    if last_transaction:
                        try:
                            last_date = datetime.strptime(last_transaction, "%Y-%m-%d")
                            days_since = (datetime.now() - last_date).days
                        except:
                            pass
                    
                    if turnover_rate < 0.1:
                        severity = "critical"
                        recommendation = "⚠️ CRITICAL: Consider markdown or bundle promotion immediately"
                    elif turnover_rate < 0.3:
                        severity = "warning"
                        recommendation = "⚠️ Review pricing strategy or consider discontinuation"
                    else:
                        severity = "monitor"
                        recommendation = "Monitor sales velocity and consider promotional offers"
                    
                    if days_since and days_since > 180:
                        recommendation = f"⚠️ No activity for {days_since} days - Consider write-off or deep discount"
                    elif days_since and days_since > 90:
                        recommendation = f"⚠️ No activity for {days_since} days - Bundle with popular items"
                    elif on_hand > 1000 and turnover_rate < 0.1:
                        recommendation = "📦 Excess stock - Run clearance sale immediately"
                    
                    slow_items.append({
                        "ItemCode": item.get("ItemCode"),
                        "ItemName": item.get("ItemName"),
                        "TurnoverRate": round(turnover_rate, 2),
                        "CurrentOnHand": on_hand,
                        "DaysSinceLastTransaction": days_since if days_since else "N/A",
                        "Severity": severity,
                        "Recommendation": recommendation,
                        "source": "inventory_fallback"
                    })
            
            slow_items.sort(key=lambda x: x["TurnoverRate"])
            result = slow_items[:limit]
            
            for i, item in enumerate(result, 1):
                item["rank"] = i
                item["analysis_days"] = days
                item["analysis_period"] = f"Last {days} days"
                item["turnover_threshold"] = turnover_threshold
            
            logger.info(f"✅ Calculated {len(result)} slow moving items from inventory data (fallback)")
            return result
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to calculate slow moving from inventory: {e}")
            return []

    # -------------------------------------------------
    # CACHE MANAGEMENT
    # -------------------------------------------------
    
    def clear_cache(self):
        """Clear all caches."""
        self._customer_cache.clear()
        self._customer_cache_time.clear()
        self._vendor_cache.clear()
        self._vendor_cache_time.clear()
        self._lead_cache.clear()
        self._lead_cache_time.clear()
        self._endpoint_cache.clear()
        
        # Clear pricing service cache
        if self._pricing_service:
            self._pricing_service.clear_cache()
        
        # Clear Redis cache
        cache = get_cache_service()
        cache.clear()
        
        logger.info("LeyscoAPIService cache cleared")
        self._stats["cache_hits"] = 0
        self._stats["cache_misses"] = 0


# =========================================================
# IMPORTANT: No singleton instance for Phase 1
# Each request creates its own instance with user token
# =========================================================

def create_api_service(user_token: str) -> LeyscoAPIService:
    """
    Create a new API service instance with the user's token.
    This should be called for each request.
    
    Args:
        user_token: The authenticated user's Bearer token
    
    Returns:
        Configured LeyscoAPIService instance
    """
    if not user_token:
        logger.warning("Creating API service without user token - data access will fail")
    return LeyscoAPIService(user_token=user_token)