"""
app/services/quotation_service.py
==================================
Service for creating sales quotations using Leysco Marketing Docs API
(SAP Object Type 23 = Sales Quotation)

FIX SUMMARY
-----------
1. _discover_quotation_endpoint(): no longer gates on OPTIONS/Allow header.
   Falls back to hardcoded KNOWN_POST_ENDPOINTS when OPTIONS returns nothing.
2. create_quotation(): removed check_endpoint_supports_post() pre-check.
   Now tries each known endpoint in order, moving on only on 405 or exception.
3. ENHANCED: Improved item validation to filter out packing materials.
4. ENHANCED: Added item search that prioritizes sellable items.
5. FIXED: Better response parsing for successful quotation creation.
6. ADDED: Formatted success message with item details, customer name, total, and validity.
7. UPDATED: Uses ResponseFormatter for consistent message formatting.
"""

import requests
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import json
import re

from app.ai_engine.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class QuotationService:
    """
    Create and manage sales quotations via Leysco Marketing Docs API.
    Sales Quotation = SAP Object Type 23
    """

    SAP_OBJECT_CODE = 23

    STATUS_MAP = {
        1: {"en": "Open",      "sw": "Funguliwa"},
        2: {"en": "Closed",    "sw": "Imefungwa"},
        3: {"en": "Cancelled", "sw": "Imeghairiwa"},
    }

    # Ordered list of POST endpoint *paths* to try when OPTIONS discovery fails.
    KNOWN_POST_ENDPOINTS = [
        "/documents/quotation",
        "/documents/quotations",
        "/quotations",
        "/sales/quotations",
        "/marketing/quotation",
        "/quotation/create",
    ]

    # Items to skip (packing materials, raw materials, etc.)
    SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL", "PACKAGING"}
    SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK", "PACK", "BAG", "BOX", "LABEL")
    SKIP_NAME_TERMS = ("LABEL", "PACK", "BAG", "BOX", "STICKER", "SLEEVE", "WRAPPER")

    def __init__(self, api_service):
        self.api = api_service
        self.base_url = api_service.base_url.rstrip("/")
        self.headers = api_service.headers
        self.timeout = api_service.timeout

        self._endpoint_cache = None
        self._endpoint_cache_time = None

    # ==========================================================
    # CACHE MANAGEMENT
    # ==========================================================
    def clear_cache(self):
        self._endpoint_cache = None
        self._endpoint_cache_time = None
        logger.info("🧹 Cleared quotation endpoint discovery cache")
        return True

    # ==========================================================
    # TOKEN/SESSION VALIDATION
    # ==========================================================
    def _is_login_page_response(self, response: requests.Response) -> bool:
        if response.status_code == 200 and 'text/html' in response.headers.get('Content-Type', ''):
            if 'Sign In' in response.text or 'login' in response.text.lower() or 'Welcome Back' in response.text:
                logger.warning("⚠️ Session expired - received login page redirect")
                return True
        return False

    def _check_response_auth(self, response: requests.Response, endpoint: str) -> bool:
        if self._is_login_page_response(response):
            logger.error(f"❌ Authentication failed for {endpoint} - session expired")
            return False
        return True

    # ==========================================================
    # ENHANCED ITEM SEARCH
    # ==========================================================
    def _find_sellable_item(self, search_term: str, limit: int = 20) -> Optional[Dict]:
        """
        Find a sellable item matching the search term.
        Skips packing materials, raw materials, and non-sellable items.
        Prioritizes items that are actually sellable (SellItem = Y).
        """
        try:
            items = self.api.get_items(search=search_term, limit=limit)
            
            if not items:
                return None
            
            # First pass: find sellable, non-packing items
            for item in items:
                item_code = item.get("ItemCode", "")
                item_name = item.get("ItemName", "")
                item_group = (item.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                is_sellable = item.get("SellItem") == "Y"
                
                # Check if it's a packing/raw material
                is_packing = (
                    item_group in self.SKIP_GROUPS or
                    any(item_code.startswith(p) for p in self.SKIP_PREFIXES) or
                    any(term in item_name.upper() for term in self.SKIP_NAME_TERMS)
                )
                
                if is_sellable and not is_packing:
                    logger.info(f"✅ Found sellable item: {item_name} ({item_code})")
                    return item
            
            # Second pass: find any sellable item (even if it might be packing)
            for item in items:
                if item.get("SellItem") == "Y":
                    logger.info(f"⚠️ Found sellable but possibly packing item: {item.get('ItemName')} ({item.get('ItemCode')})")
                    return item
            
            # No sellable items found
            logger.info(f"❌ No sellable items found for: {search_term}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding sellable item for '{search_term}': {e}")
            return None

    # ==========================================================
    # ENDPOINT DISCOVERY
    # ==========================================================
    def _discover_quotation_endpoint(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Discover the correct endpoint for quotation creation."""
        if not force_refresh and self._endpoint_cache and self._endpoint_cache_time:
            if (datetime.now() - self._endpoint_cache_time) < timedelta(hours=1):
                logger.info("📦 Using cached quotation endpoint discovery")
                return self._endpoint_cache

        logger.info("🔍 Discovering quotation endpoints...")

        if hasattr(self.api, 'discover_endpoints'):
            discovery = self.api.discover_endpoints(force_refresh)
            result = discovery.get("quotations", {})

            if "documents" in discovery and discovery["documents"].get("create"):
                if "/quotation" in discovery["documents"]["create"]:
                    result["documents_endpoint"] = discovery["documents"]["create"]
                    logger.info(f"📄 Found documents endpoint: {discovery['documents']['create']}")

            result["doc_type"] = 23
            result["doc_type_name"] = "Quotations"

            if not result.get("create"):
                result["create"] = f"{self.base_url}{self.KNOWN_POST_ENDPOINTS[0]}"
                result["_fallback_used"] = True
                logger.warning(f"⚠️ Using hardcoded fallback: {result['create']}")

            self._endpoint_cache = result
            self._endpoint_cache_time = datetime.now()
            return result

        # Manual discovery
        result = {
            "get": f"{self.base_url}/marketing/docs/23",
            "create": None,
            "documents_create": None,
            "supported_methods": ["GET"],
            "available_endpoints": [],
            "doc_type": 23,
            "doc_type_name": "Quotations"
        }

        for rel_endpoint in self.KNOWN_POST_ENDPOINTS:
            full_url = f"{self.base_url}{rel_endpoint}"
            try:
                resp = requests.options(full_url, headers=self.headers, timeout=5)

                if resp.status_code == 200 and 'text/html' in resp.headers.get('Content-Type', ''):
                    if 'Sign In' in resp.text or 'login' in resp.text:
                        logger.info(f"🔒 Endpoint exists but requires authentication: {full_url}")
                        result["available_endpoints"].append({
                            "url": rel_endpoint,
                            "auth_required": True,
                        })
                        continue

                if resp.status_code == 200:
                    allow = resp.headers.get('Allow', '')
                    methods = [m.strip() for m in allow.split(',')] if allow else []

                    endpoint_info = {"url": rel_endpoint, "methods": methods}

                    if "/documents/" in rel_endpoint:
                        endpoint_info["type"] = "documents"
                        if 'POST' in methods and not result["documents_create"]:
                            result["documents_create"] = full_url
                            logger.info(f"✅ OPTIONS confirmed POST documents endpoint: {full_url}")

                    result["available_endpoints"].append(endpoint_info)

                    if 'POST' in methods and not result["create"]:
                        result["create"] = full_url
                        result["supported_methods"] = methods
                        logger.info(f"✅ OPTIONS confirmed POST endpoint: {full_url}")

            except Exception as e:
                logger.debug(f"Could not OPTIONS-test {full_url}: {e}")
                continue

        if not result["create"] and result["documents_create"]:
            result["create"] = result["documents_create"]
            logger.info(f"📄 Using documents endpoint as primary: {result['documents_create']}")

        if not result["create"]:
            result["create"] = f"{self.base_url}{self.KNOWN_POST_ENDPOINTS[0]}"
            result["_fallback_used"] = True
            logger.warning(f"⚠️ Using hardcoded fallback: {result['create']}")

        self._endpoint_cache = result
        self._endpoint_cache_time = datetime.now()
        return result

    # ==========================================================
    # ENHANCED VALIDATE QUOTATION ITEMS
    # ==========================================================
    def _validate_quotation_items(self, items: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        """
        Validate quotation items.
        Enhanced to skip packing materials and non-sellable items.
        """
        valid_items = []
        invalid_items = []

        for idx, item in enumerate(items):
            item_code = item.get("ItemCode")
            item_name = item.get("ItemName", item_code)
            quantity  = item.get("Quantity", 1)
            price     = item.get("Price", 0)

            if not item_code:
                invalid_items.append({
                    "ItemCode": "Unknown", 
                    "ItemName": item_name,
                    "reason": "Missing item code", 
                    "index": idx
                })
                continue

            if quantity <= 0:
                invalid_items.append({
                    "ItemCode": item_code, 
                    "ItemName": item_name,
                    "reason": f"Invalid quantity: {quantity}", 
                    "index": idx
                })
                continue

            if price <= 0:
                invalid_items.append({
                    "ItemCode": item_code, 
                    "ItemName": item_name,
                    "reason": "Zero or negative price - cannot create quotation",
                    "index": idx
                })
                continue

            # Get full item details to check if sellable
            try:
                full_item = self.api.get_item_by_code(item_code)
                if full_item:
                    item_group = (full_item.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                    item_name_upper = full_item.get("ItemName", "").upper()
                    is_sellable = full_item.get("SellItem") == "Y"
                    
                    # Check if it's a packing/raw material
                    is_packing = (
                        item_group in self.SKIP_GROUPS or
                        any(item_code.startswith(p) for p in self.SKIP_PREFIXES) or
                        any(term in item_name_upper for term in self.SKIP_NAME_TERMS)
                    )
                    
                    if not is_sellable:
                        invalid_items.append({
                            "ItemCode": item_code, 
                            "ItemName": full_item.get("ItemName", item_name),
                            "reason": f"Item not sellable (SellItem = N)",
                            "index": idx
                        })
                        continue
                    
                    if is_packing:
                        invalid_items.append({
                            "ItemCode": item_code, 
                            "ItemName": full_item.get("ItemName", item_name),
                            "reason": f"Packing/raw material (Group: {item_group})",
                            "index": idx
                        })
                        continue
                        
            except Exception as e:
                logger.warning(f"⚠️ Could not validate item {item_code}: {e}")

            valid_items.append(item)

        return valid_items, invalid_items

    # ==========================================================
    # ENHANCED FORMAT QUOTATION FOR API
    # ==========================================================
    def _format_quotation_for_api(self, customer_code: str, items: List[Dict[str, Any]],
                                   comments: str = "", valid_until_days: int = 30) -> Dict[str, Any]:
        today       = datetime.now()
        valid_until = (today + timedelta(days=valid_until_days)).strftime("%Y-%m-%d")
        today_str   = today.strftime("%Y-%m-%d")

        total_amount = sum(item.get("Quantity", 1) * item.get("Price", 0) for item in items)
        comment_text = comments or f"Quotation created via AI Assistant on {today_str}"

        documents_format = {
            "CardCode":      customer_code,
            "DocDate":       today_str,
            "DocDueDate":    valid_until,
            "Comments":      comment_text,
            "DocumentLines": [
                {
                    "ItemCode":  item.get("ItemCode"),
                    "ItemName":  item.get("ItemName"),
                    "Quantity":  item.get("Quantity", 1),
                    "UnitPrice": item.get("Price", 0),
                }
                for item in items
            ],
        }

        sap_format = {
            "DocObjectCode": self.SAP_OBJECT_CODE,
            "CardCode":      customer_code,
            "DocDate":       today_str,
            "DocDueDate":    valid_until,
            "Comments":      comment_text,
            "DocumentLines": [
                {
                    "ItemCode":       item.get("ItemCode"),
                    "ItemDescription": item.get("ItemName", ""),
                    "Quantity":       float(item.get("Quantity", 1)),
                    "UnitPrice":      float(item.get("Price", 0)),
                    "WarehouseCode":  item.get("Warehouse", "01"),
                }
                for item in items
            ],
        }

        sales_app_format = {
            "CardCode":      customer_code,
            "DocDate":       today_str,
            "DocDueDate":    valid_until,
            "Comments":      comment_text,
            "DocType":       self.SAP_OBJECT_CODE,
            "DocTotal":      total_amount,
            "DocCurrency":   "KES",
            "DocumentLines": sap_format["DocumentLines"],
        }

        simplified_format = {
            "customerCode": customer_code,
            "date":         today_str,
            "validUntil":   valid_until,
            "notes":        comments,
            "documentType": "QUOTATION",
            "items": [
                {
                    "itemCode": item.get("ItemCode"),
                    "itemName": item.get("ItemName", ""),
                    "quantity": item.get("Quantity", 1),
                    "price":    item.get("Price", 0),
                    "total":    item.get("Quantity", 1) * item.get("Price", 0),
                }
                for item in items
            ],
        }

        return {
            "documents":   documents_format,
            "sales_app":   sales_app_format,
            "sap":         sap_format,
            "simplified":  simplified_format,
            "summary": {
                "customer_code": customer_code,
                "item_count":    len(items),
                "total_amount":  total_amount,
                "valid_until":   valid_until,
            },
        }

    def _pick_payload(self, endpoint: str, formatted: Dict[str, Any]) -> Dict[str, Any]:
        """Choose the best payload format for a given endpoint URL."""
        if "documents" in endpoint:
            logger.info("📤 Using 'documents' payload format")
            return formatted["documents"]
        if "quotations" in endpoint or "sales" in endpoint:
            logger.info("📤 Using 'sales_app' payload format")
            return formatted["sales_app"]
        if "marketing" in endpoint:
            logger.info("📤 Using 'sap' payload format")
            return formatted["sap"]
        logger.info("📤 Using 'simplified' payload format")
        return formatted["simplified"]

    # ==========================================================
    # CREATE QUOTATION (FULLY FIXED WITH RESPONSE FORMATTER)
    # ==========================================================
    def create_quotation(
        self,
        customer_code: str,
        items: List[Dict[str, Any]],
        comments: str = "",
        valid_until_days: int = 30,
        force_web_fallback: bool = False,
        language: str = "en",
        refresh_cache: bool = False,
    ) -> Dict[str, Any]:
        """
        Create a Sales Quotation (Object Type 23).
        Returns formatted success message with item details using ResponseFormatter.
        """
        invalid_items: List[Dict] = []

        try:
            logger.info(f"📝 Creating quotation for customer: {customer_code}")

            if not items:
                return ResponseFormatter.format_quotation_creation_error(
                    "No items provided for quotation.",
                    language=language
                )

            valid_items, invalid_items = self._validate_quotation_items(items)

            if not valid_items:
                err = "No valid items with prices found" if language != "sw" else "Hakuna bidhaa halali zenye bei"
                if invalid_items:
                    names = [i.get("ItemName", i["ItemCode"]) for i in invalid_items[:3]]
                    suffix = f". Skipped: {', '.join(names)}" if language != "sw" else f". Zimerukwa: {', '.join(names)}"
                    if len(invalid_items) > 3:
                        suffix += f" and {len(invalid_items) - 3} more" if language != "sw" else f" na {len(invalid_items) - 3} nyingine"
                    err += suffix
                
                return ResponseFormatter.format_quotation_creation_error(
                    err,
                    invalid_items,
                    language=language
                )

            if force_web_fallback:
                return self._get_web_fallback_response(customer_code, valid_items, invalid_items, language=language)

            # Get customer name for display
            customer_name = customer_code
            try:
                customer = self.api.get_customer_by_code(customer_code)
                if customer:
                    customer_name = customer.get("CardName", customer_code)
            except Exception:
                pass

            # Discover endpoints
            endpoint_info = self._discover_quotation_endpoint(force_refresh=refresh_cache)
            primary = endpoint_info.get("create")

            def _to_full_url(ep: str) -> str:
                if ep.startswith("http://") or ep.startswith("https://"):
                    return ep
                return f"{self.base_url}{ep if ep.startswith('/') else '/' + ep}"

            endpoints_to_try: List[str] = []
            if primary:
                endpoints_to_try.append(_to_full_url(primary))

            for rel in self.KNOWN_POST_ENDPOINTS:
                full = _to_full_url(rel)
                if full not in endpoints_to_try:
                    endpoints_to_try.append(full)

            if not endpoints_to_try:
                logger.warning("⚠️ No POST endpoints to try for quotations")
                return self._get_web_fallback_response(
                    customer_code, valid_items, invalid_items,
                    additional_note="No POST endpoint configured." if language != "sw"
                    else "Hakuna mwisho wa POST uliowekwa.",
                    language=language,
                )

            # Format payload
            formatted = self._format_quotation_for_api(
                customer_code, valid_items, comments, valid_until_days
            )

            logger.info(f"📤 Will try {len(endpoints_to_try)} endpoint(s) for quotation creation")
            last_error = None

            for endpoint_url in endpoints_to_try:
                payload = self._pick_payload(endpoint_url, formatted)
                logger.info(f"   → POST {endpoint_url}")

                try:
                    response = requests.post(
                        endpoint_url,
                        headers=self.headers,
                        json=payload,
                        timeout=self.timeout,
                    )
                except requests.exceptions.ConnectionError as e:
                    logger.warning(f"   Connection error: {e} — trying next endpoint")
                    last_error = str(e)
                    continue
                except requests.Timeout:
                    logger.warning(f"   Timeout — trying next endpoint")
                    last_error = "Timeout"
                    continue
                except Exception as e:
                    logger.warning(f"   Unexpected error: {e} — trying next endpoint")
                    last_error = str(e)
                    continue

                if not self._check_response_auth(response, endpoint_url):
                    auth_note = ("API session expired. Please log in again through the web interface."
                                 if language != "sw"
                                 else "Huduma ya API inahitaji kuingia tena.")
                    return self._get_web_fallback_response(
                        customer_code, valid_items, invalid_items,
                        additional_note=auth_note, language=language,
                    )

                if response.status_code == 405:
                    logger.warning(f"   405 Method Not Allowed — trying next endpoint")
                    last_error = f"405 from {endpoint_url}"
                    continue

                if response.status_code in [200, 201]:
                    try:
                        result = response.json()
                    except Exception:
                        result = {"raw_response": response.text}

                    logger.info(f"📥 Quotation API response: {str(result)[:500]}")

                    # Extract document details
                    doc_entry = None
                    doc_num = None
                    success = False
                    
                    if isinstance(result, dict):
                        if result.get("ResultState") is True or result.get("success") is True:
                            success = True
                        
                        inner = result.get("ResponseData", result)
                        
                        if isinstance(inner, dict):
                            doc_entry = (inner.get("DocEntry") or inner.get("doc_entry")
                                        or inner.get("DocNum") or inner.get("doc_num")
                                        or inner.get("id") or inner.get("ID"))
                            doc_num = (inner.get("DocNum") or inner.get("doc_num")
                                      or inner.get("docNum") or doc_entry)
                        elif isinstance(inner, list) and len(inner) > 0:
                            first_item = inner[0]
                            doc_entry = (first_item.get("DocEntry") or first_item.get("doc_entry")
                                        or first_item.get("DocNum") or first_item.get("doc_num"))
                            doc_num = (first_item.get("DocNum") or first_item.get("doc_num")
                                      or first_item.get("docNum") or doc_entry)
                    
                    if success or response.status_code in [200, 201]:
                        total_amount = formatted["summary"]["total_amount"]
                        valid_until = formatted["summary"]["valid_until"]
                        
                        # Use ResponseFormatter to format the success message
                        formatted_response = ResponseFormatter.format_quotation_creation_success(
                            customer_name=customer_name,
                            items=valid_items,
                            total_amount=total_amount,
                            valid_until=valid_until,
                            doc_num=doc_num,
                            language=language
                        )
                        
                        logger.info(f"✅ Quotation created successfully via {endpoint_url}")
                        
                        response_data = {
                            "success": True,
                            "DocEntry": doc_entry,
                            "DocNum": doc_num,
                            "CardCode": customer_code,
                            "ValidUntil": valid_until,
                            "ItemCount": len(valid_items),
                            "TotalAmount": total_amount,
                            "valid_items": valid_items,
                            "endpoint_used": endpoint_url,
                            "language": language,
                            "raw_response": result,
                            "message": formatted_response["message"],
                            "data": formatted_response["data"]
                        }
                        
                        if invalid_items:
                            response_data["skipped_items"] = invalid_items
                            response_data["warning"] = (
                                f"{len(invalid_items)} item(s) were skipped due to invalid prices or non-sellable status"
                                if language != "sw"
                                else f"Bidhaa {len(invalid_items)} zimerukwa kwa sababu ya bei batili"
                            )
                        
                        return response_data

                # Handle error responses
                try:
                    error_json = response.json()
                except Exception:
                    error_json = response.text[:500]

                logger.error(f"   {response.status_code} from {endpoint_url}: {error_json}")

                if response.status_code == 400:
                    return ResponseFormatter.format_quotation_creation_error(
                        "Bad request — check quotation data",
                        invalid_items,
                        language=language
                    )

                last_error = {"status": response.status_code, "endpoint": endpoint_url, "details": error_json}

            # All endpoints exhausted
            logger.warning("⚠️ All POST endpoints failed for quotations")
            additional_note = (
                "The API only supports viewing quotations (GET), not creating them (POST)."
                if language != "sw"
                else "API inaweza tu kuona nukuu (GET), si kuunda (POST)."
            )
            result = self._get_web_fallback_response(
                customer_code, valid_items, invalid_items,
                additional_note=additional_note, language=language,
            )
            result["last_error"] = last_error
            result["tried_endpoints"] = endpoints_to_try
            return result

        except requests.Timeout:
            logger.error("❌ Quotation creation timed out")
            return ResponseFormatter.format_quotation_creation_error(
                "Request timed out. Please try again.",
                invalid_items,
                language=language
            )
        except Exception as e:
            logger.exception("❌ Quotation creation failed unexpectedly")
            return ResponseFormatter.format_quotation_creation_error(
                str(e),
                invalid_items,
                language=language
            )

    # ==========================================================
    # GET LATEST QUOTATION
    # ==========================================================
    def get_latest_quotation(self, customer_code: str, language: str = "en") -> Optional[Dict[str, Any]]:
        """
        Get the most recent quotation for a customer.
        Useful after creating a quotation when DocNum isn't returned.
        """
        try:
            params = {
                "CardCode": customer_code,
                "page": 1,
                "per_page": 1,
                "isDoc": 1
            }
            
            response = requests.get(
                f"{self.base_url}/marketing/docs/{self.SAP_OBJECT_CODE}",
                headers=self.headers,
                params=params,
                timeout=self.timeout,
            )
            
            if response.status_code == 200:
                data = response.json()
                quotations = data.get("ResponseData", data.get("data", [])) if isinstance(data, dict) else data
                
                if quotations and len(quotations) > 0:
                    latest = quotations[0]
                    doc_status = latest.get("DocStatus")
                    if doc_status in self.STATUS_MAP:
                        latest["StatusText"] = self.STATUS_MAP[doc_status].get(language, self.STATUS_MAP[doc_status]["en"])
                    
                    doc_entry = latest.get("DocEntry")
                    if doc_entry:
                        full_quotation = self.get_quotation(str(doc_entry), language)
                        if full_quotation:
                            return full_quotation
                    
                    return latest
            
            return None
        except Exception as e:
            logger.error(f"Error getting latest quotation for {customer_code}: {e}")
            return None

    # ==========================================================
    # WEB FALLBACK RESPONSE
    # ==========================================================
    def _get_web_fallback_response(
        self,
        customer_code: str,
        valid_items: List[Dict],
        invalid_items: List[Dict],
        additional_note: str = "",
        language: str = "en",
    ) -> Dict[str, Any]:
        total_amount = sum(item.get("Quantity", 1) * item.get("Price", 0) for item in valid_items)

        customer_name = customer_code
        try:
            customer = self.api.get_customer_by_code(customer_code)
            if customer:
                customer_name = customer.get("CardName", customer_code)
        except Exception:
            pass

        is_auth_issue = additional_note and ("expired" in additional_note.lower() or "log in" in additional_note.lower())

        if language == "sw":
            response = {
                "success": False,
                "api_available": False,
                "message": "Kuunda nukuu kupitia API haiwezekani. Tafadhali tumia wavuti.",
                "web_interface_instructions": {
                    "title": "📋 Unda Nukuu Kwenye Wavuti",
                    "steps": [
                        f"1️⃣ Nenda kwenye **Mauzo → Nukuu** kwenye wavuti ya Leysco",
                        f"2️⃣ Bofya kitufe cha **'Nukuu Mpya'**",
                        f"3️⃣ Chagua mteja: **{customer_name}** ({customer_code})",
                        f"4️⃣ Ongeza bidhaa zifuatazo:",
                    ],
                    "items": [
                        f"   • {item.get('ItemName', item['ItemCode'])} - {item['Quantity']} vitengo @ "
                        f"KES {item['Price']:,.2f} = KES {item['Quantity'] * item['Price']:,.2f}"
                        for item in valid_items
                    ],
                    "total": f"**Jumla ya Kiasi: KES {total_amount:,.2f}**",
                    "additional_steps": [
                        "5️⃣ Weka muda wa uhalali (kawaida: siku 30)",
                        "6️⃣ Ongeza maoni au maelezo yoyote",
                        "7️⃣ Hifadhi na tuma kwa mteja",
                    ],
                },
                "quotation_summary": {
                    "customer_code":  customer_code,
                    "customer_name":  customer_name,
                    "items_count":    len(valid_items),
                    "total_amount":   total_amount,
                    "valid_items":    valid_items[:5],
                    "valid_until":    (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
                },
                "language": language,
            }
            if is_auth_issue:
                response["auth_instructions"] = "🔑 Tafadhali ingia tena kwenye wavuti ya Leysco kwanza."
        else:
            response = {
                "success": False,
                "api_available": False,
                "message": "Quotation creation via API is not available. Please use the web interface.",
                "web_interface_instructions": {
                    "title": "📋 Create Quotation in Web Interface",
                    "steps": [
                        f"1️⃣ Go to **Sales → Quotations** in the Leysco web application",
                        f"2️⃣ Click **'New Quotation'** button",
                        f"3️⃣ Select customer: **{customer_name}** ({customer_code})",
                        f"4️⃣ Add the following items:",
                    ],
                    "items": [
                        f"   • {item.get('ItemName', item['ItemCode'])} - {item['Quantity']} units @ "
                        f"KES {item['Price']:,.2f} = KES {item['Quantity'] * item['Price']:,.2f}"
                        for item in valid_items
                    ],
                    "total": f"**Total Amount: KES {total_amount:,.2f}**",
                    "additional_steps": [
                        "5️⃣ Set validity period (default: 30 days)",
                        "6️⃣ Add any comments or notes",
                        "7️⃣ Save and send to customer",
                    ],
                },
                "quotation_summary": {
                    "customer_code":  customer_code,
                    "customer_name":  customer_name,
                    "items_count":    len(valid_items),
                    "total_amount":   total_amount,
                    "valid_items":    valid_items[:5],
                    "valid_until":    (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
                },
                "language": language,
            }
            if is_auth_issue:
                response["auth_instructions"] = "🔑 Please log in to the Leysco web application first."

        if additional_note and not is_auth_issue:
            response["note"] = additional_note

        if invalid_items:
            key = "skipped_items"
            if language == "sw":
                response[key] = {
                    "count": len(invalid_items),
                    "items": [f"• {i.get('ItemName', i['ItemCode'])}: {i['reason']}" for i in invalid_items[:5]],
                    "note":  "Bidhaa hizi zimerukwa kwa sababu hazina bei au si za kuuzwa.",
                }
            else:
                response[key] = {
                    "count": len(invalid_items),
                    "items": [f"• {i.get('ItemName', i['ItemCode'])}: {i['reason']}" for i in invalid_items[:5]],
                    "note":  "These items were skipped because they are not sellable or have no price.",
                }
            if len(invalid_items) > 5:
                extra = len(invalid_items) - 5
                response[key]["note"] += (
                    f" ({extra} more not shown)" if language != "sw" else f" (na {extra} nyingine hazijaonyeshwa)"
                )

        if hasattr(self, '_endpoint_cache') and self._endpoint_cache:
            response["api_discovery"] = {
                "supported_methods":  self._endpoint_cache.get("supported_methods", ["GET"]),
                "available_endpoints": self._endpoint_cache.get("available_endpoints", []),
            }

        return response

    # ==========================================================
    # GET SINGLE QUOTATION
    # ==========================================================
    def get_quotation(self, doc_entry: str, language: str = "en") -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{self.base_url}/marketing/docs/{self.SAP_OBJECT_CODE}/{doc_entry}",
                headers=self.headers,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    doc_status = data.get("DocStatus")
                    if doc_status in self.STATUS_MAP:
                        data["StatusText"] = self.STATUS_MAP[doc_status].get(language, self.STATUS_MAP[doc_status]["en"])
                return data
            logger.error(f"Failed to retrieve quotation {doc_entry}: {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving quotation: {e}")
            return None

    # ==========================================================
    # GET CUSTOMER QUOTATIONS
    # ==========================================================
    def get_customer_quotations(
        self,
        customer_code: str,
        page: int = 1,
        per_page: int = 10,
        status: Optional[str] = None,
        language: str = "en",
    ) -> List[Dict[str, Any]]:
        try:
            params = {"CardCode": customer_code, "page": page, "per_page": per_page}
            if status and status.lower() == "open":
                params["DocStatus"] = 1
            elif status and status.lower() == "closed":
                params["DocStatus"] = 2

            response = requests.get(
                f"{self.base_url}/marketing/docs/{self.SAP_OBJECT_CODE}",
                headers=self.headers,
                params=params,
                timeout=self.timeout,
            )

            if response.status_code == 200:
                data = response.json()
                quotations = data.get("ResponseData", data.get("data", [])) if isinstance(data, dict) else data
                for q in quotations:
                    ds = q.get("DocStatus")
                    if ds in self.STATUS_MAP:
                        q["StatusText"] = self.STATUS_MAP[ds].get(language, self.STATUS_MAP[ds]["en"])
                logger.info(f"✅ Retrieved {len(quotations)} quotations for {customer_code}")
                return quotations

            logger.error(f"Failed to get quotations for {customer_code}: {response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Error getting customer quotations: {e}")
            return []

    # ==========================================================
    # CHECK QUOTATION STATUS
    # ==========================================================
    def check_quotation_status(self, doc_num: str, language: str = "en") -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{self.base_url}/marketing/docs/{self.SAP_OBJECT_CODE}/{doc_num}",
                headers=self.headers,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                data = response.json()
                doc_status  = data.get("DocStatus")
                status_info = self.STATUS_MAP.get(doc_status, {"en": "Unknown", "sw": "Haijulikani"})
                return {
                    "doc_num":         doc_num,
                    "status_code":     doc_status,
                    "status":          status_info.get(language, status_info["en"]),
                    "customer":        data.get("CardCode"),
                    "customer_name":   data.get("CardName"),
                    "total":           data.get("DocTotal"),
                    "total_formatted": f"KES {float(data.get('DocTotal', 0)):,.2f}",
                    "valid_until":     data.get("DocDueDate"),
                    "date":            data.get("DocDate"),
                }
            return None
        except Exception as e:
            logger.error(f"Error checking quotation status: {e}")
            return None

    # ==========================================================
    # GET QUOTATION BY NUMBER
    # ==========================================================
    def get_quotation_by_number(self, doc_num: str, language: str = "en") -> Optional[Dict[str, Any]]:
        try:
            params   = {"page": 1, "per_page": 50, "search": doc_num}
            response = requests.get(
                f"{self.base_url}/marketing/docs/{self.SAP_OBJECT_CODE}",
                headers=self.headers,
                params=params,
                timeout=self.timeout,
            )
            if response.status_code == 200:
                data       = response.json()
                quotations = data.get("ResponseData", data.get("data", [])) if isinstance(data, dict) else data
                for q in quotations:
                    if str(q.get("DocNum")) == str(doc_num):
                        ds = q.get("DocStatus")
                        if ds in self.STATUS_MAP:
                            q["StatusText"] = self.STATUS_MAP[ds].get(language, self.STATUS_MAP[ds]["en"])
                        return q
                logger.warning(f"Quotation {doc_num} not found")
            return None
        except Exception as e:
            logger.error(f"Error searching for quotation {doc_num}: {e}")
            return None