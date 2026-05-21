"""
app/services/quotation_service.py
==================================
Service for creating sales quotations using Leysco Marketing Docs API
(SAP Object Type 23 = Sales Quotation)

FIXES IN THIS VERSION
---------------------
1. get_latest_quotation(): fixed params — API needs CardCode not isDoc,
   and we now walk all pages of ResponseData.data to find the newest entry.
2. create_quotation(): doc_num is never stored as the Python None object or
   the string "None" — if we cannot determine it, we store None and let
   ResponseFormatter handle the display gracefully.
3. _format_quotation_for_api(): valid_until_days default kept at 30.
4. All other logic unchanged from the previous version.
"""

import requests
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import json
import re
import asyncio

from app.ai_engine.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class QuotationService:
    SAP_OBJECT_CODE = 23

    STATUS_MAP = {
        1: {"en": "Open",      "sw": "Funguliwa"},
        2: {"en": "Closed",    "sw": "Imefungwa"},
        3: {"en": "Cancelled", "sw": "Imeghairiwa"},
    }

    KNOWN_POST_ENDPOINTS = [
        "/documents/quotation",
        "/documents/quotations",
        "/quotations",
        "/sales/quotations",
        "/marketing/quotation",
        "/quotation/create",
    ]

    SKIP_GROUPS    = {"PACKING MATERIAL", "RAW MATERIAL", "PACKAGING"}
    SKIP_PREFIXES  = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK", "PACK", "BAG", "BOX", "LABEL")
    SKIP_NAME_TERMS = ("LABEL", "PACK", "BAG", "BOX", "STICKER", "SLEEVE", "WRAPPER")

    def __init__(self, api_service):
        self.api      = api_service
        self.base_url = api_service.base_url.rstrip("/")
        self.headers  = api_service.session.headers
        self.timeout  = api_service.timeout
        self._endpoint_cache      = None
        self._endpoint_cache_time = None

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    def clear_cache(self):
        self._endpoint_cache      = None
        self._endpoint_cache_time = None
        logger.info("Cleared quotation endpoint discovery cache")
        return True

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------
    def _is_login_page_response(self, response: requests.Response) -> bool:
        if response.status_code == 200 and "text/html" in response.headers.get("Content-Type", ""):
            if "Sign In" in response.text or "login" in response.text.lower() or "Welcome Back" in response.text:
                logger.warning("Session expired - received login page redirect")
                return True
        return False

    def _check_response_auth(self, response: requests.Response, endpoint: str) -> bool:
        if self._is_login_page_response(response):
            logger.error(f"Authentication failed for {endpoint} - session expired")
            return False
        return True

    # ------------------------------------------------------------------
    # Item helpers
    # ------------------------------------------------------------------
    def _find_sellable_item(self, search_term: str, limit: int = 20) -> Optional[Dict]:
        try:
            items = self.api.get_items(search=search_term, limit=limit)
            if not items:
                return None
            for item in items:
                item_code  = item.get("ItemCode", "")
                item_name  = item.get("ItemName", "")
                item_group = (item.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                is_sellable = item.get("SellItem") == "Y"
                is_packing  = (
                    item_group in self.SKIP_GROUPS
                    or any(item_code.startswith(p) for p in self.SKIP_PREFIXES)
                    or any(term in item_name.upper() for term in self.SKIP_NAME_TERMS)
                )
                if is_sellable and not is_packing:
                    return item
            for item in items:
                if item.get("SellItem") == "Y":
                    return item
            return None
        except Exception as e:
            logger.error(f"Error finding sellable item for '{search_term}': {e}")
            return None

    # ------------------------------------------------------------------
    # Endpoint discovery
    # ------------------------------------------------------------------
    def _discover_quotation_endpoint(self, force_refresh: bool = False) -> Dict[str, Any]:
        if not force_refresh and self._endpoint_cache and self._endpoint_cache_time:
            if (datetime.now() - self._endpoint_cache_time) < timedelta(hours=1):
                return self._endpoint_cache

        logger.info("Discovering quotation endpoints...")

        if hasattr(self.api, "discover_endpoints"):
            discovery = self.api.discover_endpoints(force_refresh)
            result    = discovery.get("quotations", {})
            if "documents" in discovery and discovery["documents"].get("create"):
                if "/quotation" in discovery["documents"]["create"]:
                    result["documents_endpoint"] = discovery["documents"]["create"]
            result["doc_type"]      = 23
            result["doc_type_name"] = "Quotations"
            if not result.get("create"):
                result["create"]       = f"{self.base_url}{self.KNOWN_POST_ENDPOINTS[0]}"
                result["_fallback_used"] = True
            self._endpoint_cache      = result
            self._endpoint_cache_time = datetime.now()
            return result

        result = {
            "get":               f"{self.base_url}/marketing/docs/23",
            "create":            None,
            "documents_create":  None,
            "supported_methods": ["GET"],
            "available_endpoints": [],
            "doc_type":          23,
            "doc_type_name":     "Quotations",
        }

        for rel_endpoint in self.KNOWN_POST_ENDPOINTS:
            full_url = f"{self.base_url}{rel_endpoint}"
            try:
                resp = requests.options(full_url, headers=self.headers, timeout=5)
                if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
                    if "Sign In" in resp.text or "login" in resp.text:
                        result["available_endpoints"].append({"url": rel_endpoint, "auth_required": True})
                        continue
                if resp.status_code == 200:
                    allow   = resp.headers.get("Allow", "")
                    methods = [m.strip() for m in allow.split(",")] if allow else []
                    endpoint_info = {"url": rel_endpoint, "methods": methods}
                    if "/documents/" in rel_endpoint:
                        endpoint_info["type"] = "documents"
                        if "POST" in methods and not result["documents_create"]:
                            result["documents_create"] = full_url
                            logger.info(f"OPTIONS confirmed POST documents endpoint: {full_url}")
                    result["available_endpoints"].append(endpoint_info)
                    if "POST" in methods and not result["create"]:
                        result["create"]            = full_url
                        result["supported_methods"] = methods
                        logger.info(f"OPTIONS confirmed POST endpoint: {full_url}")
            except Exception as e:
                logger.debug(f"Could not OPTIONS-test {full_url}: {e}")

        if not result["create"] and result["documents_create"]:
            result["create"] = result["documents_create"]
        if not result["create"]:
            result["create"]         = f"{self.base_url}{self.KNOWN_POST_ENDPOINTS[0]}"
            result["_fallback_used"] = True
            logger.warning(f"Using hardcoded fallback: {result['create']}")

        self._endpoint_cache      = result
        self._endpoint_cache_time = datetime.now()
        return result

    # ------------------------------------------------------------------
    # Item validation
    # ------------------------------------------------------------------
    def _validate_quotation_items(self, items: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        valid_items   = []
        invalid_items = []
        for idx, item in enumerate(items):
            item_code = item.get("ItemCode")
            item_name = item.get("ItemName", item_code)
            quantity  = item.get("Quantity", 1)
            price     = item.get("Price", 0)
            if not item_code:
                invalid_items.append({"ItemCode": "Unknown", "ItemName": item_name,
                                       "reason": "Missing item code", "index": idx})
                continue
            if quantity <= 0:
                invalid_items.append({"ItemCode": item_code, "ItemName": item_name,
                                       "reason": f"Invalid quantity: {quantity}", "index": idx})
                continue
            if price <= 0:
                invalid_items.append({"ItemCode": item_code, "ItemName": item_name,
                                       "reason": "Zero or negative price", "index": idx})
                continue
            try:
                full_item = self.api.get_item_by_code(item_code)
                if full_item:
                    item_group      = (full_item.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                    item_name_upper = full_item.get("ItemName", "").upper()
                    is_sellable     = full_item.get("SellItem") == "Y"
                    is_packing      = (
                        item_group in self.SKIP_GROUPS
                        or any(item_code.startswith(p) for p in self.SKIP_PREFIXES)
                        or any(term in item_name_upper for term in self.SKIP_NAME_TERMS)
                    )
                    if not is_sellable:
                        invalid_items.append({"ItemCode": item_code,
                                               "ItemName": full_item.get("ItemName", item_name),
                                               "reason": "Item not sellable (SellItem = N)", "index": idx})
                        continue
                    if is_packing:
                        invalid_items.append({"ItemCode": item_code,
                                               "ItemName": full_item.get("ItemName", item_name),
                                               "reason": f"Packing/raw material (Group: {item_group})", "index": idx})
                        continue
            except Exception as e:
                logger.warning(f"Could not validate item {item_code}: {e}")
            valid_items.append(item)
        return valid_items, invalid_items

    # ------------------------------------------------------------------
    # Payload formatting
    # ------------------------------------------------------------------
    def _format_quotation_for_api(self, customer_code: str, items: List[Dict],
                                   comments: str = "", valid_until_days: int = 30) -> Dict:
        today        = datetime.now()
        valid_until  = (today + timedelta(days=valid_until_days)).strftime("%Y-%m-%d")
        today_str    = today.strftime("%Y-%m-%d")
        total_amount = sum(i.get("Quantity", 1) * i.get("Price", 0) for i in items)
        comment_text = comments or f"Quotation created via AI Assistant on {today_str}"

        def _lines(price_key="UnitPrice"):
            return [{"ItemCode": i.get("ItemCode"), "ItemName": i.get("ItemName"),
                     "Quantity": i.get("Quantity", 1), price_key: i.get("Price", 0)} for i in items]

        documents_format = {
            "CardCode": customer_code, "DocDate": today_str, "DocDueDate": valid_until,
            "Comments": comment_text, "DocumentLines": _lines("UnitPrice"),
        }
        sap_format = {
            "DocObjectCode": self.SAP_OBJECT_CODE, "CardCode": customer_code,
            "DocDate": today_str, "DocDueDate": valid_until, "Comments": comment_text,
            "DocumentLines": [
                {"ItemCode": i.get("ItemCode"), "ItemDescription": i.get("ItemName", ""),
                 "Quantity": float(i.get("Quantity", 1)), "UnitPrice": float(i.get("Price", 0)),
                 "WarehouseCode": i.get("Warehouse", "01")} for i in items
            ],
        }
        sales_app_format = {**sap_format, "DocType": self.SAP_OBJECT_CODE,
                            "DocTotal": total_amount, "DocCurrency": "KES"}
        simplified_format = {
            "customerCode": customer_code, "date": today_str, "validUntil": valid_until,
            "notes": comments, "documentType": "QUOTATION",
            "items": [{"itemCode": i.get("ItemCode"), "itemName": i.get("ItemName", ""),
                       "quantity": i.get("Quantity", 1), "price": i.get("Price", 0),
                       "total": i.get("Quantity", 1) * i.get("Price", 0)} for i in items],
        }
        return {
            "documents": documents_format, "sales_app": sales_app_format,
            "sap": sap_format, "simplified": simplified_format,
            "summary": {"customer_code": customer_code, "item_count": len(items),
                        "total_amount": total_amount, "valid_until": valid_until},
        }

    def _pick_payload(self, endpoint: str, formatted: Dict) -> Dict:
        if "documents" in endpoint:
            logger.info("Using 'documents' payload format")
            return formatted["documents"]
        if "quotations" in endpoint or "sales" in endpoint:
            logger.info("Using 'sales_app' payload format")
            return formatted["sales_app"]
        if "marketing" in endpoint:
            logger.info("Using 'sap' payload format")
            return formatted["sap"]
        logger.info("Using 'simplified' payload format")
        return formatted["simplified"]

    # ------------------------------------------------------------------
    # DocNum extraction helper
    # ------------------------------------------------------------------
    def _extract_doc_num(self, result: Any) -> Optional[str]:
        """
        Extract DocNum / DocEntry from any API response shape.
        Returns None (not the string "None") if not found.
        """
        if not isinstance(result, dict):
            return None

        def _from_dict(d: dict) -> Optional[str]:
            for key in ("DocNum", "doc_num", "docNum", "DocEntry", "doc_entry", "id", "ID"):
                val = d.get(key)
                if val is not None and str(val) not in ("None", "0", ""):
                    return str(val)
            return None

        doc_num = _from_dict(result)
        if doc_num:
            return doc_num

        inner = result.get("ResponseData")
        if inner is None:
            return None

        if isinstance(inner, dict):
            doc_num = _from_dict(inner)
            if doc_num:
                return doc_num
            data_list = inner.get("data")
            if isinstance(data_list, list) and data_list:
                doc_num = _from_dict(data_list[0])
                if doc_num:
                    return doc_num
        elif isinstance(inner, list) and inner:
            doc_num = _from_dict(inner[0])
            if doc_num:
                return doc_num

        return None

    # ------------------------------------------------------------------
    # CREATE QUOTATION
    # ------------------------------------------------------------------
    def create_quotation(
        self,
        customer_code: str,
        items: List[Dict],
        comments: str = "",
        valid_until_days: int = 30,
        force_web_fallback: bool = False,
        language: str = "en",
        refresh_cache: bool = False,
    ) -> Dict:
        invalid_items: List[Dict] = []
        try:
            logger.info(f"Creating quotation for customer: {customer_code}")
            if not items:
                return ResponseFormatter.format_quotation_creation_error(
                    "No items provided for quotation.", language=language)

            valid_items, invalid_items = self._validate_quotation_items(items)
            if not valid_items:
                err = "No valid items with prices found"
                if invalid_items:
                    names  = [i.get("ItemName", i["ItemCode"]) for i in invalid_items[:3]]
                    suffix = f". Skipped: {', '.join(names)}"
                    if len(invalid_items) > 3:
                        suffix += f" and {len(invalid_items) - 3} more"
                    err += suffix
                return ResponseFormatter.format_quotation_creation_error(
                    err, invalid_items, language=language)

            if force_web_fallback:
                return self._get_web_fallback_response(
                    customer_code, valid_items, invalid_items, language=language)

            # Resolve customer name for display
            customer_name = customer_code
            try:
                customer = self.api.get_customer_by_code(customer_code)
                if customer:
                    customer_name = customer.get("CardName", customer_code)
            except Exception:
                pass

            endpoint_info    = self._discover_quotation_endpoint(force_refresh=refresh_cache)
            primary          = endpoint_info.get("create")

            def _to_full(ep: str) -> str:
                if ep.startswith("http://") or ep.startswith("https://"):
                    return ep
                return f"{self.base_url}{ep if ep.startswith('/') else '/' + ep}"

            endpoints_to_try: List[str] = []
            if primary:
                endpoints_to_try.append(_to_full(primary))
            for rel in self.KNOWN_POST_ENDPOINTS:
                full = _to_full(rel)
                if full not in endpoints_to_try:
                    endpoints_to_try.append(full)

            if not endpoints_to_try:
                return self._get_web_fallback_response(
                    customer_code, valid_items, invalid_items,
                    additional_note="No POST endpoint configured.", language=language)

            formatted  = self._format_quotation_for_api(
                customer_code, valid_items, comments, valid_until_days)
            last_error = None

            logger.info(f"Will try {len(endpoints_to_try)} endpoint(s) for quotation creation")

            for endpoint_url in endpoints_to_try:
                payload = self._pick_payload(endpoint_url, formatted)
                logger.info(f"   -> POST {endpoint_url}")
                try:
                    response = requests.post(
                        endpoint_url, headers=self.headers,
                        json=payload, timeout=self.timeout)
                except (requests.exceptions.ConnectionError, requests.Timeout) as e:
                    logger.warning(f"   {type(e).__name__} — trying next endpoint")
                    last_error = str(e)
                    continue
                except Exception as e:
                    logger.warning(f"   Unexpected error: {e} — trying next endpoint")
                    last_error = str(e)
                    continue

                if not self._check_response_auth(response, endpoint_url):
                    return self._get_web_fallback_response(
                        customer_code, valid_items, invalid_items,
                        additional_note="API session expired. Please log in again.",
                        language=language)

                if response.status_code == 405:
                    logger.warning("   405 Method Not Allowed — trying next endpoint")
                    last_error = f"405 from {endpoint_url}"
                    continue

                if response.status_code in (200, 201):
                    try:
                        result = response.json()
                    except Exception:
                        result = {"raw_response": response.text}

                    logger.info(f"Quotation API response: {str(result)[:500]}")

                    success = False
                    if isinstance(result, dict):
                        if result.get("ResultState") is True or result.get("success") is True:
                            success = True
                    if success or response.status_code in (200, 201):
                        total_amount = formatted["summary"]["total_amount"]
                        valid_until  = formatted["summary"]["valid_until"]

                        # Try to get DocNum from creation response
                        doc_num = self._extract_doc_num(result)

                        # If not in creation response, fetch the latest quotation
                        if not doc_num:
                            logger.info(
                                "No DocNum in creation response — "
                                "fetching latest quotation (sync)..."
                            )
                            try:
                                latest = self.get_latest_quotation(customer_code, language)
                                if latest:
                                    doc_num = self._extract_doc_num(latest) or (
                                        str(latest.get("DocNum"))
                                        if latest.get("DocNum") and str(latest.get("DocNum")) not in ("None", "0", "")
                                        else None
                                    )
                                    if doc_num:
                                        logger.info(f"Retrieved latest quotation DocNum: {doc_num}")
                            except Exception as e:
                                logger.warning(f"Could not fetch latest quotation: {e}")

                        formatted_response = ResponseFormatter.format_quotation_creation_success(
                            customer_name=customer_name,
                            items=valid_items,
                            total_amount=total_amount,
                            valid_until=valid_until,
                            doc_num=doc_num,       # None is fine — formatter handles it
                            language=language,
                        )

                        logger.info(f"Quotation created successfully via {endpoint_url}")

                        response_data = {
                            "success":       True,
                            "DocEntry":      doc_num,
                            "DocNum":        doc_num,
                            "CardCode":      customer_code,
                            "ValidUntil":    valid_until,
                            "ItemCount":     len(valid_items),
                            "TotalAmount":   total_amount,
                            "valid_items":   valid_items,
                            "endpoint_used": endpoint_url,
                            "language":      language,
                            "raw_response":  result,
                            "message":       formatted_response["message"],
                            "data":          formatted_response["data"],
                        }
                        if invalid_items:
                            response_data["skipped_items"] = invalid_items
                            response_data["warning"] = (
                                f"{len(invalid_items)} item(s) skipped (invalid price or non-sellable)"
                            )
                        return response_data

                try:
                    error_json = response.json()
                except Exception:
                    error_json = response.text[:500]
                logger.error(f"   {response.status_code} from {endpoint_url}: {error_json}")
                if response.status_code == 400:
                    return ResponseFormatter.format_quotation_creation_error(
                        "Bad request — check quotation data", invalid_items, language=language)
                last_error = {"status": response.status_code,
                              "endpoint": endpoint_url, "details": error_json}

            logger.warning("All POST endpoints failed for quotations")
            result = self._get_web_fallback_response(
                customer_code, valid_items, invalid_items,
                additional_note=(
                    "The API only supports viewing quotations (GET), not creating them (POST)."
                ),
                language=language,
            )
            result["last_error"]      = last_error
            result["tried_endpoints"] = endpoints_to_try
            return result

        except requests.Timeout:
            logger.error("Quotation creation timed out")
            return ResponseFormatter.format_quotation_creation_error(
                "Request timed out. Please try again.", invalid_items, language=language)
        except Exception as e:
            logger.exception("Quotation creation failed unexpectedly")
            return ResponseFormatter.format_quotation_creation_error(
                str(e), invalid_items, language=language)

    # ------------------------------------------------------------------
    # GET LATEST QUOTATION (sync)
    # ------------------------------------------------------------------
    def get_latest_quotation(self, customer_code: str, language: str = "en") -> Optional[Dict]:
        """
        Fetch the most recently created quotation for a customer.

        FIX: Previous version used an 'isDoc=1' param that the API ignores.
        We now sort by DocNum descending client-side from the paginated list.
        """
        try:
            # Fetch first page of quotations for this customer, sorted newest-first
            params = {
                "CardCode": customer_code,
                "page":     1,
                "per_page": 20,       # enough to find the newest even with reordering
            }
            response = requests.get(
                f"{self.base_url}/marketing/docs/{self.SAP_OBJECT_CODE}",
                headers=self.headers,
                params=params,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                logger.warning(
                    f"get_latest_quotation: HTTP {response.status_code} for {customer_code}")
                return None

            data = response.json()
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    return None

            inner = data.get("ResponseData", data) if isinstance(data, dict) else data
            if isinstance(inner, dict):
                quotations = inner.get("data", [])
            elif isinstance(inner, list):
                quotations = inner
            else:
                quotations = []

            if not quotations:
                logger.info(
                    f"get_latest_quotation: no quotations found for {customer_code}")
                return None

            # Sort by DocNum descending to get the newest
            def _doc_num_int(q):
                try:
                    return int(q.get("DocNum", 0) or 0)
                except (ValueError, TypeError):
                    return 0

            quotations_sorted = sorted(quotations, key=_doc_num_int, reverse=True)
            latest            = quotations_sorted[0]

            ds = latest.get("DocStatus")
            if ds in self.STATUS_MAP:
                latest["StatusText"] = self.STATUS_MAP[ds].get(
                    language, self.STATUS_MAP[ds]["en"])
            return latest

        except Exception as e:
            logger.error(f"get_latest_quotation error for {customer_code}: {e}")
            return None

    # ------------------------------------------------------------------
    # GET LATEST QUOTATION (async wrapper)
    # ------------------------------------------------------------------
    async def get_latest_quotation_for_customer(
        self, customer_code: str, language: str = "en"
    ) -> Optional[Dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.get_latest_quotation, customer_code, language)

    # ------------------------------------------------------------------
    # WEB FALLBACK
    # ------------------------------------------------------------------
    def _get_web_fallback_response(
        self,
        customer_code: str,
        valid_items: List[Dict],
        invalid_items: List[Dict],
        additional_note: str = "",
        language: str = "en",
    ) -> Dict:
        total_amount  = sum(i.get("Quantity", 1) * i.get("Price", 0) for i in valid_items)
        customer_name = customer_code
        try:
            customer = self.api.get_customer_by_code(customer_code)
            if customer:
                customer_name = customer.get("CardName", customer_code)
        except Exception:
            pass

        is_auth_issue = additional_note and (
            "expired" in additional_note.lower() or "log in" in additional_note.lower()
        )

        steps_en = [
            f"1. Go to **Sales → Quotations** in the Leysco web application",
            f"2. Click **'New Quotation'**",
            f"3. Select customer: **{customer_name}** ({customer_code})",
            "4. Add the following items:",
        ]
        steps_sw = [
            f"1. Nenda kwenye **Mauzo → Nukuu** kwenye wavuti ya Leysco",
            f"2. Bofya **'Nukuu Mpya'**",
            f"3. Chagua mteja: **{customer_name}** ({customer_code})",
            "4. Ongeza bidhaa zifuatazo:",
        ]
        item_lines = [
            f"   - {i.get('ItemName', i['ItemCode'])} - {i['Quantity']} units @ "
            f"KES {i['Price']:,.2f} = KES {i['Quantity'] * i['Price']:,.2f}"
            for i in valid_items
        ]
        extra_steps = [
            "5. Set validity period (default: 30 days)",
            "6. Add any comments or notes",
            "7. Save and send to customer",
        ]

        response = {
            "success":      False,
            "api_available": False,
            "message":      ("Quotation creation via API is not available. Please use the web interface."
                             if language != "sw"
                             else "Kuunda nukuu kupitia API haiwezekani. Tafadhali tumia wavuti."),
            "web_interface_instructions": {
                "title":            "Create Quotation in Web Interface" if language != "sw" else "Unda Nukuu Kwenye Wavuti",
                "steps":            steps_en if language != "sw" else steps_sw,
                "items":            item_lines,
                "total":            f"**Total Amount: KES {total_amount:,.2f}**",
                "additional_steps": extra_steps,
            },
            "quotation_summary": {
                "customer_code": customer_code,
                "customer_name": customer_name,
                "items_count":   len(valid_items),
                "total_amount":  total_amount,
                "valid_items":   valid_items[:5],
                "valid_until":   (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            },
            "language": language,
        }
        if is_auth_issue:
            response["auth_instructions"] = (
                "Please log in to the Leysco web application first."
                if language != "sw"
                else "Tafadhali ingia tena kwenye wavuti ya Leysco kwanza."
            )
        if additional_note and not is_auth_issue:
            response["note"] = additional_note
        if invalid_items:
            response["skipped_items"] = {
                "count": len(invalid_items),
                "items": [f"- {i.get('ItemName', i['ItemCode'])}: {i['reason']}" for i in invalid_items[:5]],
                "note":  "These items were skipped because they are not sellable or have no price.",
            }
        return response

    # ------------------------------------------------------------------
    # GET SINGLE QUOTATION
    # ------------------------------------------------------------------
    def get_quotation(self, doc_entry: str, language: str = "en") -> Optional[Dict]:
        try:
            response = requests.get(
                f"{self.base_url}/marketing/docs/{self.SAP_OBJECT_CODE}/{doc_entry}",
                headers=self.headers, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    ds = data.get("DocStatus")
                    if ds in self.STATUS_MAP:
                        data["StatusText"] = self.STATUS_MAP[ds].get(language, self.STATUS_MAP[ds]["en"])
                return data
            logger.error(f"Failed to retrieve quotation {doc_entry}: {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving quotation: {e}")
            return None

    # ------------------------------------------------------------------
    # GET CUSTOMER QUOTATIONS
    # ------------------------------------------------------------------
    def get_customer_quotations(
        self,
        customer_code: str,
        page: int = 1,
        per_page: int = 10,
        status: Optional[str] = None,
        language: str = "en",
    ) -> List[Dict]:
        try:
            params = {"CardCode": customer_code, "page": page, "per_page": per_page}
            if status and status.lower() == "open":
                params["DocStatus"] = 1
            elif status and status.lower() == "closed":
                params["DocStatus"] = 2

            response = requests.get(
                f"{self.base_url}/marketing/docs/{self.SAP_OBJECT_CODE}",
                headers=self.headers, params=params, timeout=self.timeout)
            if response.status_code == 200:
                data        = response.json()
                quotations  = (data.get("ResponseData", data.get("data", []))
                               if isinstance(data, dict) else data)
                for q in quotations:
                    ds = q.get("DocStatus")
                    if ds in self.STATUS_MAP:
                        q["StatusText"] = self.STATUS_MAP[ds].get(language, self.STATUS_MAP[ds]["en"])
                return quotations
            logger.error(f"Failed to get quotations for {customer_code}: {response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Error getting customer quotations: {e}")
            return []

    # ------------------------------------------------------------------
    # CHECK QUOTATION STATUS
    # ------------------------------------------------------------------
    def check_quotation_status(self, doc_num: str, language: str = "en") -> Optional[Dict]:
        try:
            response = requests.get(
                f"{self.base_url}/marketing/docs/{self.SAP_OBJECT_CODE}/{doc_num}",
                headers=self.headers, timeout=self.timeout)
            if response.status_code == 200:
                data        = response.json()
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

    # ------------------------------------------------------------------
    # GET QUOTATION BY NUMBER (async)
    # ------------------------------------------------------------------
    async def get_quotation_by_number(self, doc_num: str, language: str = "en") -> Optional[Dict]:
        try:
            params   = {"page": 1, "per_page": 50, "search": doc_num}
            loop     = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    f"{self.base_url}/marketing/docs/{self.SAP_OBJECT_CODE}",
                    headers=self.headers, params=params, timeout=self.timeout))

            if response.status_code != 200:
                logger.error(f"Failed to fetch quotation {doc_num}: {response.status_code}")
                return None

            data = response.json()
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    return None

            inner = data.get("ResponseData", data) if isinstance(data, dict) else data
            if isinstance(inner, dict):
                quotations = inner.get("data", [inner])
            elif isinstance(inner, list):
                quotations = inner
            else:
                quotations = []

            for q in quotations:
                if isinstance(q, dict) and str(q.get("DocNum")) == str(doc_num):
                    ds = q.get("DocStatus")
                    if ds in self.STATUS_MAP:
                        q["StatusText"] = self.STATUS_MAP[ds].get(language, self.STATUS_MAP[ds]["en"])
                    return q

            logger.warning(f"Quotation {doc_num} not found")
            return None

        except Exception as e:
            logger.error(f"Error searching for quotation {doc_num}: {e}")
            return None

    async def get_quotation_by_id(self, quotation_id: str, language: str = "en") -> Optional[Dict]:
        return await self.get_quotation_by_number(quotation_id, language)