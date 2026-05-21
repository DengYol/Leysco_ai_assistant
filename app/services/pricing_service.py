"""
pricing_service.py
==================
SAP B1-style pricing for Leysco - Optimized with caching and async support

MODIFIED FOR PHASE 1: Uses per-request user token instead of static token.

Pricing hierarchy (highest → lowest priority):
  1. Customer's assigned price list  (octg.ListNum)
  2. Base price list chain           (BASE_NUM walking)
  3. Default price list              (ListNum = 1)

Key behaviours mirrored from SAP B1:
  - Price list chaining via BASE_NUM
  - Price = 0 means "not priced on this list" → fall back
  - isGrossPrc = "Y" → price already includes VAT
  - UomEntry reported alongside price
  - API id ≠ SAP ListNum — we maintain a map at startup

Optimizations:
  - Redis caching for price lookups (1 hour TTL)
  - Batch price fetching support
  - Async methods for concurrent requests
  - Connection pooling
  - Price list map caching
  - Simple key-value cache for faster lookups
"""

import logging
import time
import asyncio
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from functools import lru_cache, wraps
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.config import settings, get_leysco_api_base_url
from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
DEFAULT_SAP_LIST_NUM = 1          # fallback if customer has no list assigned
MAX_CHAIN_DEPTH      = 10         # safety limit for BASE_NUM walking

# Non-EA price lists (api_ids 23-34) all return 500.
# Map each broken SAP ListNum to its working EA equivalent.
# e.g. customer on ListNum=1 'Price List 01' → try ListNum=26 'Price List 01 - EA'
NON_EA_TO_EA_FALLBACK = {
    1:  26,   # Price List 01       → Price List 01 - EA
    2:  18,   # RETAIL PRICELIST    → RETAIL PRICELIST - EA
    3:  19,   # DISTRIBUTOR         → DISTRIBUTOR - EA
    4:  20,   # INTERCOMPANY        → INTERCOMPANY - EA
    5:  21,   # WHOLESALE           → WHOLESALE - EA
    6:  22,   # MD PRICE            → MD PRICE - EA
    10: 17,   # Price List 10       → Price List 10 - EA
}
PRICE_LIST_SEARCH_TIMEOUT = 20    # seconds
PRICE_CACHE_TTL = 3600            # 1 hour for price cache (increased from 5 min)


def cache_price(ttl_seconds: int = PRICE_CACHE_TTL):
    """
    Decorator to cache price results with simple key-value storage.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            cache = get_cache_service()
            
            # Generate simple cache key
            item_code = kwargs.get('item_code') or (args[0] if args else None)
            sap_list_num = kwargs.get('sap_list_num') or (args[1] if len(args) > 1 else None)
            
            if not item_code:
                return func(self, *args, **kwargs)
            
            cache_key = f"price:{item_code}:{sap_list_num or 'default'}"
            
            # Check cache using simple method
            cached = cache.get_simple(cache_key)
            if cached is not None:
                logger.info(f"📦 Price cache hit: {item_code}")
                return cached
            
            # Execute function
            result = func(self, *args, **kwargs)
            
            # Cache result (even if not found, to avoid repeated lookups)
            if result:
                cache.set_simple(cache_key, result, ttl=ttl_seconds)
            
            return result
        return wrapper
    return decorator


class PricingService:
    """
    Resolves item prices following the SAP B1 pricing hierarchy.
    Optimized with caching, connection pooling, and async support.
    MODIFIED: Uses per-request user token instead of static token.
    """

    def __init__(self, user_token: str = None, company_code: str = None):
        """
        Initialize pricing service with user token and company code.
        
        Args:
            user_token: Bearer token from authenticated user
            company_code: Company code for multi-tenant URL resolution
        """
        self.company_code = company_code
        self.user_token = user_token
        
        # Resolve base URL dynamically using company code
        if company_code:
            self.base_url = get_leysco_api_base_url(company_code).rstrip("/")
            logger.debug(f"PricingService resolved base URL for {company_code}: {self.base_url}")
        else:
            # Fallback to global setting (should not happen in multi-tenant)
            self.base_url = settings.LEYSCO_API_BASE_URL.rstrip("/")
            logger.warning(f"PricingService initialized without company_code, using global URL: {self.base_url}")
        
        # Configure session with connection pooling
        self.session = requests.Session()
        
        # Connection pooling for better performance
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=Retry(
                total=2,  # Reduced - don't retry auth failures
                backoff_factor=0.3,
                status_forcelist=[429, 500, 502, 503, 504]  # 401 removed
            )
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # Initialize headers WITHOUT static token
        self._update_headers()

        # Built once per service lifetime — refreshed by calling _build_maps()
        # sap_list_num (int) → price list dict (contains id, BASE_NUM, isGrossPrc …)
        self._list_by_sap_num: Dict[int, Dict] = {}
        # api_id (int) → price list dict
        self._list_by_api_id:  Dict[int, Dict] = {}
        
        # Cache for price list maps (refreshed periodically)
        self._price_list_cache_time = 0
        self._price_list_cache_ttl = 3600  # 1 hour
        
        # Stats tracking
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "errors": 0
        }
        
        self._build_maps()
    
    def _update_headers(self):
        """Update request headers with current user token."""
        headers = {"Content-Type": "application/json"}
        
        if self.user_token:
            headers["Authorization"] = f"Bearer {self.user_token}"
            logger.debug("PricingService headers updated with user token")
        else:
            logger.warning("PricingService initialized WITHOUT user token - price lookups will fail")
        
        self.session.headers.update(headers)
    
    def set_user_token(self, token: str):
        """Update user token for this instance."""
        self.user_token = token
        self._update_headers()
        logger.debug("PricingService user token updated")
    
    def set_company_code(self, company_code: str):
        """Update company code and re-resolve base URL."""
        self.company_code = company_code
        if company_code:
            self.base_url = get_leysco_api_base_url(company_code).rstrip("/")
            logger.debug(f"PricingService base URL updated for {company_code}: {self.base_url}")
    
    def _ensure_auth(self) -> bool:
        """Check if we have a valid user token."""
        if not self.user_token:
            logger.warning("No user token available for price lookup")
            return False
        return True

    # ------------------------------------------------------------------
    # STATS HELPERS
    # ------------------------------------------------------------------
    
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

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def get_price_for_customer(
        self,
        item_code: str,
        customer: Dict,
        use_cache: bool = True,
    ) -> Dict:
        """
        Resolve the price of item_code for a given customer dict.

        The customer dict must contain either:
          - customer["PriceListNum"]   (direct field, often null)
          - customer["octg"]["ListNum"] (from payment group — more reliable)

        Returns a result dict — never raises.
        """
        if not self._ensure_auth():
            return {
                "found": False,
                "item_code": item_code,
                "price": None,
                "note": "Authentication required for price lookup"
            }
        
        sap_list_num = self._customer_list_num(customer)
        return self.get_price(item_code=item_code, sap_list_num=sap_list_num, use_cache=use_cache)

    @cache_price(ttl_seconds=PRICE_CACHE_TTL)
    def get_price(
        self,
        item_code: str,
        sap_list_num: int = DEFAULT_SAP_LIST_NUM,
        use_cache: bool = True,
    ) -> Dict:
        """
        Walk the price list chain starting at sap_list_num until a
        non-zero price is found, then return a rich result dict.

        Result dict keys:
          item_code        str
          price            float | None
          currency         str   ("KES")
          uom_entry        int | None
          is_gross_price   bool  (True = VAT included)
          price_list_id    int   (API id used)
          price_list_name  str
          sap_list_num     int   (SAP ListNum used)
          chain_walked     list  (SAP ListNums tried, in order)
          found            bool
          note             str
        """
        if not self._ensure_auth():
            return {
                "found": False,
                "item_code": item_code,
                "price": None,
                "note": "Authentication required for price lookup"
            }
        
        # Check cache first using simple method (if not using decorator)
        if use_cache:
            cache = get_cache_service()
            cache_key = f"price:{item_code}:{sap_list_num}"
            cached = cache.get_simple(cache_key)
            if cached is not None:
                self._record_cache_hit()
                logger.info(f"📦 Price cache hit: {item_code} on list {sap_list_num}")
                return cached
        
        self._record_cache_miss()
        
        chain_walked: List[int] = []
        current_sap_num         = sap_list_num
        depth                   = 0

        while depth < MAX_CHAIN_DEPTH:
            depth        += 1
            price_list = self._list_by_sap_num.get(current_sap_num)

            # If this SAP ListNum maps to a broken non-EA list,
            # silently redirect to the EA equivalent before fetching
            if price_list:
                api_id = self._to_int(price_list.get('id'))
                ea_sap_num = NON_EA_TO_EA_FALLBACK.get(current_sap_num)
                if ea_sap_num and api_id and api_id >= 23:
                    ea_list = self._list_by_sap_num.get(ea_sap_num)
                    if ea_list:
                        logger.info(
                            f'  Redirecting SAP {current_sap_num} '
                            f'(api_id={api_id}, broken) '
                            f'→ EA equivalent SAP {ea_sap_num} '
                            f'({ea_list.get("ListName")})'
                        )
                        price_list      = ea_list
                        current_sap_num = ea_sap_num

            if not price_list:
                note = (
                    f"SAP list {current_sap_num} not found in price list map. "
                    f"Chain: {chain_walked}"
                )
                logger.warning(note)
                break

            chain_walked.append(current_sap_num)
            api_id = price_list["id"]

            price, uom_entry = self._fetch_price(api_id, item_code)

            if price is not None and price > 0:
                result = {
                    "item_code":       item_code,
                    "price":           price,
                    "currency":        "KES",
                    "uom_entry":       uom_entry,
                    "is_gross_price":  price_list.get("isGrossPrc") == "Y",
                    "price_list_id":   api_id,
                    "price_list_name": price_list.get("ListName", ""),
                    "sap_list_num":    current_sap_num,
                    "chain_walked":    chain_walked,
                    "found":           True,
                    "note":            f"Found on list '{price_list.get('ListName')}' "
                                       f"(SAP {current_sap_num})",
                }
                # Cache result
                if use_cache:
                    cache = get_cache_service()
                    cache.set_simple(f"price:{item_code}:{sap_list_num}", result, ttl=PRICE_CACHE_TTL)
                return result

            # price = 0 or None → try base list
            base_sap_num = price_list.get("BASE_NUM")

            if not base_sap_num or base_sap_num <= 0 or base_sap_num == current_sap_num:
                # No further chaining possible (also guards against BASE_NUM=-1)
                break

            logger.info(
                f"  {item_code}: price=0 on SAP list {current_sap_num} "
                f"→ following chain to SAP list {base_sap_num}"
            )
            current_sap_num = base_sap_num

        # Nothing found after walking the full chain
        note = (
            f"No price found for {item_code}. "
            f"Lists tried (SAP ListNum): {chain_walked}"
        )
        logger.warning(note)
        result = {
            "item_code":       item_code,
            "price":           None,
            "currency":        "KES",
            "uom_entry":       None,
            "is_gross_price":  False,
            "price_list_id":   None,
            "price_list_name": "",
            "sap_list_num":    sap_list_num,
            "chain_walked":    chain_walked,
            "found":           False,
            "note":            note,
        }
        
        # Cache even not-found results to avoid repeated lookups (shorter TTL)
        if use_cache:
            cache = get_cache_service()
            cache.set_simple(f"price:{item_code}:{sap_list_num}", result, ttl=300)  # 5 min for not-found
        
        return result

    async def get_price_async(
        self,
        item_code: str,
        sap_list_num: int = DEFAULT_SAP_LIST_NUM,
        use_cache: bool = True,
    ) -> Dict:
        """
        Async version of get_price.
        """
        return await asyncio.to_thread(
            self.get_price, item_code, sap_list_num, use_cache
        )

    def get_price_any_list(
        self,
        item_code: str,
        use_cache: bool = True,
    ) -> Dict:
        """
        Try all known price lists and return the first non-zero price found.

        - Price > 0 on any list  → return it immediately
        - Price = 0 on any list  → item registered but unpriced; note it and continue
        - Item absent from list  → try next list
        Avoids recursive get_price() calls — uses _fetch_price directly.
        """
        if not self._ensure_auth():
            return {
                "found": False,
                "item_code": item_code,
                "price": None,
                "note": "Authentication required for price lookup"
            }
        
        # Check cache first
        if use_cache:
            cache = get_cache_service()
            cache_key = f"price_any:{item_code}"
            cached = cache.get_simple(cache_key)
            if cached is not None:
                self._record_cache_hit()
                logger.info(f"📦 Price_any cache hit: {item_code}")
                return cached
        
        self._record_cache_miss()
        
        registered_on: Optional[str] = None

        for sap_num in sorted(self._list_by_sap_num.keys()):
            pl     = self._list_by_sap_num[sap_num]
            api_id = self._to_int(pl.get('id'))
            if not api_id:
                continue

            # Skip broken non-EA lists (api_ids 23-34 all return 500)
            # Their EA equivalents are covered by the EA list entries
            if api_id >= 23:
                continue

            price, uom_entry = self._fetch_price(api_id, item_code)

            if price is None:
                continue  # item absent from this list

            if price > 0:
                result = {
                    "item_code":       item_code,
                    "price":           price,
                    "currency":        "KES",
                    "uom_entry":       uom_entry,
                    "is_gross_price":  pl.get("isGrossPrc") == "Y",
                    "price_list_id":   api_id,
                    "price_list_name": pl.get("ListName", ""),
                    "sap_list_num":    sap_num,
                    "chain_walked":    [sap_num],
                    "found":           True,
                    "note":            f"Found on list {sap_num}: {pl.get('ListName', '')}",
                }
                # Cache result
                if use_cache:
                    cache = get_cache_service()
                    cache.set_simple(f"price_any:{item_code}", result, ttl=PRICE_CACHE_TTL)
                return result

            # price == 0: item is registered but unpriced on this list
            if registered_on is None:
                registered_on = pl.get('ListName', f'SAP {sap_num}')
                logger.info(
                    f'  get_price_any_list: {item_code} registered but '
                    f'price=0 on {registered_on!r}'
                )

        if registered_on:
            note = (
                f'{item_code} exists in the system but has no price set '
                f'(likely an internal or inactive item).'
            )
        else:
            note = (
                f'No price data found for {item_code} on any of the '
                f'{len(self._list_by_sap_num)} price lists.'
            )

        logger.warning(f'  get_price_any_list: {note}')
        result = {
            "item_code":       item_code,
            "price":           None,
            "currency":        "KES",
            "uom_entry":       None,
            "is_gross_price":  False,
            "price_list_id":   None,
            "price_list_name": registered_on or "",
            "sap_list_num":    0,
            "chain_walked":    [],
            "found":           False,
            "note":            note,
        }
        
        # Cache even not-found results
        if use_cache:
            cache = get_cache_service()
            cache.set_simple(f"price_any:{item_code}", result, ttl=300)  # 5 min for not-found
        
        return result

    def get_prices_batch(
        self,
        item_codes: List[str],
        sap_list_num: int = DEFAULT_SAP_LIST_NUM,
    ) -> Dict[str, Dict]:
        """
        Fetch prices for multiple items efficiently.
        
        Returns a dict mapping item_code → price result.
        """
        if not self._ensure_auth():
            return {code: {"found": False, "error": "Authentication required"} for code in item_codes}
        
        if not item_codes:
            return {}
        
        results = {}
        cache = get_cache_service()
        
        # First, try to get from cache
        uncached = []
        for item_code in item_codes:
            cache_key = f"price:{item_code}:{sap_list_num}"
            cached = cache.get_simple(cache_key)
            if cached is not None:
                results[item_code] = cached
            else:
                uncached.append(item_code)
        
        # Fetch uncached items
        for item_code in uncached:
            try:
                results[item_code] = self.get_price(
                    item_code=item_code,
                    sap_list_num=sap_list_num,
                    use_cache=True
                )
            except Exception as e:
                logger.error(f"Batch pricing error for {item_code}: {e}")
                results[item_code] = {"error": True, "message": str(e)}
        
        return results

    def get_all_price_lists(self, force_refresh: bool = False) -> List[Dict]:
        """Return the cached list of all price lists (sorted by SAP ListNum)."""
        # Check if cache needs refresh
        if force_refresh or (time.time() - self._price_list_cache_time > self._price_list_cache_ttl):
            self._build_maps()
            self._price_list_cache_time = time.time()
        
        return sorted(self._list_by_sap_num.values(), key=lambda x: x.get("ListNum", 0))

    def refresh(self):
        """Force a reload of the price list map from the API."""
        if not self._ensure_auth():
            logger.warning("Cannot refresh price lists - no authentication")
            return
        self._build_maps()
        self._price_list_cache_time = time.time()
        logger.info("Price list cache refreshed")

    def clear_cache(self):
        """Clear the price cache."""
        cache = get_cache_service()
        # Clear price-related cache keys
        # This would need pattern deletion - for now just log
        logger.info("Price cache clear requested (implementation depends on cache backend)")

    # ------------------------------------------------------------------
    # INTERNAL — PRICE LIST MAP
    # ------------------------------------------------------------------

    def _build_maps(self):
        """
        Fetch all price lists and build two lookup dicts:
          sap_list_num → price_list_dict
          api_id       → price_list_dict
        """
        if not self._ensure_auth():
            logger.warning("Cannot build price lists - no authentication")
            return
        
        try:
            self._record_api_call()
            url = f"{self.base_url}/price_lists"
            logger.debug(f"Fetching price lists from: {url}")
            
            resp = self.session.get(
                url,
                timeout=15,
            )
            
            # Check for HTML response (auth failure or wrong URL)
            response_text = resp.text[:50] if resp.text else ""
            if "<!DOCTYPE" in response_text or "<html" in response_text.lower():
                logger.error(f"Pricing endpoint returned HTML — likely auth failure or wrong URL: {url}")
                logger.error(f"Response preview: {response_text}")
                return
            
            # Check for auth failure
            if resp.status_code == 401:
                logger.error("Authentication failed while fetching price lists")
                return
            
            resp.raise_for_status()
            raw = resp.json()

            records = raw.get("ResponseData") or raw.get("responseData") or []
            if isinstance(records, dict):
                records = records.get("data", [])

            self._list_by_sap_num = {}
            self._list_by_api_id  = {}

            for pl in records:
                # ListNum is stored as a string in the API ("17", "18" …)
                sap_num = self._to_int(pl.get("ListNum"))
                api_id  = self._to_int(pl.get("id"))

                if sap_num is not None:
                    self._list_by_sap_num[sap_num] = pl
                if api_id is not None:
                    self._list_by_api_id[api_id] = pl

            # Log full map so we can debug ListNum→api_id mismatches
            mapping = {
                sap_num: pl.get('id')
                for sap_num, pl in self._list_by_sap_num.items()
            }
            logger.info(
                f"PricingService: loaded {len(self._list_by_sap_num)} price lists. "
                f"SAP ListNum→API id map: {mapping}"
            )

        except Exception as e:
            self._record_error()
            logger.error(f"PricingService: failed to build price list map: {e}")

    # ------------------------------------------------------------------
    # INTERNAL — PRICE FETCH
    # ------------------------------------------------------------------

    @lru_cache(maxsize=2048)
    def _fetch_price(
        self,
        api_price_list_id: int,
        item_code: str,
    ) -> Tuple[Optional[float], Optional[int]]:
        """
        Fetch the price of item_code from a price list (by API id).

        Returns (price, uom_entry) or (None, None) on failure.
        """
        if not self._ensure_auth():
            return None, None
        
        try:
            self._record_api_call()
            url = f"{self.base_url}/item/base-prices/price-list/{api_price_list_id}"
            params = {"search": item_code, "per_page": 50}

            resp = self.session.get(url, params=params, timeout=PRICE_LIST_SEARCH_TIMEOUT)

            # Check for auth failure
            if resp.status_code == 401:
                logger.error("Authentication failed during price fetch")
                return None, None

            # 500 on certain price list IDs means the list exists in metadata
            # but has no usable data endpoint — skip it gracefully
            if resp.status_code == 500:
                logger.warning(
                    f"  _fetch_price: api_list={api_price_list_id} returned 500 "
                    f"(list may be empty or unsupported) — skipping"
                )
                return None, None

            resp.raise_for_status()
            raw = resp.json()

            records = raw.get("ResponseData") or raw.get("responseData") or []
            if isinstance(records, dict):
                records = records.get("data", [])

            for rec in records:
                if rec.get("ItemCode") == item_code:
                    price = self._extract_price(rec)
                    uom_entry = rec.get("UomEntry")
                    logger.info(
                        f"  _fetch_price: {item_code} | api_list={api_price_list_id} "
                        f"| price={price} | uom_entry={uom_entry}"
                    )
                    return price, uom_entry

            # Item not in this list at all
            logger.info(
                f"  _fetch_price: {item_code} not found in api_list={api_price_list_id}"
            )
            return None, None

        except Exception as e:
            self._record_error()
            logger.error(
                f"  _fetch_price error: list={api_price_list_id} item={item_code}: {e}"
            )
            return None, None

    # ------------------------------------------------------------------
    # INTERNAL — HELPERS
    # ------------------------------------------------------------------

    def _customer_list_num(self, customer: Dict) -> int:
        """
        Extract the SAP price list number from a customer dict.

        Priority:
          1. customer["PriceListNum"]      (direct, often null)
          2. customer["octg"]["ListNum"]   (from payment group — reliable)
          3. DEFAULT_SAP_LIST_NUM
        """
        direct = self._to_int(customer.get("PriceListNum"))
        if direct:
            return direct

        octg = customer.get("octg") or {}
        from_octg = self._to_int(octg.get("ListNum"))
        if from_octg:
            return from_octg

        logger.debug(
            f"Customer '{customer.get('CardName')}' has no price list — "
            f"using default SAP list {DEFAULT_SAP_LIST_NUM}"
        )
        return DEFAULT_SAP_LIST_NUM

    @staticmethod
    def _extract_price(record: Dict) -> Optional[float]:
        """
        Extract a numeric price from a record, checking known field names.
        Returns None only if ALL price fields are absent (not set in DB).
        Returns 0.0 if the field exists but is zero (caller interprets as unpriced).
        """
        for field in ("Price", "BasePrice", "UnitPrice", "ItemPrice"):
            val = record.get(field)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _to_int(value) -> Optional[int]:
        """Safely coerce a value to int (handles string "17", float 1.0, None)."""
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


# ---------------------------------------------------------------------------
# IMPORTANT: No singleton instance for Phase 1
# Each request creates its own instance with user token and company code
# ---------------------------------------------------------------------------

def create_pricing_service(user_token: str = None, company_code: str = None) -> PricingService:
    """
    Create a new pricing service instance with the user's token and company code.
    This should be called for each request.
    
    Args:
        user_token: The authenticated user's Bearer token
        company_code: Company code for multi-tenant URL resolution
    
    Returns:
        Configured PricingService instance
    """
    if not user_token:
        logger.warning("Creating pricing service without user token - lookups will fail")
    if not company_code:
        logger.warning("Creating pricing service without company_code - will use global URL")
    return PricingService(user_token=user_token, company_code=company_code)


# Legacy function - will be deprecated
def get_pricing_service() -> PricingService:
    """
    LEGACY: Returns singleton instance WITHOUT user token or company code.
    This will cause authentication errors.
    
    Use create_pricing_service(user_token, company_code) instead.
    """
    logger.warning("Using legacy get_pricing_service() without user token/company - this will fail")
    return PricingService()  # No token, no company - will fail