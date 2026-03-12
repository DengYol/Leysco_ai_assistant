import requests
import logging
from typing import List, Dict, Optional, Any
from app.core.config import settings
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

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


class LeyscoAPIService:
    """
    Service to interact with Leysco Sales System APIs
    AI-Optimized Version with Endpoint Discovery
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

    # Status mapping for documents
    DOC_STATUS_MAP = {
        "open": 1,
        "closed": 2,
        "pending": 1,
        "completed": 2,
        "all": None
    }

    # Common endpoint patterns for document creation.
    # Paths are RELATIVE to base_url (which already includes /api/v1).
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

    # Known working POST endpoint paths (relative to base_url).
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
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.timeout = 30
        
        # Cache for discovered endpoints
        self._endpoint_cache = {}
        self._last_discovery = None
        
        # Cache for customer lookups
        self._customer_cache = {}
        self._customer_cache_time = {}

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
    # RESPONSE NORMALIZER
    # -------------------------------------------------
    def _normalize(self, data):
        if not isinstance(data, dict):
            return data if isinstance(data, list) else []

        response_data = data.get("ResponseData") or data.get("responseData")

        if isinstance(response_data, dict):
            # Standard paginated: ResponseData.data
            records = response_data.get("data")
            if isinstance(records, list):
                return records

            # Inventory report: ResponseData.stocks.data
            stocks = response_data.get("stocks")
            if isinstance(stocks, dict):
                records = stocks.get("data")
                if isinstance(records, list):
                    return records

        if isinstance(response_data, list):
            return response_data

        if isinstance(data.get("data"), list):
            return data["data"]

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
    # CUSTOMER LOOKUP WITH CACHING
    # -------------------------------------------------
    def resolve_customer(self, customer_name: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Resolve customer name to full customer details with caching.
        Returns customer dict with CardCode, CardName, etc.
        """
        if not customer_name:
            return None
        
        # Clean the search term
        cleaned_name = clean_customer_search_term(customer_name)
        
        # Check cache first
        if use_cache and cleaned_name in self._customer_cache:
            cache_time = self._customer_cache_time.get(cleaned_name)
            if cache_time and (datetime.now() - cache_time) < timedelta(minutes=5):
                logger.info(f"📦 Using cached customer: {cleaned_name}")
                return self._customer_cache[cleaned_name]
        
        # Search for customer
        customers = self.get_customers(search=cleaned_name, limit=5)
        if not customers:
            logger.warning(f"⚠️ Customer '{customer_name}' not found")
            return None
        
        # Find best match
        best_match = None
        for customer in customers:
            card_name = customer.get("CardName", "").lower()
            # Exact match first
            if cleaned_name.lower() == card_name:
                best_match = customer
                break
            # Partial match
            if cleaned_name.lower() in card_name:
                if not best_match:
                    best_match = customer
                elif len(card_name) < len(best_match.get("CardName", "").lower()):
                    best_match = customer
        
        if not best_match:
            best_match = customers[0]
        
        # Cache the result
        if best_match and use_cache:
            self._customer_cache[cleaned_name] = best_match
            self._customer_cache_time[cleaned_name] = datetime.now()
            logger.info(f"✅ Cached customer: {cleaned_name} → {best_match.get('CardCode')}")
        
        return best_match

    # -------------------------------------------------
    # ENHANCED ENDPOINT DISCOVERY
    # -------------------------------------------------
    def _options_methods(self, url: str) -> List[str]:
        """
        Send OPTIONS to a URL and return the list of advertised methods.
        Returns an empty list (not None) on any failure or missing Allow header.
        NOTE: many SAP/Laravel proxies do NOT advertise POST in Allow even when
        POST works fine — callers must not treat an empty list as "POST blocked".
        """
        try:
            resp = self.session.options(url, timeout=5)
            if resp.status_code == 200:
                allow = resp.headers.get("Allow", "")
                if allow:
                    return [m.strip() for m in allow.split(",")]
        except Exception as e:
            logger.debug(f"OPTIONS request failed for {url}: {e}")
        return []

    def discover_endpoints(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Discover available API endpoints and their supported methods.
        Caches results for 1 hour to avoid repeated discovery calls.

        FIX: OPTIONS-based discovery is kept for information only.
             We no longer *gate* POST on the OPTIONS result because SAP B1 /
             Laravel API proxies commonly omit POST from the Allow header even
             when POST is fully supported.  Instead we fall back to the
             KNOWN_POST_ENDPOINTS list so that create_quotation() always has a
             URL to try.
        """
        # Check cache first
        if not force_refresh and self._endpoint_cache:
            cache_age = datetime.now() - self._last_discovery if self._last_discovery else timedelta(hours=1)
            if cache_age < timedelta(hours=1):
                logger.info("📦 Using cached endpoint discovery")
                return self._endpoint_cache

        logger.info("🔍 Discovering API endpoints...")
        discovery_result = {
            "quotations": {"get": None, "create": None, "supported_methods": [], "doc_type": 23},
            "orders": {"get": None, "create": None, "supported_methods": [], "doc_type": 17},
            "invoices": {"get": None, "create": None, "supported_methods": [], "doc_type": 13},
            "deliveries": {"get": None, "create": None, "supported_methods": [], "doc_type": 15},
            "documents": {"get": None, "create": None, "supported_methods": [], "available_endpoints": []},
            "customers": {"get": None, "create": None},
            "items": {"get": None},
        }

        # ----------------------------------------------------------
        # Step 1: confirm the known GET endpoints are reachable
        # ----------------------------------------------------------
        known_get_endpoints = {
            "quotations": "/marketing/docs/23",
            "orders": "/marketing/docs/17",
            "invoices": "/marketing/docs/13",
            "deliveries": "/marketing/docs/15",
            "customers": "/bp_masterdata",
            "items": "/item_masterdata",
        }

        for doc_type, endpoint in known_get_endpoints.items():
            try:
                url = f"{self.base_url}{endpoint}"
                resp = self.session.head(url, timeout=5, allow_redirects=True)
                if resp.status_code < 400:
                    discovery_result[doc_type]["get"] = endpoint
                    logger.info(f"✅ Found GET endpoint for {doc_type}: {endpoint}")

                    # OPTIONS is informational only — do NOT gate anything on it
                    methods = self._options_methods(url)
                    if methods:
                        discovery_result[doc_type]["supported_methods"] = methods
                        logger.info(f"   OPTIONS-advertised methods: {methods}")
                    else:
                        discovery_result[doc_type]["supported_methods"] = ["GET"]
            except Exception as e:
                logger.debug(f"Could not test {doc_type} endpoint {endpoint}: {e}")

        # ----------------------------------------------------------
        # Step 2: try to discover CREATE endpoints via OPTIONS
        # (informational — we fall back if nothing is found)
        # ----------------------------------------------------------
        for doc_type, patterns in self.ENDPOINT_PATTERNS.items():
            for pattern in patterns:
                if pattern in known_get_endpoints.values():
                    continue  # already handled above

                try:
                    url = f"{self.base_url}{pattern}"
                    methods = self._options_methods(url)

                    if "/documents/" in pattern:
                        discovery_result["documents"]["available_endpoints"].append({
                            "url": pattern,
                            "methods": methods
                        })
                        if "POST" in methods and not discovery_result["documents"]["create"]:
                            discovery_result["documents"]["create"] = pattern
                            discovery_result["documents"]["supported_methods"] = methods

                    if doc_type in discovery_result and "POST" in methods:
                        if not discovery_result[doc_type]["create"]:
                            discovery_result[doc_type]["create"] = pattern
                            discovery_result[doc_type]["supported_methods"] = methods
                            logger.info(f"✅ OPTIONS confirmed POST endpoint for {doc_type}: {pattern}")
                except Exception:
                    continue

        # ----------------------------------------------------------
        # Step 3 (FIX): hardcoded fallback for any doc type whose
        # create endpoint is still None after OPTIONS discovery.
        # We trust KNOWN_POST_ENDPOINTS because OPTIONS is unreliable
        # on this server stack.
        # ----------------------------------------------------------
        for doc_type, fallback_list in self.KNOWN_POST_ENDPOINTS.items():
            if discovery_result.get(doc_type, {}).get("create"):
                continue  # already found via OPTIONS — nothing to do

            logger.warning(
                f"⚠️ OPTIONS discovery found no POST endpoint for '{doc_type}'. "
                f"Falling back to hardcoded list."
            )
            for fallback_ep in fallback_list:
                discovery_result[doc_type]["create"] = fallback_ep
                logger.info(f"   Using hardcoded POST endpoint for {doc_type}: {fallback_ep}")
                break  # use the first one; create_quotation() will try them in order

        self._endpoint_cache = discovery_result
        self._last_discovery = datetime.now()
        return discovery_result

    def get_endpoint_for_document(self, doc_type: str, action: str = "get") -> Optional[str]:
        """
        Get the appropriate endpoint for a document type and action.
        """
        discovery = self.discover_endpoints()
        if doc_type in discovery:
            return discovery[doc_type].get(action)
        return None

    def check_endpoint_supports_post(self, endpoint: str) -> bool:
        """
        Check if an endpoint supports POST requests.

        FIX: This method previously returned False when the server did not
        advertise POST in the Allow header, which blocked valid endpoints.
        We now return True optimistically and let the actual POST attempt
        surface any real 405 errors.
        """
        try:
            url = f"{self.base_url}{endpoint}"
            resp = self.session.options(url, timeout=5)
            if resp.status_code == 200:
                allow = resp.headers.get("Allow", "")
                if allow:
                    # Only return False when the server *explicitly* excludes POST
                    if "POST" in allow:
                        return True
                    # Allow header present but POST missing — still try optimistically
                    logger.debug(
                        f"OPTIONS for {endpoint} returned Allow: {allow!r} "
                        f"(no POST listed). Will attempt POST anyway."
                    )
                    return True
        except Exception as e:
            logger.debug(f"Could not OPTIONS-check endpoint {endpoint}: {e}")
        # No OPTIONS response — attempt POST optimistically
        return True

    # -------------------------------------------------
    # ENHANCED CUSTOMER ORDERS METHOD
    # -------------------------------------------------
    def get_customer_orders(
        self,
        customer_name: str,
        limit: Optional[int] = 25,
        doc_status: Optional[str] = "open",
        include_details: bool = True
    ) -> List[Dict]:
        try:
            logger.info(f"📋 Fetching sales orders for customer: {customer_name}")
            
            customer = self.resolve_customer(customer_name)
            if not customer:
                logger.warning(f"⚠️ Customer '{customer_name}' not found")
                return []

            customer_code = customer.get("CardCode")
            customer_name_resolved = customer.get("CardName", customer_name)
            
            logger.info(f"✅ Resolved customer: {customer_name_resolved} ({customer_code})")

            status_value = self.DOC_STATUS_MAP.get(doc_status.lower()) if doc_status else None

            params = {
                "isDoc": 1,
                "page": 1,
                "per_page": min(limit, 100) if limit else 25,
                "CardCode": customer_code
            }
            
            if status_value is not None:
                params["DocStatus"] = status_value

            url = f"{self.base_url}/marketing/docs/17"
            logger.info(f"📤 Calling API: {url} with params: {params}")
            
            resp = self.session.get(url, params=params, timeout=20)
            self._debug_response("CUSTOMER SALES ORDERS", resp)
            
            if resp.status_code == 200:
                orders = self._normalize(resp.json())
                logger.info(f"✅ Found {len(orders)} orders for {customer_name_resolved}")
                
                enhanced_orders = []
                for order in orders[:limit] if limit else orders:
                    enhanced_order = {
                        "DocNum": order.get("DocNum") or order.get("doc_num"),
                        "DocEntry": order.get("DocEntry") or order.get("doc_entry"),
                        "DocDate": order.get("DocDate") or order.get("doc_date"),
                        "DocDueDate": order.get("DocDueDate") or order.get("doc_due_date"),
                        "DocTotal": float(order.get("DocTotal") or order.get("doc_total") or 0),
                        "DocCurrency": order.get("DocCurrency") or "KES",
                        "DocStatus": order.get("DocStatus") or order.get("doc_status"),
                        "StatusText": self._get_status_text(order.get("DocStatus")),
                        "CustomerName": customer_name_resolved,
                        "CustomerCode": customer_code,
                        "DocumentLines": order.get("DocumentLines", []) if include_details else [],
                        "LineCount": len(order.get("DocumentLines", [])),
                        "Comments": order.get("Comments", ""),
                    }
                    enhanced_orders.append(enhanced_order)
                
                return enhanced_orders
            else:
                logger.error(f"❌ API error: {resp.status_code} - {resp.text[:200]}")
                return []

        except Exception as e:
            logger.error(f"❌ Error fetching customer orders: {e}")
            return []

    # -------------------------------------------------
    # ENHANCED CUSTOMER QUOTATIONS METHOD
    # -------------------------------------------------
    def get_customer_quotations(
        self,
        customer_name: str,
        limit: int = 20,
        status: Optional[str] = None,
        include_details: bool = True
    ) -> List[Dict]:
        try:
            logger.info(f"📋 Fetching quotations for customer: {customer_name}")
            
            customer = self.resolve_customer(customer_name)
            if not customer:
                logger.warning(f"⚠️ Customer '{customer_name}' not found")
                return []

            card_code = customer.get("CardCode")
            customer_name_resolved = customer.get("CardName", customer_name)

            params = {
                "isDoc": 1,
                "page": 1,
                "per_page": min(limit, 100),
                "IsICT": "N",
                "CardCode": card_code
            }
            
            if status and status.lower() == "open":
                params["DocStatus"] = 1
            elif status and status.lower() == "closed":
                params["DocStatus"] = 2

            url = f"{self.base_url}/marketing/docs/23"
            logger.info(f"📤 Calling API: {url} with params: {params}")
            
            response = self.session.get(url, params=params, timeout=20)
            self._debug_response("CUSTOMER QUOTATIONS", response)
            
            if response.status_code == 200:
                quotations = self._normalize(response.json())
                logger.info(f"✅ Found {len(quotations)} quotations for {customer_name_resolved}")
                
                enhanced_quotations = []
                for quote in quotations[:limit]:
                    enhanced_quote = {
                        "DocNum": quote.get("DocNum") or quote.get("doc_num"),
                        "DocEntry": quote.get("DocEntry") or quote.get("doc_entry"),
                        "DocDate": quote.get("DocDate") or quote.get("doc_date"),
                        "DocDueDate": quote.get("DocDueDate") or quote.get("doc_due_date"),
                        "DocTotal": float(quote.get("DocTotal") or quote.get("doc_total") or 0),
                        "DocCurrency": quote.get("DocCurrency") or "KES",
                        "DocStatus": quote.get("DocStatus") or quote.get("doc_status"),
                        "StatusText": self._get_status_text(quote.get("DocStatus")),
                        "CustomerName": customer_name_resolved,
                        "CustomerCode": card_code,
                        "DocumentLines": quote.get("DocumentLines", []) if include_details else [],
                        "LineCount": len(quote.get("DocumentLines", [])),
                        "Comments": quote.get("Comments", ""),
                    }
                    enhanced_quotations.append(enhanced_quote)
                
                return enhanced_quotations
            else:
                logger.error(f"❌ API error: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"❌ Error fetching customer quotations: {e}")
            return []

    # -------------------------------------------------
    # GET ALL CUSTOMER DOCUMENTS
    # -------------------------------------------------
    def get_customer_documents(
        self,
        customer_name: str,
        doc_types: List[int] = None,
        limit_per_type: int = 10,
        include_details: bool = False
    ) -> Dict[str, List[Dict]]:
        if doc_types is None:
            doc_types = [17, 23, 13, 15]
        
        result = {}
        
        for doc_type in doc_types:
            type_name = self.DOC_TYPES.get(doc_type, f"Type {doc_type}")
            
            if doc_type == 17:
                docs = self.get_customer_orders(customer_name, limit_per_type, include_details=include_details)
            elif doc_type == 23:
                docs = self.get_customer_quotations(customer_name, limit_per_type, include_details=include_details)
            elif doc_type in [13, 15]:
                customer = self.resolve_customer(customer_name)
                if customer:
                    card_code = customer.get("CardCode")
                    docs = self.fetch_marketing_docs(card_code, doc_type)
                    enhanced_docs = []
                    for doc in docs[:limit_per_type]:
                        enhanced_docs.append({
                            "DocNum": doc.get("DocNum"),
                            "DocDate": doc.get("DocDate"),
                            "DocTotal": float(doc.get("DocTotal", 0)),
                            "CustomerName": customer.get("CardName"),
                            "CustomerCode": card_code,
                        })
                    docs = enhanced_docs
                else:
                    docs = []
            else:
                docs = []
            
            result[type_name] = docs
        
        return result

    # -------------------------------------------------
    # HELPER: Get Status Text
    # -------------------------------------------------
    def _get_status_text(self, status_code) -> str:
        if status_code in [1, "1", "bost_Open"]:
            return "Open"
        elif status_code in [2, "2", "bost_Close"]:
            return "Closed"
        elif status_code in [3, "3"]:
            return "Cancelled"
        else:
            return str(status_code) if status_code else "Unknown"

    # -------------------------------------------------
    # ENHANCED QUOTATION CREATION
    # -------------------------------------------------
    def create_quotation(self, quotation_data: dict) -> Dict[str, Any]:
        """
        Create a new quotation.

        FIX: No longer gates the POST attempt on check_endpoint_supports_post().
        Instead we try each known POST endpoint in order and surface the first
        successful response (2xx) or the last error.
        """
        # Resolve the create endpoint from discovery (which now always returns one)
        create_endpoint = self.get_endpoint_for_document("quotations", "create")

        # Also collect the full ordered fallback list in case the primary fails
        fallback_endpoints = list(self.KNOWN_POST_ENDPOINTS.get("quotations", []))

        # Ensure the discovered endpoint is first in the list
        if create_endpoint and create_endpoint not in fallback_endpoints:
            fallback_endpoints.insert(0, create_endpoint)
        elif create_endpoint:
            fallback_endpoints.remove(create_endpoint)
            fallback_endpoints.insert(0, create_endpoint)

        if not fallback_endpoints:
            logger.warning("⚠️ No POST endpoint available for quotations")
            return self._quotation_no_endpoint_response()

        # Prepare the payload once
        if "DocumentLines" not in quotation_data:
            quotation_data = self._format_quotation_for_api(quotation_data)

        if "metadata" not in quotation_data:
            quotation_data["metadata"] = {
                "source": "AI Assistant",
                "timestamp": datetime.now().isoformat()
            }

        last_error = None

        for endpoint in fallback_endpoints:
            url = f"{self.base_url}{endpoint}"
            logger.info(f"📤 Attempting quotation POST at {url}")

            try:
                resp = self.session.post(url, json=quotation_data, timeout=self.timeout)
                self._debug_response("CREATE QUOTATION", resp)

                if resp.status_code in [200, 201]:
                    response_data = resp.json()
                    return {
                        "success": True,
                        "data": response_data,
                        "endpoint_used": endpoint,
                        "DocNum": response_data.get("DocNum") or response_data.get("doc_num"),
                        "message": "Quotation created successfully"
                    }

                # 405 = this endpoint definitely doesn't support POST; try next
                if resp.status_code == 405:
                    logger.warning(f"   405 Method Not Allowed at {endpoint} — trying next")
                    last_error = f"405 from {endpoint}"
                    continue

                # Any other error — record it but try the next endpoint too
                try:
                    error_details = resp.json()
                except Exception:
                    error_details = resp.text[:500]

                last_error = {
                    "status": resp.status_code,
                    "endpoint": endpoint,
                    "details": error_details,
                }
                logger.warning(f"   {resp.status_code} from {endpoint}: {error_details}")

            except Exception as e:
                logger.error(f"   Exception POSTing to {endpoint}: {e}")
                last_error = str(e)
                continue

        # All endpoints exhausted
        logger.warning("⚠️ All POST endpoints failed for quotations")
        discovery = self.discover_endpoints()
        return {
            "success": False,
            "error": "Quotation creation via API is not available",
            "last_error": last_error,
            "tried_endpoints": fallback_endpoints,
            "supported_methods": discovery.get("quotations", {}).get("supported_methods", ["GET"]),
            "available_endpoints": discovery.get("documents", {}).get("available_endpoints", []),
            "web_interface_instructions": {
                "message": "Please create quotations through the web interface:",
                "steps": [
                    "1️⃣ Go to Sales → Quotations in the Leysco web application",
                    "2️⃣ Click 'New Quotation' button",
                    "3️⃣ Select customer and add items",
                    "4️⃣ Save and send to customer"
                ],
                "api_limitation": "The current API only supports viewing quotations (GET), not creating them (POST).",
                "contact_admin": "Contact your system administrator to enable quotation creation via API if needed."
            },
            "discovery_results": discovery.get("quotations", {})
        }

    def _quotation_no_endpoint_response(self) -> Dict[str, Any]:
        return {
            "success": False,
            "error": "No quotation creation endpoint configured",
            "web_interface_instructions": {
                "message": "Please create quotations through the web interface.",
            }
        }

    def _format_quotation_for_api(self, data: dict) -> dict:
        """Format quotation data to match expected API format."""
        formatted = {
            "CardCode": data.get("customer_code") or data.get("CardCode"),
            "DocDate": data.get("doc_date") or datetime.now().strftime("%Y-%m-%d"),
            "DocDueDate": data.get("valid_until") or (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            "Comments": data.get("comments", ""),
            "DocumentLines": [],
            "DocType": 23,
        }

        simplified = {
            "customerCode": data.get("customer_code") or data.get("CardCode"),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "validUntil": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            "notes": data.get("comments", ""),
            "items": [],
            "documentType": "QUOTATION"
        }

        for item in data.get("items", []):
            main_line = {
                "ItemCode": item.get("ItemCode") or item.get("item_code"),
                "ItemName": item.get("ItemName") or item.get("item_name"),
                "Quantity": float(item.get("Quantity") or item.get("quantity", 1)),
                "UnitPrice": float(item.get("Price") or item.get("price", 0)),
                "LineTotal": float(item.get("LineTotal") or
                                   (item.get("Quantity", 1) * item.get("Price", 0))),
                "WarehouseCode": item.get("Warehouse", "01"),
            }
            formatted["DocumentLines"].append(main_line)

            simplified_line = {
                "itemCode": item.get("ItemCode") or item.get("item_code"),
                "itemName": item.get("ItemName") or item.get("item_name"),
                "quantity": float(item.get("Quantity") or item.get("quantity", 1)),
                "price": float(item.get("Price") or item.get("price", 0)),
                "total": float(item.get("Quantity", 1) * item.get("Price", 0))
            }
            simplified["items"].append(simplified_line)

        return {
            "main": formatted,
            "simplified": simplified,
            "summary": {
                "customer_code": data.get("customer_code") or data.get("CardCode"),
                "item_count": len(data.get("items", [])),
                "total_amount": sum(
                    item.get("Quantity", 1) * item.get("Price", 0)
                    for item in data.get("items", [])
                ),
                "valid_until": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            }
        }

    # -------------------------------------------------
    # SALES ORDER CREATION
    # -------------------------------------------------
    def create_sales_order(self, order_data: dict) -> Dict[str, Any]:
        """Create a new sales order."""
        create_endpoint = self.get_endpoint_for_document("orders", "create")
        
        if create_endpoint:
            url = f"{self.base_url}{create_endpoint}"
            try:
                if "DocumentLines" not in order_data:
                    order_data = self._format_order_for_api(order_data)
                
                resp = self.session.post(url, json=order_data, timeout=self.timeout)
                if resp.status_code in [200, 201]:
                    return {"success": True, "data": resp.json()}
                return {"success": False, "error": f"API returned {resp.status_code}"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        return {
            "success": False,
            "error": "Sales order creation via API is not available",
            "web_interface": "Please create orders through Sales → Orders in the web interface"
        }

    def _format_order_for_api(self, data: dict) -> dict:
        return {
            "CardCode": data.get("customer_code"),
            "DocDate": datetime.now().strftime("%Y-%m-%d"),
            "DocDueDate": data.get("delivery_date", datetime.now().strftime("%Y-%m-%d")),
            "Comments": data.get("comments", ""),
            "DocumentLines": [
                {
                    "ItemCode": item.get("ItemCode"),
                    "Quantity": float(item.get("Quantity", 1)),
                    "UnitPrice": float(item.get("Price", 0)),
                    "WarehouseCode": item.get("Warehouse", "01"),
                }
                for item in data.get("items", [])
            ],
            "DocType": 17,
        }

    # -------------------------------------------------
    # AUTHENTICATION
    # -------------------------------------------------
    def login(self, username: str, password: str) -> bool:
        try:
            url = f"{self.base_url}/auth/login"
            payload = {"username": username, "password": password}
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            self._debug_response("LOGIN", resp)

            if resp.status_code == 200:
                data = resp.json()
                token = data.get("token") or data.get("access_token")
                if token:
                    self.headers["Authorization"] = f"Bearer {token}"
                    self.session.headers.update(self.headers)
                    logger.info("✅ Successfully authenticated with CRM")
                    return True
            logger.error(f"❌ Login failed: {resp.status_code}")
            return False
        except Exception as e:
            logger.error(f"❌ Login error: {e}")
            return False

    # -------------------------------------------------
    # CRM DASHBOARD ENDPOINTS
    # -------------------------------------------------
    def get_crm_data_summary(self, start_date: str, end_date: str) -> Dict[str, Any]:
        try:
            url = f"{self.base_url}/crm/data-summary"
            params = {"startdate": start_date, "enddate": end_date}
            resp = self.session.get(url, params=params, timeout=self.timeout)
            self._debug_response("CRM DATA SUMMARY", resp)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch CRM data summary: {e}")
            return {}

    def get_crm_time_series(self, start_date: str, end_date: str, granularity: str = "monthly") -> List[Dict]:
        try:
            url = f"{self.base_url}/crm/time-series"
            params = {"startdate": start_date, "enddate": end_date, "granularity": granularity}
            resp = self.session.get(url, params=params, timeout=self.timeout)
            self._debug_response("CRM TIME SERIES", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch CRM time series: {e}")
            return []

    def get_top_branches(self, start_date: str, end_date: str, limit: int = 10) -> List[Dict]:
        try:
            url = f"{self.base_url}/crm/top-branches"
            params = {"startdate": start_date, "enddate": end_date, "limit": limit}
            resp = self.session.get(url, params=params, timeout=self.timeout)
            self._debug_response("TOP BRANCHES", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch top branches: {e}")
            return []

    def get_top_salespersons(self, start_date: str, end_date: str, limit: int = 10) -> List[Dict]:
        try:
            url = f"{self.base_url}/crm/top-salespersons"
            params = {"startdate": start_date, "enddate": end_date, "limit": limit}
            resp = self.session.get(url, params=params, timeout=self.timeout)
            self._debug_response("TOP SALESPERSONS", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch top salespersons: {e}")
            return []

    def get_slow_products(self, page: int = 1, per_page: int = 10) -> List[Dict]:
        try:
            url = f"{self.base_url}/crm/slow-products"
            params = {"page": page, "per_page": per_page}
            resp = self.session.get(url, params=params, timeout=self.timeout)
            self._debug_response("SLOW PRODUCTS", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch slow products: {e}")
            return []

    def get_non_buying_customers(self, start_date: str, end_date: str, page: int = 1, per_page: int = 10) -> List[Dict]:
        try:
            url = f"{self.base_url}/crm/customers/non-buying"
            params = {"startdate": start_date, "enddate": end_date, "page": page, "per_page": per_page}
            resp = self.session.get(url, params=params, timeout=self.timeout)
            self._debug_response("NON-BUYING CUSTOMERS", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch non-buying customers: {e}")
            return []

    # -------------------------------------------------
    # ENHANCED MARKETING DOCS METHODS
    # -------------------------------------------------
    def get_document_by_id(self, doc_id: str, doc_type: Optional[int] = None) -> Optional[Dict]:
        try:
            url = f"{self.base_url}/marketing/docs/{doc_id}"
            params = {"isDoc": 1}
            if doc_type:
                params["docType"] = doc_type
            resp = self.session.get(url, params=params, timeout=self.timeout)
            self._debug_response(f"DOCUMENT {doc_id}", resp)
            if resp.status_code == 200:
                data = self._normalize(resp.json())
                return data[0] if data else None
            return None
        except Exception as e:
            logger.error(f"Failed to fetch document {doc_id}: {e}")
            return None

    def search_documents(self, doc_type: Optional[int] = None, date_from: Optional[str] = None,
                         date_to: Optional[str] = None, customer_code: Optional[str] = None,
                         status: Optional[int] = 1, page: int = 1, per_page: int = 20) -> List[Dict]:
        try:
            if doc_type:
                url = f"{self.base_url}/marketing/docs/{doc_type}"
            else:
                url = f"{self.base_url}/marketing/docs/search"

            params = {"isDoc": 1, "page": page, "per_page": per_page}
            if status is not None:
                params["DocStatus"] = status
            if date_from:
                params["FromDate"] = date_from
            if date_to:
                params["ToDate"] = date_to
            if customer_code:
                params["CardCode"] = customer_code

            resp = self.session.get(url, params=params, timeout=self.timeout)
            self._debug_response("DOCUMENT SEARCH", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to search documents: {e}")
            return []

    def get_document_types(self) -> Dict[int, str]:
        return self.DOC_TYPES

    def explore_document_type(self, doc_type: int) -> Dict[str, Any]:
        try:
            url = f"{self.base_url}/marketing/docs/{doc_type}"
            params = {"isDoc": 1, "page": 1, "per_page": 5}
            resp = self.session.get(url, params=params, timeout=self.timeout)
            result = {
                "doc_type": doc_type,
                "status_code": resp.status_code,
                "success": resp.status_code == 200,
                "sample_data": None,
            }
            if resp.status_code == 200:
                data = self._normalize(resp.json())
                result["sample_data"] = data[:2] if data else []
                result["count"] = len(data)
                if data and doc_type not in self.DOC_TYPES:
                    self.DOC_TYPES[doc_type] = f"Discovered Type {doc_type}"
            return result
        except Exception as e:
            logger.error(f"Failed to explore doc type {doc_type}: {e}")
            return {"doc_type": doc_type, "error": str(e), "success": False}

    # -------------------------------------------------
    # ENHANCED CUSTOMER METHODS
    # -------------------------------------------------
    def get_customers_paginated(self, page: int = 1, per_page: int = 20, search: str = "") -> Dict[str, Any]:
        try:
            url = f"{self.base_url}/getCustomers"
            params = {"page": page, "per_page": per_page}
            if search:
                params["search"] = clean_customer_search_term(search)
            resp = self.session.get(url, params=params, timeout=self.timeout)
            self._debug_response("CUSTOMERS PAGINATED", resp)
            resp.raise_for_status()
            data = resp.json()
            return {
                "data": self._normalize(data),
                "page": page,
                "per_page": per_page,
                "total": data.get("total", len(self._normalize(data))),
            }
        except Exception as e:
            logger.error(f"Failed to fetch paginated customers: {e}")
            return {"data": [], "page": page, "per_page": per_page, "total": 0}

    # -------------------------------------------------
    # ITEMS
    # -------------------------------------------------
    def get_items(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        try:
            url = f"{self.base_url}/item_masterdata"
            params = {"page": 1, "per_page": 50, "search": search}
            resp = self.session.get(url, params=params, timeout=15)
            self._debug_response("ITEMS", resp)
            resp.raise_for_status()
            return self._apply_limit(self._normalize(resp.json()), limit)
        except Exception as e:
            logger.error(f"Failed to fetch items: {e}")
            return []

    def get_item_by_name(self, name: str) -> Optional[Dict]:
        return self._match_by_name(
            self.get_items(search=name), name,
            ["ItemName", "ItemCode", "full_name"]
        )

    def get_item_by_code(self, item_code: str) -> Optional[Dict]:
        try:
            url = f"{self.base_url}/item_masterdata/{item_code}"
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                normalized = self._normalize(data)
                if normalized:
                    return normalized[0]
            return None
        except Exception as e:
            logger.error(f"Failed to fetch item by code {item_code}: {e}")
            return None

    def get_item_price(self, item_code: str, customer_name: str = None) -> Optional[Dict]:
        from app.services.pricing_service import PricingService
        pricing = PricingService()
        customer = self.get_customer_by_name(customer_name) if customer_name else None
        result = (
            pricing.get_price_for_customer(item_code=item_code, customer=customer)
            if customer
            else pricing.get_price(item_code=item_code)
        )
        return result if result and result.get("found") else None

    # -------------------------------------------------
    # CUSTOMERS
    # -------------------------------------------------
    def get_customers(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        try:
            cleaned_search = clean_customer_search_term(search)
            url = f"{self.base_url}/bp_masterdata"
            resp = self.session.get(url, params={"search": cleaned_search}, timeout=15)
            self._debug_response("CUSTOMERS", resp)
            resp.raise_for_status()
            return self._apply_limit(self._normalize(resp.json()), limit)
        except Exception as e:
            logger.error(f"Failed to fetch customers: {e}")
            return []

    def get_customer_by_name(self, name: str) -> Optional[Dict]:
        return self.resolve_customer(name)

    def get_customer_by_code(self, card_code: str) -> Optional[Dict]:
        try:
            url = f"{self.base_url}/bp_masterdata/{card_code}"
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                normalized = self._normalize(data)
                if normalized:
                    return normalized[0]
            return None
        except Exception as e:
            logger.error(f"Failed to fetch customer by code {card_code}: {e}")
            return None

    def get_all_customers(self, limit: int = 2000) -> list:
        try:
            url = f"{self.base_url}/bp_masterdata"
            params = {"page": 1, "per_page": limit, "search": ""}
            response = self.session.get(url, params=params, timeout=30)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch all customers: {response.text}")
                return []
            customers = [
                {"CardCode": c.get("CardCode"), "CardName": c.get("CardName")}
                for c in self._normalize(response.json())
                if c.get("CardName")
            ]
            logger.info(f"Loaded {len(customers)} customers for AI matching")
            return customers
        except Exception as e:
            logger.error(f"Customer list fetch failed: {e}")
            return []

    # -------------------------------------------------
    # PRICING & DISCOUNTS
    # -------------------------------------------------
    def get_discount_groups(self) -> List[Dict]:
        try:
            resp = self.session.get(f"{self.base_url}/DiscountGroup", timeout=15)
            self._debug_response("DISCOUNT GROUPS", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch discount groups: {e}")
            return []

    def get_volume_discount(self, item_code: str, qty: float) -> float:
        try:
            best = 0
            for g in self.get_discount_groups():
                if g.get("ItemCode") == item_code:
                    min_qty = float(g.get("MinQty", 0))
                    disc = float(g.get("DiscountPercent", 0))
                    if qty >= min_qty and disc > best:
                        best = disc
            return best
        except Exception as e:
            logger.error(f"Volume discount calc failed: {e}")
            return 0

    def get_promo_price(self, item_code: str) -> Optional[Dict]:
        try:
            resp = self.session.get(f"{self.base_url}/promo-items", timeout=15)
            self._debug_response("PROMO ITEMS", resp)
            resp.raise_for_status()
            promos = self._normalize(resp.json())
            for p in promos:
                if p.get("ItemCode") == item_code:
                    return p
            return None
        except Exception as e:
            logger.error(f"Promo fetch failed: {e}")
            return None

    def get_price_lists(self) -> List[Dict]:
        try:
            resp = self.session.get(f"{self.base_url}/price_lists", timeout=15)
            self._debug_response("PRICE LISTS", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch price lists: {e}")
            return []

    def get_price_history(self, item_code: str, days: int = 180) -> List[Dict]:
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            url = f"{self.base_url}/price_history"
            params = {
                "ItemCode": item_code,
                "FromDate": start_date.strftime("%Y-%m-%d"),
                "ToDate": end_date.strftime("%Y-%m-%d"),
            }
            resp = self.session.get(url, params=params, timeout=20)
            self._debug_response("PRICE HISTORY", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch price history for {item_code}: {e}")
            return []

    # -------------------------------------------------
    # CURRENCY & MISC
    # -------------------------------------------------
    def get_currency_rates(self) -> List[Dict]:
        try:
            resp = self.session.get(f"{self.base_url}/currency", timeout=15)
            self._debug_response("CURRENCY", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Currency fetch failed: {e}")
            return []

    def get_item_groups(self) -> List[Dict]:
        try:
            resp = self.session.get(f"{self.base_url}/itemgroup", timeout=15)
            self._debug_response("ITEM GROUPS", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Item group fetch failed: {e}")
            return []

    def get_uoms(self) -> List[Dict]:
        try:
            resp = self.session.get(f"{self.base_url}/uoms", timeout=15)
            self._debug_response("UOMS", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch UOMs: {e}")
            return []

    # -------------------------------------------------
    # MARKETING DOCUMENTS
    # -------------------------------------------------
    def fetch_marketing_docs(self, card_code: str, doc_type: int) -> List[Dict]:
        try:
            url = f"{self.base_url}/marketing/docs/{doc_type}"
            params = {"isDoc": 1, "page": 1, "per_page": 5, "CardCode": card_code}
            resp = self.session.get(url, params=params, timeout=20)
            self._debug_response("MARKETING DOCS", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Marketing docs fetch failed: {e}")
            return []

    def get_customer_activity_summary(self, card_code: str) -> dict:
        return {
            "invoices": self.fetch_marketing_docs(card_code, 13) or [],
            "deliveries": self.fetch_marketing_docs(card_code, 15) or [],
            "quotations": self.fetch_marketing_docs(card_code, 23) or [],
        }

    def calculate_engagement_level(self, summary: dict) -> str:
        total = sum(len(summary.get(k, [])) for k in ["invoices", "deliveries", "quotations"])
        if total >= 10: return "🔥 Very Active"
        if total >= 5:  return "✅ Active"
        if total >= 1:  return "⚠ Low Activity"
        return "❄ Dormant"

    def get_orders(self, customer_code: str, limit: int = 10) -> dict:
        try:
            url = f"{self.base_url}/marketing/docs/17"
            params = {"isDoc": 1, "CardCode": customer_code, "page": 1, "per_page": limit}
            response = self.session.get(url, params=params, timeout=30)
            self._debug_response("ORDERS", response)

            if response.status_code == 200:
                normalized_data = self._normalize(response.json())
                return {
                    "ResultState": True,
                    "ResultCode": 1200,
                    "ResultDesc": "Operation Was Successful",
                    "ResponseData": normalized_data[:limit] if normalized_data else [],
                }
            return {
                "ResultState": False,
                "ResultCode": response.status_code,
                "ResultDesc": f"Error: {response.status_code}",
                "ResponseData": [],
            }
        except Exception as e:
            logger.error(f"Exception in get_orders: {e}")
            return {"ResultState": False, "ResultCode": 500, "ResultDesc": f"Exception: {e}", "ResponseData": []}

    def get_outstanding_deliveries(self, customer_name: str, limit: Optional[int] = 25) -> List[Dict]:
        try:
            logger.info(f"Fetching outstanding deliveries for {customer_name}")
            customers = self.get_customers(search=customer_name)
            if not customers:
                return []

            card_code = customers[0].get("CardCode")
            params = {"isDoc": 1, "page": 1, "per_page": 50, "CardCode": card_code, "DocStatus": 1}
            url = f"{self.base_url}/marketing/docs/15"
            resp = self.session.get(url, params=params, timeout=20)
            self._debug_response("OUTSTANDING DELIVERIES", resp)
            resp.raise_for_status()

            deliveries = self._normalize(resp.json())
            outstanding = []
            for d in deliveries:
                lines = d.get("DocumentLines") or d.get("document_lines") or []
                for line in lines:
                    if float(line.get("DeliveredQty", 0)) < float(line.get("Quantity", 0)):
                        outstanding.append(d)
                        break
                else:
                    if not lines:
                        outstanding.append(d)

            return self._apply_limit(outstanding, limit)
        except Exception as e:
            logger.error(f"Outstanding delivery fetch failed: {e}")
            return []

    # -------------------------------------------------
    # WAREHOUSES & INVENTORY
    # -------------------------------------------------
    def get_warehouses(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        try:
            resp = self.session.get(f"{self.base_url}/warehouse", timeout=15)
            self._debug_response("WAREHOUSES", resp)
            resp.raise_for_status()
            warehouses = self._normalize(resp.json())
            if search:
                warehouses = [w for w in warehouses if search.lower() in str(w.get("WhsName", "")).lower()]
            return self._apply_limit(warehouses, limit)
        except Exception as e:
            logger.error(f"Failed to fetch warehouses: {e}")
            return []

    def get_warehouse_by_code(self, whs_code: str) -> Optional[Dict]:
        try:
            warehouses = self.get_warehouses(search=whs_code)
            for wh in warehouses:
                if wh.get("WhsCode") == whs_code:
                    return wh
            return None
        except Exception as e:
            logger.error(f"Failed to fetch warehouse by code {whs_code}: {e}")
            return None

    def get_inventory_report(self, search: str = "", limit: Optional[int] = None) -> List[Dict]:
        try:
            params = {"page": 1, "per_page": 100, "search": search}
            resp = self.session.get(f"{self.base_url}/inventory/report", params=params, timeout=15)
            self._debug_response("INVENTORY REPORT", resp)
            resp.raise_for_status()
            return self._apply_limit(self._normalize(resp.json()), limit)
        except Exception as e:
            logger.error(f"Failed to fetch inventory report: {e}")
            return []

    def get_inventory_by_item(self, item_code: str) -> List[Dict]:
        try:
            inventory = self.get_inventory_report(search=item_code)
            return [item for item in inventory if item.get("ItemCode") == item_code]
        except Exception as e:
            logger.error(f"Failed to fetch inventory for item {item_code}: {e}")
            return []

    def get_inventory_turnover(self, warehouse_code: Optional[str] = None) -> List[Dict]:
        try:
            url = f"{self.base_url}/inventory/turnover"
            params = {}
            if warehouse_code:
                params["Warehouse"] = warehouse_code
            resp = self.session.get(url, params=params, timeout=20)
            self._debug_response("INVENTORY TURNOVER", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch inventory turnover: {e}")
            return []

    def get_stock_by_warehouse(self, warehouse: str, item_name: Optional[str] = None) -> Dict:
        try:
            params = {"warehouse": warehouse}
            if item_name:
                params["search"] = item_name
            resp = self.session.get(f"{self.base_url}/inventory_stock", params=params, timeout=15)
            self._debug_response("WAREHOUSE STOCK", resp)
            resp.raise_for_status()
            data = self._normalize(resp.json())
            if not data:
                return {"message": f"No stock found in {warehouse}"}
            return {"data": data}
        except Exception as e:
            logger.error(f"Warehouse stock error: {e}")
            return {"error": str(e)}

    # -------------------------------------------------
    # SALES ANALYSIS & INTELLIGENCE
    # -------------------------------------------------
    def get_sales_history(self, item_code: str, days: int = 90) -> List[Dict]:
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            url = f"{self.base_url}/sales_analysis"
            params = {
                "ItemCode": item_code,
                "FromDate": start_date.strftime("%Y-%m-%d"),
                "ToDate": end_date.strftime("%Y-%m-%d"),
                "page": 1,
                "per_page": 100,
            }
            resp = self.session.get(url, params=params, timeout=20)
            self._debug_response("SALES HISTORY", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch sales history for {item_code}: {e}")
            return []

    def get_top_selling_items(self, limit: int = 50, days: int = 30) -> List[Dict]:
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            url = f"{self.base_url}/sales_analysis/top_items"
            params = {
                "FromDate": start_date.strftime("%Y-%m-%d"),
                "ToDate": end_date.strftime("%Y-%m-%d"),
                "limit": limit,
            }
            resp = self.session.get(url, params=params, timeout=20)
            self._debug_response("TOP SELLING ITEMS", resp)
            if resp.status_code == 200:
                return self._normalize(resp.json())
            return self._get_top_selling_fallback(limit)
        except Exception as e:
            logger.error(f"Failed to fetch top selling items: {e}")
            return self._get_top_selling_fallback(limit)

    def _get_top_selling_fallback(self, limit: int = 20) -> List[Dict]:
        try:
            inventory = self.get_inventory_report(limit=200)
            scored_items = []
            for item in inventory:
                on_hand = float(item.get("CurrentOnHand", item.get("OnHand", 0)) or 0)
                committed = float(item.get("CurrentIsCommited", item.get("IsCommited", 0)) or 0)
                popularity = committed / on_hand if on_hand > 0 and committed > 0 else 0
                scored_items.append({
                    "ItemCode": item.get("ItemCode"),
                    "ItemName": item.get("ItemName"),
                    "OnHand": on_hand,
                    "Committed": committed,
                    "PopularityScore": popularity,
                    "Category": "Fallback Estimate"
                })
            scored_items.sort(key=lambda x: x["PopularityScore"], reverse=True)
            logger.info(f"Generated {min(limit, len(scored_items))} top items from fallback")
            return scored_items[:limit]
        except Exception as e:
            logger.error(f"Fallback top selling calculation failed: {e}")
            return []

    # -------------------------------------------------
    # CUSTOMER INTELLIGENCE
    # -------------------------------------------------
    def get_customer_segments(self) -> List[Dict]:
        try:
            resp = self.session.get(f"{self.base_url}/customer_segments", timeout=20)
            self._debug_response("CUSTOMER SEGMENTS", resp)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Failed to fetch customer segments: {e}")
            return []

    def get_customer_rfm_analysis(self, customer_code: str) -> Optional[Dict]:
        try:
            resp = self.session.get(f"{self.base_url}/customer_rfm/{customer_code}", timeout=20)
            self._debug_response("CUSTOMER RFM", resp)
            resp.raise_for_status()
            data = self._normalize(resp.json())
            return data[0] if data else None
        except Exception as e:
            logger.error(f"Failed to fetch RFM for {customer_code}: {e}")
            return None

    # =========================================================
    # 🆕 NEW: ENHANCED METHODS FOR RECOMMENDATIONS
    # =========================================================

    def get_cross_sell_data(self, item_code: str, limit: int = 5) -> List[Dict]:
        """
        Get items frequently bought together with the given item.
        This would analyze order history to find correlations.
        """
        try:
            logger.info(f"🔍 Fetching cross-sell data for: {item_code}")
            
            # This would query a dedicated cross-sell endpoint or analyze order patterns
            # For now, return empty list and let recommendation service use fallback
            # Example: You might have an endpoint like /analytics/cross-sell/{item_code}
            # url = f"{self.base_url}/analytics/cross-sell/{item_code}"
            # resp = self.session.get(url, params={"limit": limit}, timeout=15)
            # if resp.status_code == 200:
            #     return self._normalize(resp.json())
            
            # For now, use related items from same category as fallback
            item = self.get_item_by_code(item_code)
            if item:
                group = item.get("ItmsGrpCod")
                if group:
                    # Get items in same group
                    items = self.get_items(limit=limit * 2)
                    result = []
                    for itm in items:
                        if itm.get("ItemCode") != item_code and itm.get("ItmsGrpCod") == group:
                            result.append(itm)
                            if len(result) >= limit:
                                break
                    return result
            
            return []
        except Exception as e:
            logger.error(f"Failed to fetch cross-sell data: {e}")
            return []

    def get_upsell_data(self, item_code: str, limit: int = 3) -> List[Dict]:
        """
        Get premium/upgrade alternatives for an item.
        """
        try:
            logger.info(f"🔍 Fetching upsell data for: {item_code}")
            
            # Get the source item to determine its category/price range
            source_item = self.get_item_by_code(item_code)
            if not source_item:
                return []
            
            # Try to get price for source item
            source_price_info = self.get_item_price(item_code)
            source_price = source_price_info.get("price", 0) if source_price_info else 0
            
            # Find items in same group with higher price
            group = source_item.get("ItmsGrpCod")
            if group:
                # Get all items in same group
                all_items = self.get_items(limit=50)
                candidates = []
                for item in all_items:
                    if item.get("ItemCode") != item_code and item.get("ItmsGrpCod") == group:
                        # Get price for this item
                        price_info = self.get_item_price(item.get("ItemCode"))
                        price = price_info.get("price", 0) if price_info else 0
                        if price > source_price:
                            item["Price"] = price
                            item["PriceDifference"] = price - source_price
                            candidates.append(item)
                
                # Sort by price (highest first) and return top ones
                candidates.sort(key=lambda x: x.get("Price", 0), reverse=True)
                return candidates[:limit]
            
            return []
        except Exception as e:
            logger.error(f"Failed to fetch upsell data: {e}")
            return []

    def get_seasonal_items(self, month: str = None, limit: int = 10) -> List[Dict]:
        """
        Get items that are seasonal or recommended for a specific month.
        """
        try:
            logger.info(f"🔍 Fetching seasonal items for: {month or 'current month'}")
            
            # This could query a seasonal products endpoint
            # url = f"{self.base_url}/analytics/seasonal"
            # params = {"month": month, "limit": limit}
            # resp = self.session.get(url, params=params, timeout=15)
            # if resp.status_code == 200:
            #     return self._normalize(resp.json())
            
            # For now, return trending items as fallback
            return self.get_trending_items(days=30, limit=limit)
            
        except Exception as e:
            logger.error(f"Failed to fetch seasonal items: {e}")
            return []

    def get_trending_items(self, days: int = 30, limit: int = 10) -> List[Dict]:
        """
        Get trending/popular items based on recent sales.
        """
        try:
            logger.info(f"🔍 Fetching trending items from last {days} days")
            
            # Use existing top-selling items method
            return self.get_top_selling_items(limit=limit, days=days)
            
        except Exception as e:
            logger.error(f"Failed to fetch trending items: {e}")
            return self._get_top_selling_fallback(limit)

    def get_customer_purchase_history(self, customer_code: str, limit: int = 50) -> List[Dict]:
        """
        Get detailed purchase history for a customer including line items.
        Useful for personalized recommendations.
        """
        try:
            logger.info(f"🔍 Fetching purchase history for customer: {customer_code}")
            
            # Get orders first
            orders = self.get_orders(customer_code, limit=limit)
            
            # If we have a proper response, extract line items
            if isinstance(orders, dict) and orders.get("ResultState"):
                order_data = orders.get("ResponseData", [])
                
                # For each order, we might need to fetch details to get line items
                # This could be optimized with a dedicated endpoint
                
                return order_data
            
            return []
        except Exception as e:
            logger.error(f"Failed to fetch customer purchase history: {e}")
            return []

    def get_items_by_category(self, category: str, limit: int = 20) -> List[Dict]:
        """
        Get items filtered by category/item group.
        """
        try:
            logger.info(f"🔍 Fetching items in category: {category}")
            
            # First, find the item group code for this category
            groups = self.get_item_groups()
            group_code = None
            for group in groups:
                if category.lower() in group.get("ItmsGrpNam", "").lower():
                    group_code = group.get("id")
                    break
            
            if group_code:
                url = f"{self.base_url}/item_masterdata"
                params = {"page": 1, "per_page": limit, "GroupCode": group_code}
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    return self._normalize(resp.json())
            
            # Fallback to search
            return self.get_items(search=category, limit=limit)
            
        except Exception as e:
            logger.error(f"Failed to fetch items by category: {e}")
            return []