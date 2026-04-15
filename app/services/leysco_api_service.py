"""
app/services/leysco_api_service.py
===================================
Leysco API Service - Enhanced with Business Partner Type Filtering and Pagination
Optimized with connection pooling, Redis caching, and async support
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
            cache = get_cache_service()
            
            # Generate cache key
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
    AI-Optimized Version with Business Partner Type Filtering
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

    def __init__(self):
        self.base_url = settings.LEYSCO_API_BASE_URL.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {settings.LEYSCO_API_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # Configure session with connection pooling
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Connection pooling for better performance
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=Retry(
                total=3,
                backoff_factor=0.3,
                status_forcelist=[429, 500, 502, 503, 504]
            )
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        self.timeout = 30
        self._is_authenticated = True
        
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
    # AUTHENTICATION HELPERS
    # -------------------------------------------------
    
    def _check_auth(self, response: requests.Response) -> bool:
        """Check if response indicates authentication failure."""
        if response.status_code == 401 or response.status_code == 302:
            self._stats["auth_errors"] += 1
            logger.warning(f"Authentication issue detected (status {response.status_code})")
            
            # Try to re-authenticate if credentials are available
            if hasattr(settings, 'LEYSCO_USERNAME') and hasattr(settings, 'LEYSCO_PASSWORD'):
                if self.login(settings.LEYSCO_USERNAME, settings.LEYSCO_PASSWORD):
                    logger.info("Re-authentication successful")
                    return True
            
            self._is_authenticated = False
            return False
        
        return True
    
    def _ensure_auth(self) -> bool:
        """Ensure we have valid authentication."""
        if not self._is_authenticated:
            if hasattr(settings, 'LEYSCO_USERNAME') and hasattr(settings, 'LEYSCO_PASSWORD'):
                return self.login(settings.LEYSCO_USERNAME, settings.LEYSCO_PASSWORD)
        return self._is_authenticated

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
    # AUTHENTICATION
    # -------------------------------------------------
    def login(self, username: str, password: str) -> bool:
        """Authenticate with the API and store token."""
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
                    # Retry with new auth
                    resp = self.session.get(url, params=params, timeout=30)
                
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
                    resp = self.session.get(url, params=params, timeout=30)
                
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
                    resp = self.session.get(url, params=params, timeout=30)
                
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
                    resp = self.session.get(url, params=params, timeout=30)
                
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
                resp = self.session.get(url, params=params, timeout=15)
            
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
                    logger.warning("Authentication failed during inventory fetch, retrying...")
                    resp = self.session.get(url, params=params, timeout=15)
                
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
                logger.warning("Authentication failed during warehouse fetch, retrying...")
                resp = self.session.get(url, params=params, timeout=15)
            
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
            
            # Try multiple possible endpoints - prioritize /marketing/docs/17
            endpoints_to_try = [
                "/marketing/docs/17",  # SAP document type for Sales Orders (priority - working endpoint)
                "/sales_orders?status=open",
                "/orders?status=open",
                "/documents/order",
            ]
            
            for endpoint in endpoints_to_try:
                url = f"{self.base_url}{endpoint}"
                params = {"page": 1, "per_page": limit}
                if customer_code:
                    params["CardCode"] = customer_code
                
                logger.info(f"📦 Fetching open sales orders from: {url}")
                self._record_api_call()
                
                try:
                    resp = self.session.get(url, params=params, timeout=15)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        
                        # Parse based on endpoint
                        orders = []
                        
                        if endpoint == "/marketing/docs/17":
                            # Handle the specific format from /marketing/docs/17
                            if data.get("ResultState") and data.get("ResponseData"):
                                response_data = data["ResponseData"]
                                if isinstance(response_data, dict):
                                    # Check for data array (list of documents)
                                    if "data" in response_data:
                                        orders = response_data["data"]
                                    elif "DocumentLines" in response_data:
                                        # Single document returned
                                        orders = [response_data]
                                elif isinstance(response_data, list):
                                    orders = response_data
                        else:
                            # Use standard normalization for other endpoints
                            orders = self._normalize(data)
                        
                        if orders:
                            logger.info(f"✅ Found {len(orders)} orders from {endpoint}")
                            
                            # Process and format orders to extract line items
                            formatted_orders = []
                            
                            for order in orders:
                                # Extract order header
                                doc_num = order.get("DocNum") or order.get("doc_num") or order.get("DocumentNumber")
                                doc_entry = order.get("DocEntry") or order.get("doc_entry") or order.get("DocumentEntry")
                                card_code = order.get("CardCode") or order.get("card_code") or customer_code
                                card_name = order.get("CardName") or order.get("card_name") or "Unknown"
                                doc_date = order.get("DocDate") or order.get("doc_date") or ""
                                doc_due_date = order.get("DocDueDate") or order.get("doc_due_date") or ""
                                
                                # Get items - check multiple possible field names
                                items = (order.get("DocumentLines") or 
                                        order.get("items") or 
                                        order.get("Lines") or 
                                        order.get("document_lines") or
                                        [])
                                
                                # If no items found and order is a single item structure
                                if not items and order.get("ItemCode"):
                                    items = [order]
                                
                                logger.debug(f"Processing order {doc_num}: {len(items)} items")
                                
                                for item in items:
                                    item_code = item.get("ItemCode") or item.get("item_code") or item.get("ProductCode")
                                    item_name = item.get("ItemName") or item.get("item_name") or item.get("ProductName")
                                    quantity = float(item.get("Quantity") or item.get("quantity") or 0)
                                    open_qty = float(item.get("OpenQty") or item.get("open_qty") or item.get("OpenQuantity") or quantity)
                                    price = float(item.get("Price") or item.get("price") or 0)
                                    
                                    # Only include items with outstanding quantity
                                    if open_qty > 0:
                                        formatted_orders.append({
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
                                            "Status": "Open"
                                        })
                                        logger.debug(f"  Added item: {item_code} - {item_name}, OpenQty: {open_qty}")
                                
                                # Limit the number of orders to prevent overwhelming response
                                if len(formatted_orders) >= limit:
                                    break
                            
                            if formatted_orders:
                                logger.info(f"✅ Processed {len(formatted_orders)} line items from {endpoint}")
                                return formatted_orders
                            else:
                                logger.warning(f"Found {len(orders)} orders but no items with outstanding quantity")
                        
                except Exception as e:
                    logger.debug(f"Endpoint {endpoint} failed: {e}")
                    continue
            
            # If we get here, no orders found
            logger.info("No open sales orders found from any endpoint")
            return []
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch open sales orders: {e}", exc_info=True)
            return []

    # -------------------------------------------------
    # ANALYTICS: TOP SELLING ITEMS (ENHANCED FALLBACK)
    # -------------------------------------------------
    @cache_api_result(ttl_seconds=ANALYTICS_CACHE_TTL)
    def get_top_selling_items(self, limit: int = 10, days: int = 30) -> List[Dict]:
        """
        Get top selling items based on sales velocity.
        Uses inventory data with recency scoring when API endpoint is unavailable.
        """
        try:
            # Try API endpoint first
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            url = f"{self.base_url}/sales_analysis/top_items"
            params = {
                "FromDate": start_date.strftime("%Y-%m-%d"),
                "ToDate": end_date.strftime("%Y-%m-%d"),
                "limit": limit,
            }
            
            if self._ensure_auth():
                self._record_api_call()
                resp = self.session.get(url, params=params, timeout=20)
                
                if resp.status_code == 200:
                    try:
                        items = self._normalize(resp.json())
                        if items:
                            for i, item in enumerate(items, 1):
                                item["rank"] = i
                                item["analysis_days"] = days
                                item["analysis_period"] = f"Last {days} days"
                            logger.info(f"✅ Retrieved {len(items)} top selling items from API")
                            return items
                    except:
                        pass
            
            # Fallback: Calculate from inventory data
            return self._calculate_top_selling_from_inventory(limit, days)
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch top selling items: {e}")
            return self._calculate_top_selling_from_inventory(limit, days)

    # =========================================================
    # FIXED: _calculate_top_selling_from_inventory
    # =========================================================
    
    def _calculate_top_selling_from_inventory(self, limit: int = 20, days: int = 30) -> List[Dict]:
        """
        Calculate top selling items from inventory data using multiple metrics.
        FIXED: Properly handles zero PeriodOutQty by using committed orders as demand indicator.
        """
        try:
            inventory = self.get_inventory_report(limit=1000)
            
            if not inventory:
                logger.warning("No inventory data available for top selling calculation")
                return []
            
            scored_items = []
            
            for item in inventory:
                # Extract item details
                item_code = item.get("ItemCode", "")
                item_name = item.get("ItemName", "")
                
                # Skip items with no name or code
                if not item_code and not item_name:
                    continue
                
                # Get stock metrics
                on_hand = float(item.get("CurrentOnHand", 0))
                committed = float(item.get("CurrentIsCommited", 0))
                period_out_qty = float(item.get("PeriodOutQty", 0))
                last_transaction = item.get("LastTransactionDate", "")
                
                # Calculate demand score based on available data
                demand_score = 0
                
                # If we have period out quantity (actual sales), use that
                if period_out_qty > 0:
                    # Daily sales rate over the period
                    daily_sales = period_out_qty / days if days > 0 else 0
                    demand_score = min(100, daily_sales * 10)  # Scale: 10 units/day = 100 score
                elif committed > 0:
                    # Use committed orders as demand indicator
                    # High committed relative to on-hand indicates demand
                    if on_hand > 0:
                        demand_ratio = min(2.0, committed / on_hand)
                        demand_score = min(100, demand_ratio * 50)
                    else:
                        # Out of stock with committed orders - high demand
                        demand_score = min(100, 50 + (committed / 100))
                elif on_hand > 0:
                    # Have stock but no demand indicators - low priority
                    demand_score = 5
                
                # Recency bonus (newer transactions = higher score)
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
                
                # Turnover bonus (how fast stock is moving relative to on-hand)
                turnover_bonus = 0
                if on_hand > 0 and committed > 0:
                    turnover_ratio = committed / on_hand
                    if turnover_ratio > 2:
                        turnover_bonus = 25
                    elif turnover_ratio > 1:
                        turnover_bonus = 15
                    elif turnover_ratio > 0.5:
                        turnover_bonus = 10
                
                # Stockout bonus (items with low stock and high committed)
                stockout_bonus = 0
                if on_hand > 0 and committed > on_hand:
                    stockout_bonus = 20  # Items that are backordered
                
                total_score = demand_score + recency_bonus + turnover_bonus + stockout_bonus
                
                # Determine velocity category
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
                
                # Only include items with some activity
                if total_score > 0 or on_hand > 0:
                    scored_items.append({
                        "ItemCode": item_code,
                        "ItemName": item_name if item_name else item_code,
                        "PopularityScore": round(total_score, 2),
                        "CurrentOnHand": on_hand,
                        "CurrentIsCommited": committed,
                        "PeriodOutQty": period_out_qty,
                        "LastTransactionDate": last_transaction if last_transaction else "N/A",
                        "Velocity": velocity,
                        "DemandScore": round(demand_score, 1),
                        "RecencyBonus": round(recency_bonus, 1),
                    })
            
            # Sort by popularity score (highest first)
            scored_items.sort(key=lambda x: x["PopularityScore"], reverse=True)
            result = scored_items[:limit]
            
            for i, item in enumerate(result, 1):
                item["rank"] = i
                item["analysis_days"] = days
                item["analysis_period"] = f"Last {days} days"
            
            logger.info(f"✅ Calculated {len(result)} top selling items from inventory data")
            
            # Log the first few items for debugging
            for item in result[:5]:
                logger.info(f"   Top item: {item.get('ItemName')} (Code: {item.get('ItemCode')}, Score: {item.get('PopularityScore')})")
            
            return result
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to calculate top selling from inventory: {e}")
            return []

    # -------------------------------------------------
    # ANALYTICS: SLOW MOVING ITEMS (ENHANCED FALLBACK)
    # -------------------------------------------------
    @cache_api_result(ttl_seconds=ANALYTICS_CACHE_TTL)
    def get_slow_moving_items(self, limit: int = 10, days: int = 90, turnover_threshold: float = 0.5) -> List[Dict]:
        """
        Get slow moving items based on turnover rate.
        Uses inventory data when API endpoint is unavailable.
        """
        try:
            # Try API endpoint first
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            url = f"{self.base_url}/sales_analysis/slow_items"
            params = {
                "FromDate": start_date.strftime("%Y-%m-%d"),
                "ToDate": end_date.strftime("%Y-%m-%d"),
                "limit": limit,
                "turnover_threshold": turnover_threshold,
            }
            
            if self._ensure_auth():
                self._record_api_call()
                resp = self.session.get(url, params=params, timeout=20)
                
                if resp.status_code == 200:
                    try:
                        items = self._normalize(resp.json())
                        if items:
                            for i, item in enumerate(items, 1):
                                item["rank"] = i
                                item["analysis_days"] = days
                                item["analysis_period"] = f"Last {days} days"
                                item["turnover_threshold"] = turnover_threshold
                            logger.info(f"✅ Retrieved {len(items)} slow moving items from API")
                            return items
                    except:
                        pass
            
            # Fallback: Calculate from inventory data
            return self._calculate_slow_moving_from_inventory(limit, days, turnover_threshold)
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to fetch slow moving items: {e}")
            return self._calculate_slow_moving_from_inventory(limit, days, turnover_threshold)

    def _calculate_slow_moving_from_inventory(self, limit: int = 20, days: int = 90, turnover_threshold: float = 0.5) -> List[Dict]:
        """
        Calculate slow moving items from inventory data.
        No hardcoded data - all calculations based on actual inventory.
        """
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
                
                # Calculate turnover rate
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
                
                # Check if slow moving
                if turnover_rate < turnover_threshold and on_hand > 0:
                    days_since = None
                    if last_transaction:
                        try:
                            last_date = datetime.strptime(last_transaction, "%Y-%m-%d")
                            days_since = (datetime.now() - last_date).days
                        except:
                            pass
                    
                    # Determine severity and recommendation
                    if turnover_rate < 0.1:
                        severity = "critical"
                        urgency = "HIGH - Immediate action required"
                        recommendation = "⚠️ CRITICAL: Consider markdown or bundle promotion immediately"
                    elif turnover_rate < 0.3:
                        severity = "warning"
                        urgency = "MEDIUM - Review within 30 days"
                        recommendation = "⚠️ Review pricing strategy or consider discontinuation"
                    else:
                        severity = "monitor"
                        urgency = "LOW - Monitor monthly"
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
                        "CurrentIsCommited": committed,
                        "PeriodOutQty": period_out_qty,
                        "DaysSinceLastTransaction": days_since if days_since else "N/A",
                        "Severity": severity,
                        "Urgency": urgency,
                        "Recommendation": recommendation,
                    })
            
            slow_items.sort(key=lambda x: x["TurnoverRate"])
            result = slow_items[:limit]
            
            for i, item in enumerate(result, 1):
                item["rank"] = i
                item["analysis_days"] = days
                item["analysis_period"] = f"Last {days} days"
                item["turnover_threshold"] = turnover_threshold
            
            logger.info(f"✅ Calculated {len(result)} slow moving items from inventory data")
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


# Singleton instance
_leysco_api_instance: Optional[LeyscoAPIService] = None


def get_leysco_api_service() -> LeyscoAPIService:
    """Get or create singleton instance."""
    global _leysco_api_instance
    if _leysco_api_instance is None:
        _leysco_api_instance = LeyscoAPIService()
        logger.info("✅ Created new LeyscoAPIService singleton instance")
    return _leysco_api_instance