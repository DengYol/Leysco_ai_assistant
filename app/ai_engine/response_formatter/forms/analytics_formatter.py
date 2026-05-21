"""Analytics formatting - top selling, slow moving, sales analytics"""

from ..base import BaseFormatter


class AnalyticsFormatter(BaseFormatter):
    """Formatter for analytics-related responses"""
    
    @classmethod
    def format_top_selling_items(cls, items: list, limit: int = 10, days: int = 30, language: str = "en") -> dict:
        """Format top selling items - supports both 'ItemName' and 'name' fields."""
        if not items:
            return cls._not_available(
                cls._get_no_results_message("GET_TOP_SELLING_ITEMS", language)
            )

        opener = cls._get_opener("GET_TOP_SELLING_ITEMS", language)

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📊 **Bidhaa {min(limit, len(items))} Zinazouzwa Sana** (Siku {days} zilizopita)")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📊 **Top {min(limit, len(items))} Selling Items** (Last {days} days)")
            lines.append("")

        for i, item in enumerate(items[:limit], 1):
            name = item.get('name') or item.get('ItemName', 'Unknown')
            score = item.get('PopularityScore', item.get('popularity_score', 0))
            velocity = item.get('Velocity', item.get('velocity', 'MEDIUM'))
            quantity = item.get('quantity') or item.get('Quantity', item.get('total_quantity', 0))

            if velocity == "VERY_HIGH":
                emoji = "🔥🔥"
            elif velocity == "HIGH":
                emoji = "🔥"
            elif velocity == "MEDIUM":
                emoji = "📈"
            elif velocity == "LOW":
                emoji = "📉"
            else:
                emoji = "❄️"

            if language == "sw":
                lines.append(f"{i}. {emoji} **{name}**")
                if quantity and quantity > 0:
                    lines.append(f"   📦 Imewauza: {quantity:,.0f}")
                if score and score > 0:
                    lines.append(f"   📊 Alama ya Umaarufu: {score:.1f}/100")
                lines.append("")
            else:
                lines.append(f"{i}. {emoji} **{name}**")
                if quantity and quantity > 0:
                    lines.append(f"   📦 Sold: {quantity:,.0f} units")
                if score and score > 0:
                    lines.append(f"   📊 Popularity Score: {score:.1f}/100")
                lines.append("")

        lines.append(cls._get_tip("GET_TOP_SELLING_ITEMS", language))
        lines.append(cls._get_closer(language))

        return {"message": "\n".join(lines), "data": items}
    
    @classmethod
    def format_slow_moving_items(cls, items: list, limit: int = 10, days: int = 90, language: str = "en") -> dict:
        """Format slow moving items - supports both naming conventions."""
        if not items:
            return cls._not_available(
                cls._get_no_results_message("GET_SLOW_MOVING_ITEMS", language)
            )

        opener = cls._get_opener("GET_SLOW_MOVING_ITEMS", language)

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"⚠️ **Bidhaa {len(items)} Zinazotembea Polepole** (Siku {days} zilizopita)")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"⚠️ **Top {len(items)} Slow Moving Items** (Last {days} days)")
            lines.append("")

        for i, item in enumerate(items[:limit], 1):
            name = item.get('name') or item.get('ItemName', 'Unknown')
            turnover = item.get('TurnoverRate', item.get('turnover_rate', 0))
            severity = item.get('Severity', item.get('severity', 'monitor'))
            recommendation = item.get('Recommendation', item.get('recommendation', ''))
            days_in_stock = item.get('DaysOfStock', item.get('days_in_stock', 0))
            quantity = item.get('quantity') or item.get('Quantity', item.get('total_quantity', 0))

            if severity == "critical":
                emoji = "🔴"
            elif severity == "warning":
                emoji = "🟡"
            else:
                emoji = "🟢"

            if language == "sw":
                lines.append(f"{i}. {emoji} **{name}**")
                if quantity and quantity > 0:
                    lines.append(f"   📦 Imewauza: {quantity:,.0f}")
                if days_in_stock and days_in_stock > 0:
                    lines.append(f"   📅 Siku hisani: {days_in_stock}")
                lines.append(f"   📊 Kiwango cha Mzunguko: {turnover:.2f}")
                if recommendation:
                    lines.append(f"   💡 {recommendation}")
                lines.append("")
            else:
                lines.append(f"{i}. {emoji} **{name}**")
                if quantity and quantity > 0:
                    lines.append(f"   📦 Sold: {quantity:,.0f} units")
                if days_in_stock and days_in_stock > 0:
                    lines.append(f"   📅 Days in stock: {days_in_stock}")
                lines.append(f"   📊 Turnover Rate: {turnover:.2f}")
                if recommendation:
                    lines.append(f"   💡 {recommendation}")
                lines.append("")

        lines.append(cls._get_tip("GET_SLOW_MOVING_ITEMS", language))
        lines.append(cls._get_closer(language))

        return {"message": "\n".join(lines), "data": items}
    
    @classmethod
    def format_sales_analytics(cls, data: dict, language: str = "en") -> dict:
        """Format sales analytics data - handles decision support response format."""
        if not data or data.get("error"):
            return cls._not_available(
                cls._get_no_results_message("GET_SALES_ANALYTICS", language) if "GET_SALES_ANALYTICS" in cls.NO_RESULTS else "No sales data available."
            )

        opener = cls._get_opener("GET_SALES_ANALYTICS", language)
        
        if "summary" in data:
            summary = data.get("summary", {})
            top_products = data.get("top_products", [])
            date_range = data.get("date_range", {})
        else:
            summary = data
            top_products = data.get("top_products", [])
            date_range = data.get("date_range", {})

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append("📊 **Uchambuzi wa Mauzo**\n")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append("📊 **Sales Analytics**\n")

        if date_range:
            if language == "sw":
                lines.append(f"📅 Kipindi: {date_range.get('from', 'N/A')} hadi {date_range.get('to', 'N/A')}")
            else:
                lines.append(f"📅 Period: {date_range.get('from', 'N/A')} to {date_range.get('to', 'N/A')}")
            lines.append("")

        total_revenue = summary.get('total_revenue', 0)
        total_orders = summary.get('total_transactions', 0)
        unique_customers = summary.get('unique_customers', 0)
        avg_order = summary.get('average_order_value', 0)
        total_items = summary.get('total_items_sold', 0)

        if language == "sw":
            lines.append(f"💰 **Mapato Jumla:** KES {total_revenue:,.2f}")
            lines.append(f"📦 **Oda Jumla:** {total_orders:,}")
            lines.append(f"👥 **Wateja Waliokuwa:** {unique_customers:,}")
            lines.append(f"📊 **Wastani wa Oda:** KES {avg_order:,.2f}")
            lines.append(f"📦 **Bidhaa Zilizouzwa:** {total_items:,}")
            lines.append("")
        else:
            lines.append(f"💰 **Total Revenue:** KES {total_revenue:,.2f}")
            lines.append(f"📦 **Total Orders:** {total_orders:,}")
            lines.append(f"👥 **Unique Customers:** {unique_customers:,}")
            lines.append(f"📊 **Average Order Value:** KES {avg_order:,.2f}")
            lines.append(f"📦 **Total Items Sold:** {total_items:,}")
            lines.append("")

        if top_products:
            if language == "sw":
                lines.append("🏆 **Bidhaa 5 Zinazouzwa Sana**")
            else:
                lines.append("🏆 **Top 5 Selling Products**")
            for i, prod in enumerate(top_products[:5], 1):
                prod_name = prod.get('name', prod.get('ItemName', 'Unknown'))
                prod_revenue = prod.get('revenue', prod.get('total_revenue', 0))
                prod_quantity = prod.get('quantity', prod.get('Quantity', 0))
                lines.append(f"{i}. **{prod_name}** - KES {prod_revenue:,.2f} ({prod_quantity:,.0f} units)")
            lines.append("")

        lines.append(cls._get_closer(language))

        return {"message": "\n".join(lines), "data": data}