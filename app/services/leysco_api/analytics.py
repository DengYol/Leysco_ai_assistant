"""Sales analytics and performance metrics"""

import logging
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from .utils import safe_float, is_html_response
from .cache import cache_api_result
from .constants import ANALYTICS_CACHE_TTL

logger = logging.getLogger(__name__)


class AnalyticsHandler:
    """Handles sales analytics, top selling, and slow moving items"""

    def __init__(self, parent):
        self.parent       = parent
        self.session      = parent.session
        self.base_url     = parent.base_url
        self.auth_handler = parent.auth_handler
        self.inventory    = parent.inventory

    def _record_cache_hit(self):
        if hasattr(self.parent, '_record_cache_hit'):
            self.parent._record_cache_hit()

    def _record_cache_miss(self):
        if hasattr(self.parent, '_record_cache_miss'):
            self.parent._record_cache_miss()

    def _get_period_days(self, period: str) -> int:
        return {
            "last_7_days":   7,
            "last_30_days":  30,
            "last_90_days":  90,
            "last_365_days": 365,
        }.get(period, 30)

    def _parse_orders(self, data: dict) -> List[Dict]:
        if data.get("ResultState") and data.get("ResponseData"):
            rd = data["ResponseData"]
            if isinstance(rd, dict):
                return rd.get("data", [])
            if isinstance(rd, list):
                return rd
        from .utils import normalize_response
        return normalize_response(data)

    def _fetch_orders(
        self,
        start_date: datetime,
        end_date: datetime,
        per_page: int = 500,
    ) -> List[Dict]:
        """Fetch sales orders for a date window — single reusable helper."""
        if not self.auth_handler.ensure_auth():
            return []
        url = f"{self.base_url}/marketing/docs/17"
        params = {
            "page":     1,
            "per_page": per_page,
            "FromDate": start_date.strftime("%Y-%m-%d"),
            "ToDate":   end_date.strftime("%Y-%m-%d"),
        }
        try:
            self.parent._record_api_call()
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code != 200 or is_html_response(resp.text):
                return []
            return self._parse_orders(resp.json())
        except Exception as e:
            logger.warning(f"_fetch_orders error: {e}")
            return []

    @staticmethod
    def _aggregate_item_sales(orders: List[Dict]) -> Dict[str, Dict]:
        """
        Walk order lines and accumulate per-item quantity + revenue.
        Returns {item_code: {name, code, quantity, revenue}}
        ItemName is read directly from DocumentLines — no extra API calls.
        """
        sales: Dict[str, Dict] = {}
        for order in orders:
            lines = order.get("document_lines", []) or order.get("DocumentLines", [])
            for line in lines:
                code = line.get("ItemCode")
                if not code:
                    continue
                qty  = safe_float(line.get("Quantity"))
                if qty <= 0:
                    continue
                name = line.get("ItemName") or line.get("item_name") or code
                rev  = qty * safe_float(line.get("Price"))
                if code not in sales:
                    sales[code] = {
                        "name": name, "code": code,
                        "quantity": 0.0, "revenue": 0.0,
                    }
                else:
                    if sales[code]["name"] == code and name != code:
                        sales[code]["name"] = name
                sales[code]["quantity"] += qty
                sales[code]["revenue"]  += rev
        return sales

    # ------------------------------------------------------------------
    # SALES ANALYTICS
    # ------------------------------------------------------------------

    @cache_api_result(ttl_seconds=ANALYTICS_CACHE_TTL)
    def get_sales_analytics(
        self,
        period: str = "last_30_days",
        limit: int = 100,
        customer_code: str = None,
        item_code: str = None,
    ) -> List[Dict]:
        """Get real sales analytics data from Leysco API."""
        try:
            if not self.auth_handler.ensure_auth():
                return []

            period_days = self._get_period_days(period)
            end_date    = datetime.now()
            start_date  = end_date - timedelta(days=period_days)

            url = f"{self.base_url}/marketing/docs/17"
            params = {
                "page": 1, "per_page": limit,
                "FromDate": start_date.strftime("%Y-%m-%d"),
                "ToDate":   end_date.strftime("%Y-%m-%d"),
            }
            if customer_code:
                params["CardCode"] = customer_code

            self.parent._record_api_call()
            resp = self.session.get(url, params=params, timeout=30)
            if not self.auth_handler.check_auth(resp):
                return []
            if resp.status_code != 200 or is_html_response(resp.text):
                return []

            orders = self._parse_orders(resp.json())
            if not orders:
                return []

            return self._aggregate_analytics(
                orders, item_code, start_date, end_date, period_days
            )
        except Exception as e:
            self.parent._record_error()
            logger.error(f"Failed to fetch sales analytics: {e}", exc_info=True)
            return []

    def _aggregate_analytics(
        self, orders, item_code, start_date, end_date, period_days
    ) -> List[Dict]:
        total_revenue      = 0.0
        total_transactions = 0
        unique_customers: set = set()
        total_items_sold   = 0.0
        product_sales: Dict = {}
        customer_sales: Dict = {}
        monthly_data: Dict   = {}

        for order in orders:
            doc_total = safe_float(order.get("DocTotal"))
            card_code = order.get("CardCode")
            card_name = order.get("CardName", "Unknown")
            doc_date  = order.get("DocDate", "")

            total_revenue      += doc_total
            total_transactions += 1

            if card_code:
                unique_customers.add(card_code)
                cs = customer_sales.setdefault(
                    card_name, {"revenue": 0.0, "count": 0, "code": card_code}
                )
                cs["revenue"] += doc_total
                cs["count"]   += 1

            if doc_date and len(doc_date) >= 7:
                mk = doc_date[:7]
                md = monthly_data.setdefault(mk, {"revenue": 0.0, "count": 0})
                md["revenue"] += doc_total
                md["count"]   += 1

            lines = order.get("document_lines", []) or order.get("DocumentLines", [])
            for line in lines:
                ic  = line.get("ItemCode")
                nm  = line.get("ItemName", "Unknown")
                qty = safe_float(line.get("Quantity"))
                prc = safe_float(line.get("Price"))
                total_items_sold += qty
                if item_code and ic != item_code:
                    continue
                ps = product_sales.setdefault(
                    nm, {"quantity": 0.0, "revenue": 0.0, "code": ic or ""}
                )
                ps["quantity"] += qty
                ps["revenue"]  += qty * prc

        avg_order = total_revenue / total_transactions if total_transactions else 0.0

        top_products = [
            {"name": n, "code": v["code"],
             "quantity": int(v["quantity"]),
             "revenue":  round(v["revenue"], 2)}
            for n, v in sorted(
                product_sales.items(),
                key=lambda x: x[1]["revenue"], reverse=True
            )[:10]
        ]
        top_customers = [
            {"name": n, "code": v["code"],
             "revenue": round(v["revenue"], 2), "orders": v["count"]}
            for n, v in sorted(
                customer_sales.items(),
                key=lambda x: x[1]["revenue"], reverse=True
            )[:5]
        ]
        monthly_summary = [
            {"month": m,
             "revenue": round(monthly_data[m]["revenue"], 2),
             "orders":  monthly_data[m]["count"]}
            for m in sorted(monthly_data.keys())[-6:]
        ]

        return [{
            "analysis_type":      "sales_analytics",
            "period_days":        period_days,
            "period_description": f"last {period_days} days",
            "date_range": {
                "from": start_date.strftime("%Y-%m-%d"),
                "to":   end_date.strftime("%Y-%m-%d"),
            },
            "summary": {
                "total_revenue":       round(total_revenue, 2),
                "total_transactions":  total_transactions,
                "average_order_value": round(avg_order, 2),
                "unique_customers":    len(unique_customers),
                "total_items_sold":    int(total_items_sold),
            },
            "top_products":  top_products,
            "top_customers": top_customers,
            "monthly_trend": monthly_summary,
            "data_points":   len(orders),
            "source":        "sales_orders_api",
        }]

    # ------------------------------------------------------------------
    # TOP SELLING ITEMS
    # ------------------------------------------------------------------

    @cache_api_result(ttl_seconds=ANALYTICS_CACHE_TTL)
    def get_top_selling_items(self, limit: int = 10, days: int = 30) -> List[Dict]:
        """
        Top-selling items with quantity, revenue, and month-on-month trend.

        - quantity / revenue come from DocumentLines — no extra item lookups.
        - trend_pct  = % change vs the previous equal-length period.
        """
        try:
            if not self.auth_handler.ensure_auth():
                return []

            end_date   = datetime.now()
            start_date = end_date - timedelta(days=days)
            prev_end   = start_date
            prev_start = prev_end - timedelta(days=days)

            logger.info("📊 Fetching sales orders for top items")
            current_orders  = self._fetch_orders(start_date, end_date)
            previous_orders = self._fetch_orders(prev_start, prev_end)

            if not current_orders:
                return self._calculate_top_selling_from_inventory(limit, days)

            current_sales  = self._aggregate_item_sales(current_orders)
            previous_sales = self._aggregate_item_sales(previous_orders)

            if not current_sales:
                return self._calculate_top_selling_from_inventory(limit, days)

            sorted_items = sorted(
                current_sales.values(),
                key=lambda x: x["quantity"], reverse=True,
            )[:limit]

            top_qty = sorted_items[0]["quantity"] if sorted_items else 1.0
            result  = []

            for i, item in enumerate(sorted_items, 1):
                code     = item["code"]
                prev_qty = previous_sales.get(code, {}).get("quantity", 0.0)

                if prev_qty > 0:
                    trend_pct = round(
                        ((item["quantity"] - prev_qty) / prev_qty) * 100, 1
                    )
                else:
                    trend_pct = None   # no previous data — omit trend arrow

                result.append({
                    "name":            item["name"],
                    "code":            code,
                    "quantity":        item["quantity"],
                    "revenue":         round(item["revenue"], 2),
                    "rank":            i,
                    "analysis_days":   days,
                    "PopularityScore": min(
                        100,
                        round((item["quantity"] / max(1.0, top_qty)) * 100, 1),
                    ),
                    "trend_pct":       trend_pct,
                })

            logger.info(f"✅ Found {len(result)} top selling items from sales orders")
            return result

        except Exception as e:
            self.parent._record_error()
            logger.error(f"Error in get_top_selling_items: {e}")
            return self._calculate_top_selling_from_inventory(limit, days)

    def _calculate_top_selling_from_inventory(
        self, limit: int = 10, days: int = 30
    ) -> List[Dict]:
        """Fallback: estimate ranking from inventory commit ratios."""
        try:
            inventory = self.inventory.get_inventory_report(limit=1000)
            if not inventory:
                return []

            scored = []
            for item in inventory:
                on_hand    = safe_float(item.get("CurrentOnHand"))
                committed  = safe_float(item.get("CurrentIsCommited"))
                period_out = safe_float(item.get("PeriodOutQty", 0))

                if period_out > 0:
                    score = min(100.0, (period_out / days) * 10)
                elif committed > 0 and on_hand > 0:
                    score = min(100.0, (min(2.0, committed / on_hand)) * 50)
                elif on_hand > 0:
                    score = 5.0
                else:
                    continue

                scored.append({
                    "name":            item.get("ItemName") or item.get("ItemCode", "Unknown"),
                    "code":            item.get("ItemCode", ""),
                    "quantity":        period_out,
                    "revenue":         0.0,
                    "trend_pct":       None,
                    "PopularityScore": round(score, 2),
                    "source":          "inventory_fallback",
                })

            scored.sort(key=lambda x: x["PopularityScore"], reverse=True)
            for i, item in enumerate(scored[:limit], 1):
                item["rank"]          = i
                item["analysis_days"] = days

            logger.info(f"✅ {len(scored[:limit])} top sellers from inventory (fallback)")
            return scored[:limit]

        except Exception as e:
            logger.error(f"Inventory fallback failed: {e}")
            return []

    # ------------------------------------------------------------------
    # SLOW MOVING ITEMS
    # ------------------------------------------------------------------

    @cache_api_result(ttl_seconds=ANALYTICS_CACHE_TTL)
    def get_slow_moving_items(
        self,
        limit: int = 10,
        days: int = 90,
        turnover_threshold: float = 0.5,
    ) -> List[Dict]:
        """
        Slow-moving items with:
          - stock on hand
          - qty sold in the analysis period
          - days since last sale (from LastTransactionDate)
          - risk label (Dead Stock / High Overstock / Slow Moving)

        All data sourced from the inventory report and sales orders.
        Nothing is hardcoded.
        """
        try:
            if not self.auth_handler.ensure_auth():
                return []

            # ── Inventory snapshot ───────────────────────────────────
            inventory = self.inventory.get_inventory_report(limit=2000)
            if not inventory:
                logger.warning("No inventory data for slow-moving analysis")
                return []

            # Collapse multi-warehouse rows per item code
            inv_map: Dict[str, Dict] = {}
            for row in inventory:
                code = row.get("ItemCode")
                if not code:
                    continue
                if code in inv_map:
                    inv_map[code]["CurrentOnHand"]     += safe_float(row.get("CurrentOnHand"))
                    inv_map[code]["CurrentIsCommited"] += safe_float(row.get("CurrentIsCommited"))
                    existing = inv_map[code].get("LastTransactionDate", "")
                    incoming = row.get("LastTransactionDate", "")
                    if incoming and incoming > existing:
                        inv_map[code]["LastTransactionDate"] = incoming
                else:
                    inv_map[code] = {
                        "ItemName":            row.get("ItemName") or code,
                        "ItemCode":            code,
                        "CurrentOnHand":       safe_float(row.get("CurrentOnHand")),
                        "CurrentIsCommited":   safe_float(row.get("CurrentIsCommited")),
                        "LastTransactionDate": row.get("LastTransactionDate", ""),
                        "PeriodOutQty":        safe_float(row.get("PeriodOutQty", 0)),
                    }

            # ── Sales in the analysis period ────────────────────────
            end_date   = datetime.now()
            start_date = end_date - timedelta(days=days)
            orders     = self._fetch_orders(start_date, end_date, per_page=500)

            sold_in_period: Dict[str, float] = {}
            for order in orders:
                lines = order.get("document_lines", []) or order.get("DocumentLines", [])
                for line in lines:
                    c = line.get("ItemCode")
                    if c:
                        sold_in_period[c] = (
                            sold_in_period.get(c, 0.0)
                            + safe_float(line.get("Quantity"))
                        )

            # ── Score items ──────────────────────────────────────────
            slow_items = []
            for code, inv in inv_map.items():
                on_hand = inv["CurrentOnHand"]
                if on_hand <= 0:
                    continue

                qty_sold = sold_in_period.get(code, inv.get("PeriodOutQty", 0.0))
                turnover = qty_sold / on_hand

                if turnover >= turnover_threshold:
                    continue

                # Days since last transaction
                last_txn_str          = inv.get("LastTransactionDate", "")
                days_since_last_sale: Optional[int] = None
                last_sale_date_fmt    = ""
                if last_txn_str:
                    try:
                        last_dt              = datetime.strptime(last_txn_str[:10], "%Y-%m-%d")
                        days_since_last_sale = (end_date - last_dt).days
                        last_sale_date_fmt   = last_dt.strftime("%Y-%m-%d")
                    except ValueError:
                        pass

                # Risk classification (no magic numbers beyond the threshold param)
                if qty_sold == 0 or (
                    days_since_last_sale is not None and days_since_last_sale > days
                ):
                    risk           = "Dead Stock"
                    severity       = "critical"
                    recommendation = "No movement — review for clearance or write-off"
                elif turnover < turnover_threshold * 0.4:
                    risk           = "High Overstock"
                    severity       = "warning"
                    recommendation = "Very slow — run promotion or bundle with fast movers"
                else:
                    risk           = "Slow Moving"
                    severity       = "monitor"
                    recommendation = "Below target — consider discount or redistribution"

                slow_items.append({
                    # Fields the formatter uses for display
                    "name":                 inv["ItemName"],
                    "code":                 code,
                    "stock":                int(on_hand),
                    "sold_in_period":       int(qty_sold),
                    "analysis_days":        days,
                    "last_sale_date":       last_sale_date_fmt,
                    "days_since_last_sale": days_since_last_sale,
                    "risk":                 risk,
                    # SAP-style aliases kept for backwards compatibility
                    "ItemName":             inv["ItemName"],
                    "ItemCode":             code,
                    "OnHand":               on_hand,
                    "TurnoverRate":         round(turnover, 4),
                    "Severity":             severity,
                    "Recommendation":       recommendation,
                })

            # Zero-movement first, then ascending turnover
            slow_items.sort(
                key=lambda x: (x["sold_in_period"], x["TurnoverRate"])
            )
            result = slow_items[:limit]

            logger.info(
                f"✅ Found {len(result)} slow-moving items "
                f"(threshold={turnover_threshold}, days={days})"
            )
            return result

        except Exception as e:
            self.parent._record_error()
            logger.error(f"Error in get_slow_moving_items: {e}", exc_info=True)
            return []