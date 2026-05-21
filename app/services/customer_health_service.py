"""
app/services/customer_health_service.py
=========================================
Customer Health Score Service - Optimized with caching and async support

Uses actual Leysco API methods from client.py
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache, wraps

from app.services.leysco_api.client import LeyscoAPIService, create_api_service
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


def cache_health_score(ttl_seconds: int = HEALTH_SCORE_TTL):
    """Decorator to cache health score results."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, customer_code=None, customer_name=None):
            cache = get_cache_service()
            
            # Generate cache key (include user token for isolation)
            user_suffix = self.user_token[:8] if self.user_token else "no_token"
            company_suffix = self.company_code if self.company_code else "no_company"
            key = customer_code or customer_name
            if not key:
                return func(self, customer_code, customer_name)
            
            cache_key = f"health_score:{user_suffix}:{company_suffix}:{key}"
            
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

    def __init__(self, user_token: str = None, company_code: str = None) -> None:
        """
        Initialize CustomerHealthService with user token and company code.
        
        Args:
            user_token: Bearer token from authenticated user
            company_code: Company code for multi-tenant URL resolution
        """
        self.user_token = user_token
        self.company_code = company_code
        
        # Create API service with user token and company code
        if user_token:
            self.api = create_api_service(
                user_token=user_token,
                company_code=company_code
            )
            logger.info(f"✅ CustomerHealthService initialized WITH user token and company_code={company_code}")
        else:
            logger.warning("⚠️ CustomerHealthService initialized WITHOUT user token - API calls will fail")
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

    def set_user_token(self, token: str):
        """Update user token for this instance."""
        self.user_token = token
        self.api.set_user_token(token)
        logger.debug("CustomerHealthService user token updated")
    
    def set_company_code(self, company_code: str):
        """Update company code for this instance."""
        self.company_code = company_code
        self.api.set_company_code(company_code)
        logger.debug(f"CustomerHealthService company code updated to: {company_code}")

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
    # Get customer orders (using actual API methods)
    # ------------------------------------------------------------------
    
    def _get_customer_orders(self, customer_code: str, days_back: int = 90) -> List[Dict]:
        """Get customer orders from the last N days."""
        try:
            # Use get_customer_orders method from LeyscoAPIService
            orders = self.api.get_customer_orders(customer_code=customer_code, limit=100)
            if not orders:
                return []
            
            # Filter by date if needed
            if days_back:
                cutoff_date = datetime.now() - timedelta(days=days_back)
                filtered = []
                for order in orders:
                    doc_date_str = order.get("DocDate", "")
                    if doc_date_str:
                        try:
                            doc_date = datetime.strptime(doc_date_str[:10], "%Y-%m-%d")
                            if doc_date >= cutoff_date:
                                filtered.append(order)
                        except:
                            filtered.append(order)
                    else:
                        filtered.append(order)
                return filtered
            
            return orders
        except Exception as e:
            logger.error(f"Error getting customer orders for {customer_code}: {e}")
            return []
    
    def _get_customer_quotations(self, customer_code: str, days_back: int = 180) -> List[Dict]:
        """Get customer quotations from the last N days."""
        try:
            # Use get_quotations method from LeyscoAPIService (if available)
            if hasattr(self.api, 'get_quotations'):
                quotations = self.api.get_quotations(customer_code=customer_code, limit=100)
            else:
                # Fallback: use get_customer_orders with doc_type parameter
                quotations = self.api.get_customer_orders(customer_code=customer_code, limit=100)
            
            if not quotations:
                return []
            
            # Filter by date if needed
            if days_back:
                cutoff_date = datetime.now() - timedelta(days=days_back)
                filtered = []
                for quote in quotations:
                    doc_date_str = quote.get("DocDate", "")
                    if doc_date_str:
                        try:
                            doc_date = datetime.strptime(doc_date_str[:10], "%Y-%m-%d")
                            if doc_date >= cutoff_date:
                                filtered.append(quote)
                        except:
                            filtered.append(quote)
                    else:
                        filtered.append(quote)
                return filtered
            
            return quotations
        except Exception as e:
            logger.error(f"Error getting customer quotations for {customer_code}: {e}")
            return []

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
    # Public: portfolio views
    # ------------------------------------------------------------------

    def get_top_healthy(self, limit: int = 10) -> list[dict]:
        """Top N customers with score >= 70 (Good or Excellent)."""
        return self._batch(min_score=70, limit=limit, descending=True)

    def get_at_risk(self, limit: int = 10) -> list[dict]:
        """Top N most at-risk customers with score < 50."""
        return self._batch(max_score=49, limit=limit, descending=False)

    async def get_top_healthy_async(self, limit: int = 10) -> list[dict]:
        """Async version of get_top_healthy."""
        return await asyncio.to_thread(self.get_top_healthy, limit)

    async def get_at_risk_async(self, limit: int = 10) -> list[dict]:
        """Async version of get_at_risk."""
        return await asyncio.to_thread(self.get_at_risk, limit)

    # ------------------------------------------------------------------
    # Signal calculators
    # ------------------------------------------------------------------

    def _recency(self, code: str) -> dict:
        """Score based on days since last order. 0d=100, 90d=10, >90=0."""
        try:
            self._record_api_call()
            orders = self._get_customer_orders(code, days_back=365)
            
            if not orders:
                return self._sig(0, days_since_order=None, label="No orders found")

            # Get the most recent order date
            latest_order = None
            latest_date = None
            
            for order in orders:
                doc_date_str = order.get("DocDate", "")
                if doc_date_str:
                    try:
                        doc_date = datetime.strptime(doc_date_str[:10], "%Y-%m-%d")
                        if latest_date is None or doc_date > latest_date:
                            latest_date = doc_date
                            latest_order = order
                    except:
                        pass
            
            if not latest_date:
                return self._sig(0, days_since_order=None, label="No valid date available")

            days = (datetime.now() - latest_date).days
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

    def _frequency(self, code: str) -> dict:
        """Score based on order count in last 90 days."""
        try:
            self._record_api_call()
            orders = self._get_customer_orders(code, days_back=90)
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

    def _conversion(self, code: str) -> dict:
        """Score based on quotation-to-order conversion rate (last 180 days)."""
        try:
            self._record_api_call()
            quotes = self._get_customer_quotations(code, days_back=180)
            orders = self._get_customer_orders(code, days_back=180)
            
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

    def _financials(self, code: str) -> dict:
        """Score based on outstanding invoices vs credit limit."""
        try:
            self._record_api_call()
            customers = self.api.get_customers(search=code, limit=1)
            credit_limit = 0.0
            if customers:
                # Try different field names for credit limit
                credit_limit = float(customers[0].get("CreditLimit", 0)) or float(customers[0].get("CredLimit", 0))
            
            # Get outstanding invoices using available methods
            # For now, use a placeholder - you'll need to implement based on your API
            outstanding = 0.0
            
            # Try to get invoice data if available
            if hasattr(self.api, 'get_outstanding_invoices'):
                invoices = self.api.get_outstanding_invoices(customer_code=code)
                if invoices:
                    outstanding = sum(float(inv.get("DocTotal", 0)) for inv in invoices)
            
            if credit_limit <= 0:
                return self._sig(
                    75.0,
                    outstanding=outstanding, credit_limit=0.0, util_pct=0.0,
                    label="No credit limit set",
                )

            util = outstanding / credit_limit if credit_limit > 0 else 0
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
    # Batch scoring
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
        
        # Clear Redis cache
        cache = get_cache_service()
        
        logger.info("Customer health service cache cleared")


# =========================================================
# Factory function to create CustomerHealthService with user token and company code
# =========================================================

def create_customer_health_service(user_token: str = None, company_code: str = None) -> CustomerHealthService:
    """
    Create a CustomerHealthService instance with the user's token and company code.
    
    Args:
        user_token: The authenticated user's Bearer token
        company_code: Company code for multi-tenant URL resolution
    
    Returns:
        Configured CustomerHealthService instance
    """
    if not user_token:
        logger.warning("⚠️ create_customer_health_service called WITHOUT user token - data access will fail")
    else:
        logger.info(f"✅ create_customer_health_service called WITH user token and company_code={company_code}")
    
    return CustomerHealthService(user_token=user_token, company_code=company_code)