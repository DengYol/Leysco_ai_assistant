"""
app/services/dashboard_service.py
===================================
Proactive Dashboard Service - Optimized with caching and async support

Called once when the Flutter app opens. Runs all alert checks in
parallel (using threads) and returns a single structured payload so
the home screen can immediately show the rep what needs attention.

Alerts surfaced
---------------
1. Critical / low stock items       (WarehouseService.get_low_stock_alerts)
2. Deliveries due today or overdue  (DeliveryTrackingService across all customers)
3. Stale quotations (7+ days open)  (LeyscoAPIService marketing docs)
4. Top 3 trending products          (LeyscoAPIService top items)

Each alert section is independent — a failure in one section never
blocks the others from returning.

Optimizations:
- Redis caching for dashboard data
- Async support for concurrent section loading
- Better error handling with fallbacks
- Configurable cache TTLs

MODIFIED FOR PHASE 1: Accepts user token and passes to all services
"""

from __future__ import annotations

import logging
import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from functools import wraps

from app.services.leysco_api_service import LeyscoAPIService, create_api_service
from app.services.warehouse_service import WarehouseService, create_warehouse_service
from app.services.delivery_tracking_service import DeliveryTrackingService
from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# How long (seconds) each section is allowed before we give up on it
_SECTION_TIMEOUT = 8

# Quotations older than this are considered stale
_STALE_QUOTE_DAYS = 7

# How many items to surface per section
_MAX_STOCK_ALERTS   = 5
_MAX_DELIVERIES     = 5
_MAX_STALE_QUOTES   = 5
_MAX_TRENDING       = 3

# Cache TTL for dashboard data (5 minutes)
DASHBOARD_CACHE_TTL = 300


def cache_dashboard(ttl_seconds: int = DASHBOARD_CACHE_TTL):
    """Decorator to cache dashboard results."""
    def decorator(func):
        @wraps(func)
        def wrapper(self):
            cache = get_cache_service()
            
            # Generate cache key (include user token for isolation)
            user_suffix = self.user_token[:8] if self.user_token else "no_token"
            cache_key = f"dashboard:{user_suffix}:{datetime.now().strftime('%Y-%m-%d-%H')}"  # Hourly cache
            
            # Check cache
            cached = cache.get_simple(cache_key)
            if cached is not None:
                logger.info("⚡ Dashboard cache hit")
                return cached
            
            # Execute function
            result = func(self)
            
            # Cache result
            if result:
                cache.set_simple(cache_key, result, ttl=ttl_seconds)
            
            return result
        return wrapper
    return decorator


class DashboardService:
    """
    Aggregates proactive business alerts for the Flutter home screen.
    Optimized with caching and async support.
    
    MODIFIED: Now accepts user_token to properly authenticate API calls.
    """

    def __init__(self, user_token: str = None) -> None:
        """
        Initialize DashboardService with user token.
        
        Args:
            user_token: Bearer token from authenticated user
        """
        self.user_token = user_token
        
        # Create API services with the user token
        if user_token:
            self.api = create_api_service(user_token)
            self.warehouse = create_warehouse_service(user_token)
            logger.debug("DashboardService initialized with user token")
        else:
            logger.warning("DashboardService initialized WITHOUT user token - API calls will fail")
            self.api = LeyscoAPIService()
            self.warehouse = WarehouseService()
        
        self.delivery = DeliveryTrackingService(api_service=self.api)
        
        # Stats tracking
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "errors": 0
        }
        
        # Cache for individual sections
        self._section_cache = {}
        self._section_cache_time = {}
        self._section_cache_ttl = 120  # 2 minutes

    def set_user_token(self, token: str):
        """Update user token for this instance."""
        self.user_token = token
        self.api.set_user_token(token)
        self.warehouse.set_user_token(token)
        logger.debug("DashboardService user token updated")

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
    # Public entry point
    # ------------------------------------------------------------------

    @cache_dashboard(ttl_seconds=DASHBOARD_CACHE_TTL)
    def get_dashboard(self) -> dict[str, Any]:
        """
        Run all alert sections concurrently and return the merged payload.
        Optimized with caching (5 minute TTL).
        """
        sections = {
            "stock":      self._stock_alerts,
            "deliveries": self._delivery_alerts,
            "quotations": self._quotation_alerts,
            "trending":   self._trending_alerts,
        }

        results: dict[str, Any] = {}
        errors: list[str] = []

        # Run all four sections concurrently
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="dashboard") as pool:
            futures = {pool.submit(fn): name for name, fn in sections.items()}

            for future in as_completed(futures, timeout=_SECTION_TIMEOUT + 2):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=_SECTION_TIMEOUT)
                    logger.info(f"Dashboard section '{name}' completed")
                except TimeoutError:
                    self._record_error()
                    logger.warning(f"Dashboard section '{name}' timed out")
                    results[name] = _empty_section(name)
                    errors.append(f"{name}: timeout")
                except Exception as exc:
                    self._record_error()
                    logger.error(f"Dashboard section '{name}' failed: {exc}")
                    results[name] = _empty_section(name)
                    errors.append(f"{name}: {exc}")

        # Top-level metric counts for the Flutter header cards
        metrics = {
            "critical_stock_count": results.get("stock", {}).get("critical_count", 0),
            "deliveries_due_today": results.get("deliveries", {}).get("due_today_count", 0),
            "stale_quote_count":    results.get("quotations", {}).get("stale_count", 0),
        }

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "alerts":       results,
            "metrics":      metrics,
            "errors":       errors,
        }

    async def get_dashboard_async(self) -> dict[str, Any]:
        """Async version of get_dashboard."""
        return await asyncio.to_thread(self.get_dashboard)

    # ------------------------------------------------------------------
    # Section 1: Stock alerts (Cached)
    # ------------------------------------------------------------------

    def _stock_alerts(self) -> dict[str, Any]:
        """
        Return critical and low-stock items across all warehouses.
        Optimized with section-level caching.
        """
        # Check section cache (include user token for isolation)
        user_suffix = self.user_token[:8] if self.user_token else "no_token"
        cache_key = f"stock_alerts:{user_suffix}"
        
        if cache_key in self._section_cache:
            cache_time = self._section_cache_time.get(cache_key)
            if cache_time and (datetime.now() - cache_time).seconds < self._section_cache_ttl:
                self._record_cache_hit()
                return self._section_cache[cache_key]
        
        self._record_cache_miss()
        self._record_api_call()
        
        all_alerts = self.warehouse.get_low_stock_alerts(
            threshold_pct=0.10,
            min_available=50,
        )

        critical = [a for a in all_alerts if a.get("Severity") == "CRITICAL"]
        low = [a for a in all_alerts if a.get("Severity") == "LOW"]

        # Surface at most _MAX_STOCK_ALERTS items, critical first
        top = (critical + low)[:_MAX_STOCK_ALERTS]

        result = {
            "section":        "stock",
            "critical_count": len(critical),
            "low_count":      len(low),
            "total_alerts":   len(all_alerts),
            "items": [
                {
                    "item_code":   a["ItemCode"],
                    "item_name":   a["ItemName"],
                    "warehouse":   a["WhsCode"],
                    "available":   a["Available"],
                    "on_hand":     a["OnHand"],
                    "severity":    a["Severity"],
                    "label": (
                        f"{a['ItemName']} — {a['Available']} units left"
                        if a["Available"] > 0
                        else f"{a['ItemName']} — OUT OF STOCK"
                    ),
                }
                for a in top
            ],
            "suggestion": "Show low stock alerts",
        }
        
        # Cache the result
        self._section_cache[cache_key] = result
        self._section_cache_time[cache_key] = datetime.now()
        
        return result

    # ------------------------------------------------------------------
    # Section 2: Deliveries due today / overdue (Cached)
    # ------------------------------------------------------------------

    def _delivery_alerts(self) -> dict[str, Any]:
        """
        Find deliveries that are due today or already overdue.
        Optimized with section-level caching.
        """
        # Check section cache (include user token for isolation)
        user_suffix = self.user_token[:8] if self.user_token else "no_token"
        cache_key = f"delivery_alerts:{user_suffix}"
        
        if cache_key in self._section_cache:
            cache_time = self._section_cache_time.get(cache_key)
            if cache_time and (datetime.now() - cache_time).seconds < self._section_cache_ttl:
                self._record_cache_hit()
                return self._section_cache[cache_key]
        
        self._record_cache_miss()
        self._record_api_call()
        
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)

        # Fetch open delivery documents via search_documents()
        # doc_type 15 = Deliveries in SAP B1, status=1 = Open
        try:
            raw_docs = self.api.search_documents(
                doc_type=15,
                status=1,
                per_page=100,
            )
        except Exception as exc:
            self._record_error()
            logger.warning(f"Could not fetch delivery docs for dashboard: {exc}")
            raw_docs = []

        due_today: list[dict] = []
        overdue: list[dict] = []

        for doc in raw_docs:
            due_str = doc.get("DocDueDate") or doc.get("ShipDate") or ""
            if not due_str:
                continue
            try:
                due_date = datetime.strptime(due_str[:10], "%Y-%m-%d").date()
            except ValueError:
                continue

            entry = {
                "doc_num":       doc.get("DocNum"),
                "customer_code": doc.get("CardCode"),
                "customer_name": doc.get("CardName"),
                "due_date":      due_str[:10],
                "total_value":   doc.get("DocTotal"),
                "status":        self.delivery._determine_delivery_status(doc),
                "label": (
                    f"{doc.get('CardName', 'Unknown')} — due today"
                    if due_date == today
                    else f"{doc.get('CardName', 'Unknown')} — overdue {(today - due_date).days}d"
                ),
            }

            if due_date < today:
                overdue.append(entry)
            elif due_date == today:
                due_today.append(entry)

        # Sort overdue by how many days late (worst first)
        overdue.sort(key=lambda d: d["due_date"])

        top = (overdue + due_today)[:_MAX_DELIVERIES]

        result = {
            "section":         "deliveries",
            "overdue_count":   len(overdue),
            "due_today_count": len(due_today),
            "total_alerts":    len(overdue) + len(due_today),
            "deliveries":      top,
            "suggestion":      "Track deliveries due today",
        }
        
        # Cache the result
        self._section_cache[cache_key] = result
        self._section_cache_time[cache_key] = datetime.now()
        
        return result

    # ------------------------------------------------------------------
    # Section 3: Stale quotations (Cached)
    # ------------------------------------------------------------------

    def _quotation_alerts(self) -> dict[str, Any]:
        """
        Find open quotations with no activity for _STALE_QUOTE_DAYS+ days.
        Optimized with section-level caching.
        """
        # Check section cache (include user token for isolation)
        user_suffix = self.user_token[:8] if self.user_token else "no_token"
        cache_key = f"quotation_alerts:{user_suffix}"
        
        if cache_key in self._section_cache:
            cache_time = self._section_cache_time.get(cache_key)
            if cache_time and (datetime.now() - cache_time).seconds < self._section_cache_ttl:
                self._record_cache_hit()
                return self._section_cache[cache_key]
        
        self._record_cache_miss()
        self._record_api_call()
        
        cutoff = datetime.now() - timedelta(days=_STALE_QUOTE_DAYS)

        # Fetch open quotations via search_documents()
        # doc_type 23 = Quotations in SAP B1, status=1 = Open
        try:
            raw_quotes = self.api.search_documents(
                doc_type=23,
                status=1,
                per_page=100,
            )
        except Exception as exc:
            self._record_error()
            logger.warning(f"Could not fetch quotations for dashboard: {exc}")
            raw_quotes = []

        stale: list[dict] = []

        for q in raw_quotes:
            doc_date_str = q.get("DocDate") or ""
            if not doc_date_str:
                continue
            try:
                doc_date = datetime.strptime(doc_date_str[:10], "%Y-%m-%d")
            except ValueError:
                continue

            age_days = (datetime.now() - doc_date).days
            if age_days >= _STALE_QUOTE_DAYS:
                stale.append({
                    "doc_num":       q.get("DocNum"),
                    "customer_code": q.get("CardCode"),
                    "customer_name": q.get("CardName"),
                    "doc_date":      doc_date_str[:10],
                    "age_days":      age_days,
                    "total_value":   q.get("DocTotal"),
                    "label": (
                        f"{q.get('CardName', 'Unknown')} — "
                        f"Quote #{q.get('DocNum')} open {age_days} days"
                    ),
                })

        # Oldest first (most urgent follow-up)
        stale.sort(key=lambda q: q["age_days"], reverse=True)
        top = stale[:_MAX_STALE_QUOTES]

        result = {
            "section":      "quotations",
            "stale_count":  len(stale),
            "quotations":   top,
            "suggestion":   "Show stale quotations",
        }
        
        # Cache the result
        self._section_cache[cache_key] = result
        self._section_cache_time[cache_key] = datetime.now()
        
        return result

    # ------------------------------------------------------------------
    # Section 4: Trending products (Cached)
    # ------------------------------------------------------------------

    def _trending_alerts(self) -> dict[str, Any]:
        """
        Return the top selling items from the last 30 days.
        Optimized with section-level caching.
        """
        # Check section cache (include user token for isolation)
        user_suffix = self.user_token[:8] if self.user_token else "no_token"
        cache_key = f"trending_alerts:{user_suffix}"
        
        if cache_key in self._section_cache:
            cache_time = self._section_cache_time.get(cache_key)
            if cache_time and (datetime.now() - cache_time).seconds < self._section_cache_ttl:
                self._record_cache_hit()
                return self._section_cache[cache_key]
        
        self._record_cache_miss()
        self._record_api_call()
        
        try:
            raw = self.api.get_top_selling_items(days=30, limit=_MAX_TRENDING)
        except Exception as exc:
            self._record_error()
            logger.warning(f"Could not fetch trending items for dashboard: {exc}")
            raw = []

        items = []
        for item in raw[:_MAX_TRENDING]:
            items.append({
                "item_code":     item.get("ItemCode"),
                "item_name":     item.get("ItemName") or item.get("name"),
                "quantity_sold": item.get("QuantitySold") or item.get("quantity"),
                "revenue":       item.get("Revenue") or item.get("revenue"),
                "label":         item.get("ItemName") or item.get("name", "Unknown item"),
            })

        result = {
            "section":     "trending",
            "items":       items,
            "period_days": 30,
            "suggestion":  "Recommend top products to sell today",
        }
        
        # Cache the result
        self._section_cache[cache_key] = result
        self._section_cache_time[cache_key] = datetime.now()
        
        return result

    # ------------------------------------------------------------------
    # Cache Management
    # ------------------------------------------------------------------

    def clear_cache(self):
        """Clear all caches."""
        self._section_cache = {}
        self._section_cache_time = {}
        
        # Clear Redis cache
        cache = get_cache_service()
        
        logger.info("Dashboard service cache cleared")
        self._stats["cache_hits"] = 0
        self._stats["cache_misses"] = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_section(name: str) -> dict[str, Any]:
    """Return a safe empty payload when a section fails or times out."""
    base: dict[str, Any] = {"section": name, "error": True}
    if name == "stock":
        base.update({"critical_count": 0, "low_count": 0, "total_alerts": 0, "items": []})
    elif name == "deliveries":
        base.update({"overdue_count": 0, "due_today_count": 0, "total_alerts": 0, "deliveries": []})
    elif name == "quotations":
        base.update({"stale_count": 0, "quotations": []})
    elif name == "trending":
        base.update({"items": []})
    return base


# ---------------------------------------------------------------------------
# Factory function - creates fresh instance per request
# ---------------------------------------------------------------------------

def create_dashboard_service(user_token: str = None) -> DashboardService:
    """
    Create a new DashboardService instance with the user's token.
    
    Args:
        user_token: The authenticated user's Bearer token
    
    Returns:
        Configured DashboardService instance
    """
    if not user_token:
        logger.warning("⚠️ create_dashboard_service called WITHOUT user token - data access will fail")
    else:
        logger.info("✅ create_dashboard_service called WITH user token")
    
    return DashboardService(user_token=user_token)


# ---------------------------------------------------------------------------
# DEPRECATED: Old singleton accessor - kept for backward compatibility
# ---------------------------------------------------------------------------

_dashboard_instance: DashboardService | None = None


def get_dashboard_service(user_token: str = None) -> DashboardService:
    """
    DEPRECATED: Old singleton accessor. Use create_dashboard_service() instead.
    
    This function is kept for backward compatibility but will log a warning.
    For new code, use create_dashboard_service(user_token=token) to create
    a fresh instance per request.
    """
    import warnings
    warnings.warn(
        "get_dashboard_service() is deprecated. Use create_dashboard_service(user_token=token) instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    global _dashboard_instance
    if _dashboard_instance is None:
        _dashboard_instance = DashboardService(user_token=user_token)
        logger.warning("Using deprecated singleton pattern - create fresh instances per request for better isolation")
    elif user_token and _dashboard_instance.user_token != user_token:
        _dashboard_instance.set_user_token(user_token)
        logger.debug("Updated deprecated singleton with new token")
    
    return _dashboard_instance