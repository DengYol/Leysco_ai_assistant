"""Analytics and reporting intent handlers"""

import logging
import re
from datetime import datetime
from typing import List, Dict, Optional
from ..base_handler import BaseHandler

logger = logging.getLogger(__name__)


def _fmt_revenue(amount: float) -> str:
    """Format a KES amount: use M/K suffixes for readability, no hardcoding."""
    if amount >= 1_000_000:
        return f"KES {amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"KES {amount / 1_000:.1f}K"
    return f"KES {amount:,.0f}"


def _trend_arrow(trend_pct: Optional[float]) -> str:
    """Return a trend string like '↑ 18%' or '↓ 3%', or '' if no data."""
    if trend_pct is None:
        return ""
    arrow = "↑" if trend_pct >= 0 else "↓"
    return f"{arrow} {abs(trend_pct):.1f}%"


def _period_label(days: int) -> str:
    """Human-readable period label derived from the number of days."""
    now = datetime.now()
    if days <= 7:
        return f"Last {days} Days"
    if days <= 31:
        return now.strftime("%B %Y")     # e.g. "May 2026"
    if days <= 92:
        return f"Last {days} Days (Q)"
    return f"Last {days} Days"


class AnalyticsHandler(BaseHandler):
    """Handler for analytics and reporting intents"""

    # ------------------------------------------------------------------
    # TOP SELLING ITEMS
    # ------------------------------------------------------------------

    def get_top_selling_items(self, message: str, limit: int, language: str) -> dict:
        logger.info("Processing GET_TOP_SELLING_ITEMS intent")

        if not (isinstance(limit, int) and limit > 0):
            limit = 10

        days = 30
        days_match  = re.search(r'(\d+)\s+days', message, re.IGNORECASE)
        limit_match = re.search(r'top\s+(\d+)',  message, re.IGNORECASE)
        if days_match:
            days  = int(days_match.group(1))
        if limit_match:
            limit = int(limit_match.group(1))

        logger.info(f"Getting top {limit} selling items for last {days} days")

        try:
            items = self.api.get_top_selling_items(limit=limit, days=days)

            if not items:
                if language == "sw":
                    return {
                        "message": "Hakuna bidhaa zilizopatikana kwa kipindi hiki. "
                                   "Jaribu kipindi kingine.",
                        "data": [],
                    }
                return {
                    "message": "No top selling items found for this period. "
                               "Try a different time range.",
                    "data": [],
                }

            period = _period_label(days)

            if language == "sw":
                lines = [f"Bidhaa Zinazouzwa Sana ({period})\n"]
                for item in items:
                    name     = item.get("name") or item.get("ItemName", "Unknown")
                    qty      = item.get("quantity", 0)
                    revenue  = item.get("revenue", 0.0)
                    trend    = _trend_arrow(item.get("trend_pct"))
                    rank     = item.get("rank", "")

                    lines.append(f"{rank}. {name}")
                    lines.append(f"   Iliyouzwa: {qty:,.0f} vipande")
                    if revenue > 0:
                        lines.append(f"   Mapato: {_fmt_revenue(revenue)}")
                    if trend:
                        lines.append(f"   Mwenendo: {trend} kutoka kipindi kilichopita")
                    lines.append("")

                lines += [
                    "Hatua Zinazofuata:",
                    "• Uliza 'hisa ya [bidhaa]' kuona upatikanaji",
                    "• Uliza 'bei ya [bidhaa]' kuona bei",
                ]
            else:
                lines = [f"Top Selling Items ({period})\n"]
                for item in items:
                    name    = item.get("name") or item.get("ItemName", "Unknown")
                    qty     = item.get("quantity", 0)
                    revenue = item.get("revenue", 0.0)
                    trend   = _trend_arrow(item.get("trend_pct"))
                    rank    = item.get("rank", "")

                    lines.append(f"{rank}. {name}")
                    lines.append(f"   Sold: {qty:,.0f} units")
                    if revenue > 0:
                        lines.append(f"   Revenue: {_fmt_revenue(revenue)}")
                    if trend:
                        lines.append(f"   Trend: {trend} from last period")
                    lines.append("")

                lines += [
                    "Next Steps:",
                    "• Ask 'stock of [item]' to see availability",
                    "• Ask 'price of [item]' to see pricing",
                    "• Ask 'create quotation' to generate quotes",
                ]

            return {"message": "\n".join(lines), "data": items}

        except Exception as e:
            logger.error(f"Error in GET_TOP_SELLING_ITEMS: {e}")
            if language == "sw":
                return {
                    "message": f"Hitilafu: {e}\n\nJaribu tena baadaye.",
                    "data": [],
                }
            return {
                "message": f"Error fetching top selling items: {e}\n\nPlease try again later.",
                "data": [],
            }

    # ------------------------------------------------------------------
    # SLOW MOVING ITEMS
    # ------------------------------------------------------------------

    def get_slow_moving_items(self, message: str, limit: int, language: str) -> dict:
        logger.info("Processing GET_SLOW_MOVING_ITEMS intent")

        if not (isinstance(limit, int) and limit > 0):
            limit = 10

        days      = 90
        threshold = 0.5

        days_match  = re.search(r'(\d+)\s+days', message, re.IGNORECASE)
        limit_match = re.search(r'slow\s+(\d+)',  message, re.IGNORECASE)
        if days_match:
            days  = int(days_match.group(1))
        if limit_match:
            limit = int(limit_match.group(1))

        logger.info(f"Getting {limit} slow moving items over {days} days")

        try:
            items = self.api.get_slow_moving_items(
                limit=limit, days=days, turnover_threshold=threshold
            )

            if not items:
                if language == "sw":
                    return {
                        "message": "Hakuna bidhaa zinazotembea polepole kwa kipindi hiki. "
                                   "Hisa zako zinasonga vizuri!",
                        "data": [],
                    }
                return {
                    "message": "No slow moving items found for this period. "
                               "Your inventory is moving well!",
                    "data": [],
                }

            if language == "sw":
                lines = [f"Bidhaa Zinazotembea Polepole (Siku {days} Zilizopita)\n",
                         "Bidhaa hizi zinahitaji uangalizi:\n"]
                for item in items:
                    name             = item.get("name") or item.get("ItemName", "Unknown")
                    stock            = item.get("stock",          item.get("OnHand", 0))
                    sold             = item.get("sold_in_period", 0)
                    last_sale        = item.get("last_sale_date", "")
                    days_since       = item.get("days_since_last_sale")
                    risk             = item.get("risk",           "Polepole")
                    recommendation   = item.get("Recommendation", "")
                    rank             = item.get("rank", items.index(item) + 1)

                    lines.append(f"{rank}. {name}")
                    lines.append(f"   Hisa: {int(stock):,} vipande")
                    lines.append(f"   Iliyouzwa katika siku {days}: {int(sold):,}")
                    if last_sale:
                        suffix = f" (siku {days_since} zilizopita)" if days_since is not None else ""
                        lines.append(f"   Mauzo ya mwisho: {last_sale}{suffix}")
                    lines.append(f"   Hatari: {risk}")
                    if recommendation:
                        lines.append(f"   Pendekezo: {recommendation}")
                    lines.append("")

                lines += [
                    "Mapendekezo ya Jumla:",
                    "• Fanya promo au punguza bei",
                    "• Fungasha na bidhaa zinazouzwa sana",
                    "• Wasiliana na wateja wanaonunua bidhaa kama hizi",
                ]
            else:
                lines = [f"Slow Moving Items (Last {days} Days)\n",
                         "These items need attention:\n"]
                for item in items:
                    name           = item.get("name") or item.get("ItemName", "Unknown")
                    stock          = item.get("stock",          item.get("OnHand", 0))
                    sold           = item.get("sold_in_period", 0)
                    last_sale      = item.get("last_sale_date", "")
                    days_since     = item.get("days_since_last_sale")
                    risk           = item.get("risk",           "Slow Moving")
                    recommendation = item.get("Recommendation", "")
                    rank           = item.get("rank", items.index(item) + 1)

                    lines.append(f"{rank}. {name}")
                    lines.append(f"   Stock: {int(stock):,} units")
                    lines.append(f"   Sold in {days} days: {int(sold):,}")
                    if last_sale:
                        suffix = f" ({days_since} days ago)" if days_since is not None else ""
                        lines.append(f"   Last sale: {last_sale}{suffix}")
                    lines.append(f"   Risk: {risk}")
                    if recommendation:
                        lines.append(f"   {recommendation}")
                    lines.append("")

                lines += [
                    "Recommendations:",
                    "• Run promotions or markdowns",
                    "• Bundle with popular items",
                    "• Reach out to customers who buy similar products",
                ]

            return {"message": "\n".join(lines), "data": items}

        except Exception as e:
            logger.error(f"Error in GET_SLOW_MOVING_ITEMS: {e}")
            if language == "sw":
                return {
                    "message": f"Hitilafu: {e}\n\nJaribu tena baadaye.",
                    "data": [],
                }
            return {
                "message": f"Error fetching slow moving items: {e}\n\nPlease try again later.",
                "data": [],
            }

    # ------------------------------------------------------------------
    # SALES ANALYTICS
    # ------------------------------------------------------------------

    def get_sales_analytics(self, entities: dict, message: str, language: str) -> dict:
        logger.info("Processing GET_SALES_ANALYTICS intent")

        period = "last_30_days"
        msg_lower = message.lower()
        if "7 days" in msg_lower or "weekly" in msg_lower:
            period = "last_7_days"
        elif "90 days" in msg_lower or "quarterly" in msg_lower:
            period = "last_90_days"
        elif "365 days" in msg_lower or "yearly" in msg_lower:
            period = "last_365_days"

        limit = entities.get("quantity") or 100
        if isinstance(limit, str) and limit.isdigit():
            limit = int(limit)

        try:
            analytics = self.api.get_sales_analytics(period=period, limit=limit)

            if not analytics:
                if language == "sw":
                    return {
                        "message": "Hakuna data ya mauzo kwa kipindi hiki. "
                                   "Jaribu kipindi kingine.",
                        "data": [],
                    }
                return {
                    "message": "No sales data available for this period. "
                               "Try a different period.",
                    "data": [],
                }

            data         = analytics[0]
            summary      = data.get("summary", {})
            top_products = data.get("top_products", [])
            date_range   = data.get("date_range", {})

            if language == "sw":
                lines = [
                    "📊 Uchambuzi wa Mauzo\n",
                    f"Kipindi: {period.replace('_', ' ')}",
                    f"Tarehe: {date_range.get('from', 'N/A')} hadi {date_range.get('to', 'N/A')}\n",
                    f"Mapato Jumla: {_fmt_revenue(summary.get('total_revenue', 0))}",
                    f"Oda Jumla: {summary.get('total_transactions', 0):,}",
                    f"Wateja: {summary.get('unique_customers', 0):,}",
                    f"Wastani wa Oda: {_fmt_revenue(summary.get('average_order_value', 0))}",
                    f"Bidhaa Zilizouzwa: {summary.get('total_items_sold', 0):,}\n",
                ]
                if top_products:
                    lines.append("🏆 Bidhaa 5 Zinazouzwa Sana")
                    for i, p in enumerate(top_products[:5], 1):
                        lines.append(
                            f"{i}. {p.get('name', 'Unknown')} — "
                            f"{_fmt_revenue(p.get('revenue', 0))} "
                            f"({p.get('quantity', 0):,} vipande)"
                        )
            else:
                lines = [
                    "📊 Sales Analytics\n",
                    f"Period: {period.replace('_', ' ')}",
                    f"Date Range: {date_range.get('from', 'N/A')} to {date_range.get('to', 'N/A')}\n",
                    f"Total Revenue: {_fmt_revenue(summary.get('total_revenue', 0))}",
                    f"Total Orders: {summary.get('total_transactions', 0):,}",
                    f"Unique Customers: {summary.get('unique_customers', 0):,}",
                    f"Average Order Value: {_fmt_revenue(summary.get('average_order_value', 0))}",
                    f"Total Items Sold: {summary.get('total_items_sold', 0):,}\n",
                ]
                if top_products:
                    lines.append("🏆 Top 5 Selling Products")
                    for i, p in enumerate(top_products[:5], 1):
                        lines.append(
                            f"{i}. {p.get('name', 'Unknown')} — "
                            f"{_fmt_revenue(p.get('revenue', 0))} "
                            f"({p.get('quantity', 0):,} units)"
                        )

            dp = data.get("data_points", 0)
            if dp:
                if language == "sw":
                    lines.append(f"\n*Uchambuzi unategemea rekodi {dp} za mauzo*")
                else:
                    lines.append(f"\n*Analysis based on {dp} sales records*")

            return {"message": "\n".join(lines), "data": analytics}

        except Exception as e:
            logger.error(f"Error fetching sales analytics: {e}")
            if language == "sw":
                return {
                    "message": f"Hitilafu: {e}\n\nJaribu tena baadaye.",
                    "data": [],
                }
            return {
                "message": f"Error fetching sales analytics: {e}\n\nPlease try again later.",
                "data": [],
            }