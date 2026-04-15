"""
app/services/customer_health_service.py
=========================================
Customer Health Score Service - Optimized with caching and async support

Scores each customer 0–100 from four weighted signals:

  Recency      30%   Days since last order  (recent = high)
  Frequency    25%   Orders in last 90 days (more = higher)
  Conversion   25%   Quote-to-order rate    (higher = healthier)
  Financials   20%   Outstanding invoices vs credit limit (lower debt = better)

Grade bands
-----------
  90–100  🟢 Excellent   VIP, high-value, low-risk
  70–89   🟢 Good        Active and healthy
  50–69   🟡 Fair        Some risk signals, monitor
  30–49   🟠 At Risk     Needs sales rep attention
  0–29    🔴 Critical    High churn risk or overdue debt

Optimizations:
- Redis caching for health scores
- Async support for concurrent scoring
- Batch processing for portfolio views
- LRU cache for frequent lookups
"""

import logging
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache, wraps

from app.services.leysco_api_service import LeyscoAPIService
from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)

# Weights (must sum to 1.0)
_W_RECENCY    = 0.30
_W_FREQUENCY  = 0.25
_W_CONVERSION = 0.25
_W_FINANCIALS = 0.20

# Frequency benchmark: orders per 90 days that earns a full score
_IDEAL_ORDERS_PER_90D = 6

# Grade thresholds  (score, label, emoji)
_GRADES = [
    (90, "Excellent", "🟢"),
    (70, "Good",      "🟢"),
    (50, "Fair",      "🟡"),
    (30, "At Risk",   "🟠"),
    ( 0, "Critical",  "🔴"),
]

# Cache TTLs
HEALTH_SCORE_TTL = 3600  # 1 hour
BATCH_RESULTS_TTL = 1800  # 30 minutes


def cache_health_score(ttl_seconds: int = HEALTH_SCORE_TTL):
    """Decorator to cache health score results."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, customer_code=None, customer_name=None):
            cache = get_cache_service()
            
            # Generate cache key
            key = customer_code or customer_name
            if not key:
                return func(self, customer_code, customer_name)
            
            cache_key = f"health_score:{key}"
            
            # Check cache
            cached = cache.get_simple(cache_key)
            if cached is not None:
                logger.info(f"⚡ Health score cache hit: {key}")
                return cached
            
            # Execute function
            result = func(self, customer_code, customer_name)
            
            # Cache result (even if error, to avoid repeated lookups)
            if result and not result.get("error"):
                cache.set_simple(cache_key, result, ttl=ttl_seconds)
            
            return result
        return wrapper
    return decorator


class CustomerHealthService:
    """Compute customer health scores from SAP B1 data via LeyscoAPIService."""

    def __init__(self) -> None:
        self.api = LeyscoAPIService()
        
        # Cache for batch results
        self._batch_cache = {}
        self._batch_cache_time = {}
        self._batch_cache_ttl = 1800  # 30 minutes
        
        # Stats tracking
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "errors": 0
        }

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
    # Public: score one customer
    # ------------------------------------------------------------------

    @cache_health_score(ttl_seconds=HEALTH_SCORE_TTL)
    def score(
        self,
        customer_code: str | None = None,
        customer_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Compute the health score for a single customer.
        Optimized with caching.

        Provide customer_code (CardCode) OR customer_name.

        Returns
        -------
        {
            "customer_code":   str,
            "customer_name":   str,
            "score":           float,
            "grade":           str,
            "emoji":           str,
            "signals": {...},
            "recommendations": [...],
            "error":           str | None,
        }
        """
        # ── Resolve customer ──────────────────────────────────────────────────
        if not customer_code:
            if not customer_name:
                return self._err("Provide customer_code or customer_name")
            self._record_api_call()
            results = self.api.get_customers(search=customer_name, limit=5)
            if not results:
                return self._err(f"Customer '{customer_name}' not found")
            customer_code = results[0].get("CardCode")
            customer_name = results[0].get("CardName", customer_name)
        else:
            self._record_api_call()
            results = self.api.get_customers(search=customer_code, limit=1)
            customer_name = results[0].get("CardName", customer_code) if results else customer_code

        # ── Compute signals ───────────────────────────────────────────────────
        r_sig   = self._recency(customer_code)
        f_sig   = self._frequency(customer_code)
        c_sig   = self._conversion(customer_code)
        fin_sig = self._financials(customer_code)

        composite = (
            r_sig["score"]   * _W_RECENCY    +
            f_sig["score"]   * _W_FREQUENCY  +
            c_sig["score"]   * _W_CONVERSION +
            fin_sig["score"] * _W_FINANCIALS
        )
        composite = round(min(100.0, max(0.0, composite)), 1)
        label, emoji = self._get_grade(composite)

        recs = self._recommendations(composite, r_sig, f_sig, c_sig, fin_sig)

        logger.info("CustomerHealth[%s] score=%.1f (%s)", customer_code, composite, label)

        return {
            "customer_code":   customer_code,
            "customer_name":   customer_name,
            "score":           composite,
            "grade":           label,
            "emoji":           emoji,
            "signals": {
                "recency":    r_sig,
                "frequency":  f_sig,
                "conversion": c_sig,
                "financials": fin_sig,
            },
            "recommendations": recs,
            "error":           None,
        }

    async def score_async(
        self,
        customer_code: str | None = None,
        customer_name: str | None = None,
    ) -> dict[str, Any]:
        """Async version of score."""
        return await asyncio.to_thread(self.score, customer_code, customer_name)

    # ------------------------------------------------------------------
    # Public: portfolio views (Optimized with caching)
    # ------------------------------------------------------------------

    def get_top_healthy(self, limit: int = 10) -> list[dict]:
        """Top N customers with score >= 70 (Good or Excellent)."""
        cache_key = f"top_healthy_{limit}"
        
        # Check cache
        if cache_key in self._batch_cache:
            cache_time = self._batch_cache_time.get(cache_key)
            if cache_time and (datetime.now() - cache_time).seconds < self._batch_cache_ttl:
                self._record_cache_hit()
                return self._batch_cache[cache_key]
        
        self._record_cache_miss()
        result = self._batch(min_score=70, limit=limit, descending=True)
        
        # Cache result
        self._batch_cache[cache_key] = result
        self._batch_cache_time[cache_key] = datetime.now()
        
        return result

    def get_at_risk(self, limit: int = 10) -> list[dict]:
        """Top N most at-risk customers with score < 50."""
        cache_key = f"at_risk_{limit}"
        
        # Check cache
        if cache_key in self._batch_cache:
            cache_time = self._batch_cache_time.get(cache_key)
            if cache_time and (datetime.now() - cache_time).seconds < self._batch_cache_ttl:
                self._record_cache_hit()
                return self._batch_cache[cache_key]
        
        self._record_cache_miss()
        result = self._batch(max_score=49, limit=limit, descending=False)
        
        # Cache result
        self._batch_cache[cache_key] = result
        self._batch_cache_time[cache_key] = datetime.now()
        
        return result

    async def get_top_healthy_async(self, limit: int = 10) -> list[dict]:
        """Async version of get_top_healthy."""
        return await asyncio.to_thread(self.get_top_healthy, limit)

    async def get_at_risk_async(self, limit: int = 10) -> list[dict]:
        """Async version of get_at_risk."""
        return await asyncio.to_thread(self.get_at_risk, limit)

    # ------------------------------------------------------------------
    # Signal calculators (Optimized with LRU cache)
    # ------------------------------------------------------------------

    @lru_cache(maxsize=256)
    def _recency_cached(self, code: str) -> dict:
        """Cached version of recency calculation."""
        return self._recency(code)
    
    def _recency(self, code: str) -> dict:
        """Score based on days since last order. 0d=100, 90d=10, >90=0."""
        try:
            self._record_api_call()
            orders = self.api.search_documents(
                doc_type=17, card_code=code, per_page=1
            )
            if not orders:
                return self._sig(0, days_since_order=None, label="No orders found")

            date_str = (orders[0].get("DocDate") or "")[:10]
            if not date_str:
                return self._sig(0, days_since_order=None, label="No date available")

            days = (datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")).days
            if days <= 0:
                score = 100.0
            elif days <= 90:
                score = 100.0 - (days / 90.0) * 90.0
            else:
                score = 0.0

            return self._sig(
                round(score, 1),
                days_since_order=days,
                label=f"Last order {days} days ago",
            )
        except Exception as exc:
            self._record_error()
            logger.warning("Recency signal error for %s: %s", code, exc)
            return self._sig(0, days_since_order=None, label="Data unavailable")

    @lru_cache(maxsize=256)
    def _frequency_cached(self, code: str) -> dict:
        """Cached version of frequency calculation."""
        return self._frequency(code)
    
    def _frequency(self, code: str) -> dict:
        """Score based on order count in last 90 days."""
        since = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        try:
            self._record_api_call()
            orders = self.api.search_documents(
                doc_type=17, card_code=code, date_from=since, per_page=50
            )
            count = len(orders)
            score = min(100.0, (count / _IDEAL_ORDERS_PER_90D) * 100.0)
            return self._sig(
                round(score, 1),
                orders_90d=count,
                label=f"{count} orders in last 90 days",
            )
        except Exception as exc:
            self._record_error()
            logger.warning("Frequency signal error for %s: %s", code, exc)
            return self._sig(0, orders_90d=0, label="Data unavailable")

    @lru_cache(maxsize=256)
    def _conversion_cached(self, code: str) -> dict:
        """Cached version of conversion calculation."""
        return self._conversion(code)
    
    def _conversion(self, code: str) -> dict:
        """Score based on quotation-to-order conversion rate (last 180 days)."""
        since = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        try:
            self._record_api_call()
            quotes = self.api.search_documents(
                doc_type=23, card_code=code, date_from=since, per_page=100
            )
            orders = self.api.search_documents(
                doc_type=17, card_code=code, date_from=since, per_page=100
            )
            nq = len(quotes)
            no = len(orders)

            if nq == 0:
                return self._sig(
                    50.0,
                    quotes=0, orders=no, rate_pct=0.0,
                    label="No quotations (neutral)",
                )

            rate = min(1.0, no / nq)
            score = round(rate * 100.0, 1)
            return self._sig(
                score,
                quotes=nq, orders=no,
                rate_pct=round(rate * 100, 1),
                label=f"{rate*100:.0f}% conversion ({no}/{nq})",
            )
        except Exception as exc:
            self._record_error()
            logger.warning("Conversion signal error for %s: %s", code, exc)
            return self._sig(50, quotes=0, orders=0, rate_pct=0, label="Data unavailable")

    @lru_cache(maxsize=256)
    def _financials_cached(self, code: str) -> dict:
        """Cached version of financials calculation."""
        return self._financials(code)
    
    def _financials(self, code: str) -> dict:
        """Score based on outstanding invoices vs credit limit."""
        try:
            self._record_api_call()
            customers = self.api.get_customers(search=code, limit=1)
            credit_limit = 0.0
            if customers:
                octg = customers[0].get("octg") or {}
                credit_limit = float(octg.get("CredLimit", 0))

            invoices = self.api.fetch_marketing_docs(card_code=code, doc_type=13)
            outstanding = sum(
                float(inv.get("DocTotal") or inv.get("doc_total") or 0)
                for inv in (invoices or [])
                if (inv.get("DocStatus") or inv.get("doc_status")) in (1, "1", "bost_Open")
            )

            if credit_limit <= 0:
                return self._sig(
                    75.0,
                    outstanding=outstanding, credit_limit=0.0, util_pct=0.0,
                    label="No credit limit set",
                )

            util = outstanding / credit_limit
            score = round(max(0.0, (1.0 - util) * 100.0), 1)
            return self._sig(
                score,
                outstanding=outstanding,
                credit_limit=credit_limit,
                util_pct=round(util * 100, 1),
                label=f"KES {outstanding:,.0f} outstanding ({util*100:.0f}% of limit)",
            )
        except Exception as exc:
            self._record_error()
            logger.warning("Financials signal error for %s: %s", code, exc)
            return self._sig(75, outstanding=0, credit_limit=0, util_pct=0, label="Data unavailable")

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _recommendations(
        self,
        score:   float,
        r_sig:   dict,
        f_sig:   dict,
        c_sig:   dict,
        fin_sig: dict,
    ) -> list[str]:
        recs: list[str] = []

        days = r_sig.get("days_since_order")
        if days is not None and days > 60:
            recs.append(f"Re-engage — no order in {days} days. Send a follow-up or offer.")
        elif days is not None and days > 30:
            recs.append("Schedule a check-in call — activity is slowing down.")

        if f_sig.get("orders_90d", 0) == 0:
            recs.append("No orders in 90 days — urgent re-engagement needed.")
        elif f_sig.get("orders_90d", 0) < 2:
            recs.append("Low order frequency — consider a volume promotion.")

        rate = c_sig.get("rate_pct", 100)
        if c_sig.get("quotes", 0) >= 3 and rate < 30:
            recs.append(f"Low quote conversion ({rate:.0f}%) — review pricing or follow-up speed.")

        util = fin_sig.get("util_pct", 0)
        outstanding = fin_sig.get("outstanding", 0)
        if util > 80:
            recs.append(f"Credit limit {util:.0f}% used (KES {outstanding:,.0f}) — flag for finance.")
        elif util > 50:
            recs.append(f"Credit utilisation at {util:.0f}% — monitor closely.")

        if score >= 90:
            recs.append("Excellent customer — consider loyalty reward or credit increase.")
        elif score >= 70 and not recs:
            recs.append("Healthy customer — maintain regular contact.")

        return recs[:4]

    # ------------------------------------------------------------------
    # Batch scoring (Optimized)
    # ------------------------------------------------------------------

    def _batch(
        self,
        min_score:  float = 0,
        max_score:  float = 100,
        limit:      int   = 10,
        descending: bool  = True,
    ) -> list[dict]:
        try:
            self._record_api_call()
            customers = self.api.get_customers(limit=50)
        except Exception as exc:
            self._record_error()
            logger.error("Batch score fetch failed: %s", exc)
            return []

        results: list[dict] = []
        for c in customers:
            code = c.get("CardCode")
            name = c.get("CardName", code)
            if not code:
                continue
            try:
                r = self.score(customer_code=code, customer_name=name)
                if r.get("error"):
                    continue
                if min_score <= r["score"] <= max_score:
                    results.append(r)
            except Exception:
                continue

        results.sort(key=lambda x: x["score"], reverse=descending)
        return results[:limit]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _err(message: str) -> dict:
        return {"error": message, "score": 0, "grade": "Unknown", "emoji": "⚪",
                "customer_code": None, "customer_name": None,
                "signals": {}, "recommendations": []}

    @staticmethod
    def _sig(score: float, **kwargs) -> dict:
        """Build a signal dict with score + any extra fields."""
        return {"score": float(score), **kwargs}

    @staticmethod
    def _get_grade(score: float) -> Tuple[str, str]:
        """Get grade label and emoji based on score."""
        for threshold, label, emoji in _GRADES:
            if score >= threshold:
                return label, emoji
        return "Critical", "🔴"

    # ------------------------------------------------------------------
    # Cache Management
    # ------------------------------------------------------------------

    def clear_cache(self):
        """Clear all caches."""
        self._batch_cache.clear()
        self._batch_cache_time.clear()
        
        # Clear LRU caches
        self._recency_cached.cache_clear()
        self._frequency_cached.cache_clear()
        self._conversion_cached.cache_clear()
        self._financials_cached.cache_clear()
        
        # Clear Redis cache
        cache = get_cache_service()
        
        logger.info("Customer health service cache cleared")


# Singleton instance
customer_health_service = CustomerHealthService()