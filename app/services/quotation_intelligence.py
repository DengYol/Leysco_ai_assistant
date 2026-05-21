"""
app/services/quotation_intelligence.py
========================================
Quotation Follow-up Intelligence Service - Optimized with caching and async support

FIXED: Removed singleton pattern, now accepts user_token per instance
FIXED: Properly passes token to LeyscoAPIService and PricingService

Surfaces three types of actionable business intelligence:

1. Stale quotations  — open quotes with no activity for N+ days
2. Unconverted customers — customers who received quotes but haven't
   placed an order within a follow-up window
3. Conversion rate — what % of quotes turn into orders (per customer
   or overall)

All methods are read-only and call the existing LeyscoAPIService.
No new API endpoints are required.

Integration points
------------------
- Registered as FOLLOW_UP_QUOTATIONS in prompt_manager.VALID_INTENTS
- Routed in action_router under intent == "FOLLOW_UP_QUOTATIONS"
- Surfaced proactively by dashboard_service._quotation_alerts()
"""

from __future__ import annotations

import logging
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache, wraps

from app.services.leysco_api.client import LeyscoAPIService, create_api_service
from app.services.cache_service import get_cache_service
from app.services.pricing_service import get_pricing_service, create_pricing_service, PricingService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuneable thresholds
# ---------------------------------------------------------------------------
STALE_QUOTE_DAYS     = 7    # quote open for this many days → stale
FOLLOW_UP_DAYS       = 30   # customer received quote but no order within N days → flag
MAX_RESULTS          = 10   # max items per section
SAP_DOC_OPEN         = 1    # SAP DocStatus value for open documents
SAP_DOC_TYPE_QUOTE   = 23   # SAP document type: Quotations
SAP_DOC_TYPE_ORDER   = 17   # SAP document type: Sales Orders

# Cache TTLs
QUOTATION_CACHE_TTL = 1800   # 30 minutes
VALIDATION_CACHE_TTL = 300   # 5 minutes


def cache_quotation(ttl_seconds: int = QUOTATION_CACHE_TTL):
    """Decorator to cache quotation intelligence results."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            cache = get_cache_service()
            
            # Generate cache key (include user_token and company_code for isolation)
            func_name = func.__name__
            user_suffix = self.user_token[:8] if self.user_token else "no_token"
            company_suffix = self.company_code if self.company_code else "no_company"
            cache_str = f"quotation:{user_suffix}:{company_suffix}:{func_name}:{str(args)}:{str(sorted(kwargs.items()))}"
            cache_key = hashlib.md5(cache_str.encode()).hexdigest()
            
            # Check cache
            cached = cache.get_simple(cache_key)
            if cached is not None:
                logger.debug(f"⚡ Quotation cache hit: {func_name}")
                return cached
            
            # Execute function
            result = func(self, *args, **kwargs)
            
            # Cache result
            if result:
                cache.set_simple(cache_key, result, ttl=ttl_seconds)
            
            return result
        return wrapper
    return decorator


class QuotationIntelligence:
    """
    Read-only quotation analytics for the Leysco AI assistant.
    Optimized with caching and async support.
    
    FIXED: Now accepts user_token and company_code to properly authenticate API calls.
    """

    def __init__(self, user_token: str = None, company_code: str = None) -> None:
        """
        Initialize QuotationIntelligence with user token and company code.
        
        Args:
            user_token: The authenticated user's Bearer token from the request
            company_code: Company code for multi-tenant URL resolution
        """
        self.user_token = user_token
        self.company_code = company_code
        
        # Create API services with the user token and company code
        if user_token:
            self.api = LeyscoAPIService(
                user_token=user_token,
                company_code=company_code
            )
            self.pricing = create_pricing_service(
                user_token=user_token,
                company_code=company_code
            )
            logger.info(f"✅ QuotationIntelligence initialized WITH user token and company_code={company_code}")
        else:
            self.api = LeyscoAPIService()  # Will fail but at least initialized
            self.pricing = get_pricing_service()  # Will fail but at least initialized
            logger.warning("⚠️ QuotationIntelligence initialized WITHOUT user token - data access will fail")
        
        # Stats tracking
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "errors": 0
        }
        
        # Cache for customer resolution
        self._customer_cache = {}
        self._customer_cache_ttl = 300  # 5 minutes

    def set_user_token(self, token: str):
        """
        Update user token for this instance.
        Useful when reusing the instance across requests.
        """
        self.user_token = token
        self.api.set_user_token(token)
        if hasattr(self.pricing, 'set_user_token'):
            self.pricing.set_user_token(token)
        logger.debug("QuotationIntelligence token updated")
    
    def set_company_code(self, company_code: str):
        """
        Update company code for this instance.
        """
        self.company_code = company_code
        self.api.set_company_code(company_code)
        if hasattr(self.pricing, 'set_company_code'):
            self.pricing.set_company_code(company_code)
        logger.debug(f"QuotationIntelligence company code updated to: {company_code}")

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
    # Main entry point — called by action_router
    # ------------------------------------------------------------------

    @cache_quotation(ttl_seconds=QUOTATION_CACHE_TTL)
    def get_follow_up_report(
        self,
        customer_name: str | None = None,
        language: str = "en",
    ) -> dict[str, Any]:
        """
        Produce a follow-up intelligence report.
        Optimized with caching.

        If ``customer_name`` is provided the report is scoped to that
        customer; otherwise it covers all customers.

        Returns
        -------
        {
            "stale_quotations":        [...],
            "unconverted_customers":   [...],
            "conversion_rate":         {...},
            "customer_name":           str | None,
            "generated_at":            str,
            "summary_line":            str,
        }
        """
        customer_code: str | None = None
        resolved_name: str | None = None

        if customer_name:
            # Check customer cache
            if customer_name in self._customer_cache:
                cache_time = self._customer_cache.get(f"{customer_name}_time")
                if cache_time and (datetime.now() - cache_time).seconds < self._customer_cache_ttl:
                    customer_code = self._customer_cache[customer_name].get("CardCode")
                    resolved_name = self._customer_cache[customer_name].get("CardName", customer_name)
            
            if not customer_code:
                self._record_api_call()
                customer = self.api.resolve_customer(customer_name)
                if customer:
                    customer_code = customer.get("CardCode")
                    resolved_name = customer.get("CardName", customer_name)
                    # Cache customer
                    self._customer_cache[customer_name] = customer
                    self._customer_cache[f"{customer_name}_time"] = datetime.now()
                else:
                    return {
                        "error": True,
                        "message": (
                            f"Customer '{customer_name}' not found."
                            if language == "en"
                            else f"Mteja '{customer_name}' hakupatikana."
                        ),
                    }

        stale = self.get_stale_quotations(customer_code=customer_code)
        unconverted = self.get_unconverted_customers(customer_code=customer_code)
        conversion = self.get_conversion_rate(customer_code=customer_code)

        summary_line = self._build_summary(stale, unconverted, conversion, resolved_name or customer_name, language)

        return {
            "stale_quotations":      stale[:MAX_RESULTS],
            "unconverted_customers": unconverted[:MAX_RESULTS],
            "conversion_rate":       conversion,
            "customer_name":         resolved_name or customer_name,
            "generated_at":          datetime.now().isoformat(timespec="seconds"),
            "summary_line":          summary_line,
        }

    async def get_follow_up_report_async(
        self,
        customer_name: str | None = None,
        language: str = "en",
    ) -> dict[str, Any]:
        """Async version of get_follow_up_report."""
        return await asyncio.to_thread(self.get_follow_up_report, customer_name, language)

    # ------------------------------------------------------------------
    # 1. Stale quotations (Cached)
    # ------------------------------------------------------------------

    @cache_quotation(ttl_seconds=QUOTATION_CACHE_TTL)
    def get_stale_quotations(
        self,
        customer_code: str | None = None,
        stale_days: int = STALE_QUOTE_DAYS,
    ) -> list[dict[str, Any]]:
        """
        Return open quotations that have had no activity for ``stale_days``+.
        Sorted oldest-first (most urgent follow-up at the top).
        """
        try:
            self._record_api_call()
            raw = self.api.search_documents(
                doc_type=SAP_DOC_TYPE_QUOTE,
                status=SAP_DOC_OPEN,
                customer_code=customer_code,
                per_page=100,
            )
        except Exception as exc:
            self._record_error()
            logger.error(f"QuotationIntelligence.get_stale_quotations failed: {exc}")
            return []

        cutoff = datetime.now() - timedelta(days=stale_days)
        stale: list[dict] = []

        for q in raw:
            doc_date_str = q.get("DocDate") or ""
            if not doc_date_str:
                continue
            try:
                doc_date = datetime.strptime(doc_date_str[:10], "%Y-%m-%d")
            except ValueError:
                continue

            age_days = (datetime.now() - doc_date).days
            if age_days < stale_days:
                continue

            stale.append({
                "doc_num":       q.get("DocNum"),
                "customer_code": q.get("CardCode"),
                "customer_name": q.get("CardName") or "Unknown",
                "doc_date":      doc_date_str[:10],
                "age_days":      age_days,
                "total_value":   _safe_float(q.get("DocTotal")),
                "valid_until":   (q.get("DocDueDate") or "")[:10],
                "urgency":       "HIGH" if age_days >= stale_days * 2 else "MEDIUM",
                "label": (
                    f"Q-{q.get('DocNum')} · "
                    f"{q.get('CardName', 'Unknown')} · "
                    f"{age_days} days old · "
                    f"KES {_safe_float(q.get('DocTotal')):,.0f}"
                ),
            })

        stale.sort(key=lambda x: x["age_days"], reverse=True)
        logger.info(f"Stale quotations found: {len(stale)}")
        return stale

    # ------------------------------------------------------------------
    # 2. Unconverted customers (Cached)
    # ------------------------------------------------------------------

    @cache_quotation(ttl_seconds=QUOTATION_CACHE_TTL)
    def get_unconverted_customers(
        self,
        customer_code: str | None = None,
        follow_up_days: int = FOLLOW_UP_DAYS,
    ) -> list[dict[str, Any]]:
        """
        Find customers who received a quotation but have NOT placed an
        order in the last ``follow_up_days`` days.
        """
        try:
            self._record_api_call()
            raw_quotes = self.api.search_documents(
                doc_type=SAP_DOC_TYPE_QUOTE,
                status=SAP_DOC_OPEN,
                customer_code=customer_code,
                per_page=100,
            )
        except Exception as exc:
            self._record_error()
            logger.error(f"QuotationIntelligence.get_unconverted_customers failed: {exc}")
            return []

        # Build a map: card_code → most recent quote info
        customers_with_quotes: dict[str, dict] = {}
        for q in raw_quotes:
            code = q.get("CardCode")
            if not code:
                continue
            existing = customers_with_quotes.get(code)
            doc_date = (q.get("DocDate") or "")[:10]
            if not existing or doc_date > existing.get("last_quote_date", ""):
                customers_with_quotes[code] = {
                    "customer_code": code,
                    "customer_name": q.get("CardName") or "Unknown",
                    "last_quote_date": doc_date,
                    "last_quote_num":  q.get("DocNum"),
                    "last_quote_value": _safe_float(q.get("DocTotal")),
                    "open_quote_count": 1,
                }
            else:
                existing["open_quote_count"] = existing.get("open_quote_count", 1) + 1

        if not customers_with_quotes:
            return []

        # Check each customer for recent orders
        cutoff_date = (datetime.now() - timedelta(days=follow_up_days)).strftime("%Y-%m-%d")
        unconverted: list[dict] = []

        for code, info in customers_with_quotes.items():
            try:
                self._record_api_call()
                recent_orders = self.api.search_documents(
                    doc_type=SAP_DOC_TYPE_ORDER,
                    customer_code=code,
                    date_from=cutoff_date,
                    per_page=5,
                )
            except Exception:
                recent_orders = []

            if not recent_orders:
                days_since_quote = (
                    datetime.now() -
                    datetime.strptime(info["last_quote_date"], "%Y-%m-%d")
                ).days if info["last_quote_date"] else 0

                info["days_since_last_quote"] = days_since_quote
                info["label"] = (
                    f"{info['customer_name']} — "
                    f"{info['open_quote_count']} open quote(s) · "
                    f"no order in {follow_up_days} days"
                )
                unconverted.append(info)

        unconverted.sort(key=lambda x: x.get("days_since_last_quote", 0), reverse=True)
        logger.info(f"Unconverted customers found: {len(unconverted)}")
        return unconverted

    # ------------------------------------------------------------------
    # 3. Conversion rate (Cached)
    # ------------------------------------------------------------------

    @cache_quotation(ttl_seconds=QUOTATION_CACHE_TTL)
    def get_conversion_rate(
        self,
        customer_code: str | None = None,
        lookback_days: int = 90,
    ) -> dict[str, Any]:
        """
        Calculate quotation-to-order conversion rate over the last
        ``lookback_days`` days.
        """
        from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        try:
            self._record_api_call()
            quotes = self.api.search_documents(
                doc_type=SAP_DOC_TYPE_QUOTE,
                customer_code=customer_code,
                date_from=from_date,
                per_page=200,
            )
            orders = self.api.search_documents(
                doc_type=SAP_DOC_TYPE_ORDER,
                customer_code=customer_code,
                date_from=from_date,
                per_page=200,
            )
        except Exception as exc:
            self._record_error()
            logger.error(f"QuotationIntelligence.get_conversion_rate failed: {exc}")
            quotes, orders = [], []

        total = len(quotes)
        placed = len(orders)

        if total == 0:
            rate = 0.0
            interpretation = "No quotations in period"
        else:
            rate = min(placed / total * 100, 100.0)
            if rate >= 70:
                interpretation = "Excellent conversion"
            elif rate >= 50:
                interpretation = "Good conversion"
            elif rate >= 30:
                interpretation = "Needs improvement"
            else:
                interpretation = "Low — consider follow-up strategy"

        return {
            "rate_pct":      round(rate, 1),
            "converted":     placed,
            "total_quotes":  total,
            "lookback_days": lookback_days,
            "customer_code": customer_code,
            "interpretation": interpretation,
        }

    # ------------------------------------------------------------------
    # 4. Quotation Validation for Creation (Cached)
    # ------------------------------------------------------------------

    @cache_quotation(ttl_seconds=VALIDATION_CACHE_TTL)
    def validate_quotation_items(
        self,
        items: list[dict],
        customer_code: str,
        language: str = "en",
    ) -> dict[str, Any]:
        """
        Validate items before creating a quotation.
        Checks:
        - Items exist in system
        - Items are sellable (not packing materials)
        - Items have valid prices
        - Quantities are positive
        """
        SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL", "PACKAGING"}
        SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK", "PACK", "BAG", "BOX", "LABEL")
        SKIP_NAME_TERMS = ("LABEL", "PACK", "BAG", "BOX", "STICKER", "SLEEVE")
        
        valid_items = []
        invalid_items = []
        
        for idx, item in enumerate(items):
            item_code = item.get("ItemCode")
            item_name = item.get("ItemName", "Unknown")
            quantity = item.get("Quantity", 1)
            
            # Check quantity
            if quantity <= 0:
                invalid_items.append({
                    "code": item_code,
                    "name": item_name,
                    "reason": "Invalid quantity (must be greater than 0)",
                    "index": idx
                })
                continue
            
            # Get full item details
            self._record_api_call()
            full_item = self.api.get_item_by_code(item_code) if item_code else None
            
            if not full_item:
                invalid_items.append({
                    "code": item_code,
                    "name": item_name,
                    "reason": "Item not found in system",
                    "index": idx
                })
                continue
            
            # Check if sellable
            is_sellable = full_item.get("SellItem") == "Y"
            item_group = (full_item.get("item_group") or {}).get("ItmsGrpNam", "").upper()
            item_name_upper = full_item.get("ItemName", "").upper()
            
            # Check if it's packing/raw material
            is_packing = (
                item_group in SKIP_GROUPS or
                any(item_code.startswith(p) for p in SKIP_PREFIXES) or
                any(term in item_name_upper for term in SKIP_NAME_TERMS)
            )
            
            if not is_sellable or is_packing:
                invalid_items.append({
                    "code": item_code,
                    "name": full_item.get("ItemName", item_name),
                    "reason": f"Item not sellable (Group: {item_group})",
                    "index": idx
                })
                continue
            
            # Get price
            try:
                price_result = self.pricing.get_price_for_customer(
                    item_code=item_code,
                    customer={"CardCode": customer_code}
                )
                price = price_result.get("price", 0) if price_result.get("found") else 0
            except Exception as e:
                logger.warning(f"Could not get price for {item_code}: {e}")
                price = 0
            
            if price <= 0:
                invalid_items.append({
                    "code": item_code,
                    "name": full_item.get("ItemName", item_name),
                    "reason": "No price configured for this customer",
                    "index": idx
                })
                continue
            
            # Item is valid
            valid_items.append({
                "ItemCode": item_code,
                "ItemName": full_item.get("ItemName", item_name),
                "Quantity": quantity,
                "Price": price,
                "LineTotal": quantity * price,
                "ItemGroup": item_group,
                "IsSellable": is_sellable
            })
        
        return {
            "valid_items": valid_items,
            "invalid_items": invalid_items,
            "total_valid": len(valid_items),
            "total_invalid": len(invalid_items),
            "valid": len(invalid_items) == 0
        }

    # ------------------------------------------------------------------
    # 5. Quotation Suggestions (Cached)
    # ------------------------------------------------------------------

    @cache_quotation(ttl_seconds=QUOTATION_CACHE_TTL)
    def get_quotation_suggestions(
        self,
        customer_code: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Suggest items that this customer frequently buys.
        Helps sales reps create quotations faster.
        """
        try:
            # Get customer details
            customer = self.api.get_customer_by_code(customer_code)
            if not customer:
                return []
            
            # Get customer's order history
            self._record_api_call()
            orders = self.api.get_customer_orders(
                customer_name=customer.get("CardName", ""),
                limit=20,
                include_details=True
            )
            
            if not orders:
                return []
            
            # Extract frequently purchased items
            item_counts = {}
            for order in orders:
                lines = order.get("DocumentLines", [])
                for line in lines:
                    code = line.get("ItemCode")
                    if code:
                        item_counts[code] = item_counts.get(code, 0) + 1
            
            # Get top items
            top_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
            
            suggestions = []
            for code, count in top_items:
                self._record_api_call()
                item = self.api.get_item_by_code(code)
                if item and item.get("SellItem") == "Y":
                    suggestions.append({
                        "ItemCode": code,
                        "ItemName": item.get("ItemName", code),
                        "Frequency": count,
                        "LastOrdered": "Recent"
                    })
            
            return suggestions
            
        except Exception as e:
            self._record_error()
            logger.error(f"Failed to get quotation suggestions: {e}")
            return []

    # ------------------------------------------------------------------
    # Formatting helpers for action_router
    # ------------------------------------------------------------------

    def format_report_message(
        self,
        report: dict[str, Any],
        language: str = "en",
    ) -> str:
        """
        Convert a get_follow_up_report() result into a chat-ready string.
        Called by action_router after get_follow_up_report().
        """
        if report.get("error"):
            return report.get("message", "Error generating report.")

        stale = report.get("stale_quotations", [])
        unconverted = report.get("unconverted_customers", [])
        conversion = report.get("conversion_rate", {})
        customer = report.get("customer_name")

        if language == "sw":
            scope = f"kwa **{customer}**" if customer else "kwa wateja wote"
            lines = [f"📋 **Ripoti ya Ufuatiliaji wa Nukuu** {scope}\n"]

            if stale:
                lines.append(f"⏰ **Nukuu Zilizo Wazi Zaidi ya Siku {STALE_QUOTE_DAYS}** ({len(stale)}):\n")
                for q in stale[:5]:
                    lines.append(
                        f"  • Q-{q['doc_num']} · {q['customer_name']} · "
                        f"siku {q['age_days']} · KES {q['total_value']:,.0f}"
                    )
                if len(stale) > 5:
                    lines.append(f"  ... na nyingine {len(stale) - 5}\n")
            else:
                lines.append("✅ Hakuna nukuu zilizo wazi kwa muda mrefu.\n")

            if unconverted:
                lines.append(f"\n👥 **Wateja Wenye Nukuu Bila Oda** ({len(unconverted)}):\n")
                for c in unconverted[:5]:
                    lines.append(
                        f"  • {c['customer_name']} — nukuu {c['open_quote_count']} wazi"
                    )
                if len(unconverted) > 5:
                    lines.append(f"  ... na wengine {len(unconverted) - 5}\n")
            else:
                lines.append("\n✅ Wateja wote waliokuwa na nukuu wameweka oda hivi karibuni.\n")

            lines.append(
                f"\n📊 **Kiwango cha Ubadilishaji:** "
                f"{conversion.get('rate_pct', 0)}% "
                f"({conversion.get('converted', 0)} oda / {conversion.get('total_quotes', 0)} nukuu "
                f"katika siku {conversion.get('lookback_days', 90)} zilizopita) — "
                f"{conversion.get('interpretation', '')}"
            )

        else:
            scope = f"for **{customer}**" if customer else "across all customers"
            lines = [f"📋 **Quotation Follow-up Report** {scope}\n"]

            if stale:
                lines.append(f"⏰ **Stale Open Quotations (>{STALE_QUOTE_DAYS} days)** — {len(stale)} found:\n")
                for q in stale[:5]:
                    urgency_icon = "🔴" if q["urgency"] == "HIGH" else "🟡"
                    lines.append(
                        f"  {urgency_icon} Q-{q['doc_num']} · "
                        f"{q['customer_name']} · "
                        f"{q['age_days']} days old · "
                        f"KES {q['total_value']:,.0f}"
                    )
                if len(stale) > 5:
                    lines.append(f"  ... and {len(stale) - 5} more\n")
            else:
                lines.append("✅ No stale open quotations found.\n")

            if unconverted:
                lines.append(
                    f"\n👥 **Customers with Quotes but No Recent Order** — {len(unconverted)} found:\n"
                )
                for c in unconverted[:5]:
                    lines.append(
                        f"  • {c['customer_name']} — "
                        f"{c['open_quote_count']} open quote(s), "
                        f"no order in {FOLLOW_UP_DAYS} days"
                    )
                if len(unconverted) > 5:
                    lines.append(f"  ... and {len(unconverted) - 5} more\n")
            else:
                lines.append(
                    "\n✅ All customers with recent quotes have placed orders.\n"
                )

            lines.append(
                f"\n📊 **Conversion Rate:** "
                f"{conversion.get('rate_pct', 0)}% "
                f"({conversion.get('converted', 0)} orders / "
                f"{conversion.get('total_quotes', 0)} quotes in last "
                f"{conversion.get('lookback_days', 90)} days) — "
                f"{conversion.get('interpretation', '')}"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        stale: list,
        unconverted: list,
        conversion: dict,
        customer_name: str | None,
        language: str,
    ) -> str:
        """One-liner for the Flutter dashboard card."""
        stale_count = len(stale)
        unc_count = len(unconverted)
        rate = conversion.get("rate_pct", 0)

        if language == "sw":
            parts = []
            if stale_count:
                parts.append(f"{stale_count} nukuu za zamani")
            if unc_count:
                parts.append(f"{unc_count} wateja bila oda")
            parts.append(f"ubadilishaji {rate}%")
            return " · ".join(parts)

        parts = []
        if stale_count:
            parts.append(f"{stale_count} stale quote(s)")
        if unc_count:
            parts.append(f"{unc_count} customer(s) to follow up")
        parts.append(f"{rate}% conversion rate")
        return " · ".join(parts)

    # ------------------------------------------------------------------
    # Cache Management
    # ------------------------------------------------------------------

    def clear_cache(self):
        """Clear all caches."""
        self._customer_cache.clear()
        logger.info("Quotation intelligence cache cleared")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# FIXED: Removed singleton pattern - now creates fresh instance per request
# ---------------------------------------------------------------------------

def create_quotation_intelligence(user_token: str = None, company_code: str = None) -> QuotationIntelligence:
    """
    Create a new QuotationIntelligence instance with the user's token and company code.
    Called per request to ensure proper authentication isolation.
    
    Args:
        user_token: The authenticated user's Bearer token from the request
        company_code: Company code for multi-tenant URL resolution
    
    Returns:
        Configured QuotationIntelligence instance
    
    Example:
        qi = create_quotation_intelligence(user_token=request_token, company_code="TEST001")
        report = qi.get_follow_up_report()
    """
    if not user_token:
        logger.warning("Creating QuotationIntelligence without user token - data access will fail")
    return QuotationIntelligence(user_token=user_token, company_code=company_code)


# ---------------------------------------------------------------------------
# DEPRECATED: Old singleton accessor - kept for backward compatibility
# but will log a warning. Use create_quotation_intelligence() instead.
# ---------------------------------------------------------------------------

_qi_instance: QuotationIntelligence | None = None


def get_quotation_intelligence(user_token: str = None, company_code: str = None) -> QuotationIntelligence:
    """
    DEPRECATED: Old singleton accessor. Use create_quotation_intelligence() instead.
    
    This function is kept for backward compatibility but will log a warning.
    For new code, use create_quotation_intelligence(user_token=token, company_code=company_code) to create
    a fresh instance per request.
    
    If user_token is provided, it will update the singleton's token (but this
    is not recommended for multi-tenant applications).
    """
    import warnings
    warnings.warn(
        "get_quotation_intelligence() is deprecated. Use create_quotation_intelligence(user_token=token, company_code=company_code) instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    global _qi_instance
    if _qi_instance is None:
        _qi_instance = QuotationIntelligence(user_token=user_token, company_code=company_code)
        logger.warning("Using deprecated singleton pattern - create fresh instances per request for better isolation")
    elif user_token and _qi_instance.user_token != user_token:
        _qi_instance.set_user_token(user_token)
        logger.debug("Updated deprecated singleton with new token")
    elif company_code and _qi_instance.company_code != company_code:
        _qi_instance.set_company_code(company_code)
        logger.debug("Updated deprecated singleton with new company code")
    
    return _qi_instance