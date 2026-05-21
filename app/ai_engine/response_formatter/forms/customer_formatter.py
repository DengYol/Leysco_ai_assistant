"""Customer formatting for segmentation, orders, and activity"""

from typing import Dict, Any, List
from ..base import BaseFormatter


class CustomerFormatter(BaseFormatter):
    """Formatter for customer-related responses"""
    
    @classmethod
    def format_customer_segmentation(cls, data: Dict[str, Any], language: str = "en") -> dict:
        """Format customer segmentation data."""
        customers = data.get("customers", [])
        item_name = data.get("item_name", "this product")
        recommendations = data.get("recommendations", [])

        if not customers:
            msg = cls._get_no_results_message("FIND_CUSTOMERS_BY_ITEM", language)
            return {"message": msg, "data": []}

        opener = cls._get_opener("FIND_CUSTOMERS_BY_ITEM", language)

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"🎯 Wateja Wanaonunua {item_name}")
            lines.append(f"📊 Nimepata wateja {len(customers)}:")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"🎯 Customers Who Buy {item_name}")
            lines.append(f"📊 Found {len(customers)} customers:")
            lines.append("")

        for i, cust in enumerate(customers[:cls.MAX_CUSTOMERS_DISPLAY], 1):
            cust_name = cust.get("CardName", "Unknown")
            cust_code = cust.get("CardCode", "N/A")
            qty = cust.get("PurchaseQuantity", 0)
            last_purchase = cust.get("LastPurchaseDate", "")
            reason = cust.get("RecommendationReason", "")

            if language == "sw":
                lines.append(f"{i}. {cust_name} (Msimbo: {cust_code})")
                if qty > 0:
                    lines.append(f"   📦 Kiasi: {qty:,.0f} vitengo")
                if last_purchase:
                    lines.append(f"   🕒 Alinunua mwisho: {cls._format_date(last_purchase)}")
                if reason:
                    lines.append(f"   💡 {reason}")
                lines.append("")
            else:
                lines.append(f"{i}. {cust_name} (Code: {cust_code})")
                if qty > 0:
                    lines.append(f"   📦 Quantity purchased: {qty:,.0f} units")
                if last_purchase:
                    lines.append(f"   🕒 Last purchased: {cls._format_date(last_purchase)}")
                if reason:
                    lines.append(f"   💡 {reason}")
                lines.append("")

        total_customers = len(customers)
        if total_customers > cls.MAX_CUSTOMERS_DISPLAY:
            if language == "sw":
                lines.append(f"... na {total_customers - cls.MAX_CUSTOMERS_DISPLAY} wateja wengine.")
            else:
                lines.append(f"... and {total_customers - cls.MAX_CUSTOMERS_DISPLAY} more customers.")
            lines.append("")

        if recommendations:
            if language == "sw":
                lines.append("💡 Mapendekezo:")
            else:
                lines.append("💡 Recommendations:")
            for rec in recommendations[:3]:
                lines.append(f"• {rec}")
            lines.append("")

        if language == "sw":
            lines.append("💡 Vitendo:")
            lines.append("• Uliza 'nionyeshe maelezo ya mteja' kwa maelezo zaidi")
            lines.append("• Uliza 'unda nukuu kwa wateja hawa' kutengeneza nukuu")
        else:
            lines.append("💡 Next Steps:")
            lines.append("• Ask 'show customer details' for more information")
            lines.append("• Ask 'create quotation for these customers' to generate quotes")

        lines.append(cls._get_closer(language))

        return {"message": "\n".join(lines), "data": customers}
    
    @classmethod
    def format_customer_orders(cls, orders: list, customer_name: str, language: str = "en") -> dict:
        """Format customer orders."""
        if not orders:
            msg = cls._get_no_results_message("GET_CUSTOMER_ORDERS", language)
            msg = msg.replace("this customer", customer_name)
            return {"message": msg, "data": []}

        opener = cls._get_opener("GET_CUSTOMER_ORDERS", language)

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📋 **Oda za {customer_name}**")
            lines.append(f"📊 Nimepata oda {len(orders)}:")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📋 **Orders for {customer_name}**")
            lines.append(f"📊 Found {len(orders)} orders:")
            lines.append("")

        total_value = 0
        for i, o in enumerate(orders[:10], 1):
            doc_num = o.get('DocNum', 'N/A')
            doc_date = cls._format_date(o.get('DocDate', ''))
            doc_total = float(o.get('DocTotal', 0))
            status = o.get('StatusText', o.get('DocStatus', 'Unknown'))
            total_value += doc_total

            if language == "sw":
                lines.append(f"{i}. **Oda #{doc_num}** ({doc_date})")
                lines.append(f"   💰 Kiasi: KES {doc_total:,.2f}")
                lines.append(f"   📍 Hali: {status}")
                lines.append("")
            else:
                lines.append(f"{i}. **Order #{doc_num}** ({doc_date})")
                lines.append(f"   💰 Amount: KES {doc_total:,.2f}")
                lines.append(f"   📍 Status: {status}")
                lines.append("")

        if len(orders) > 10:
            if language == "sw":
                lines.append(f"... na {len(orders) - 10} oda nyingine")
            else:
                lines.append(f"... and {len(orders) - 10} more orders")
            lines.append("")

        if language == "sw":
            lines.append(f"💰 **Jumla Kuu:** KES {total_value:,.2f}")
        else:
            lines.append(f"💰 **Grand Total:** KES {total_value:,.2f}")

        lines.append(cls._get_closer(language))

        return {"message": "\n".join(lines), "data": orders}
    
    @classmethod
    def format_customer_activity(cls, summary: dict, engagement: str, language: str = "en") -> dict:
        """Format customer activity summary."""
        invoices = summary.get("invoices", [])
        deliveries = summary.get("deliveries", [])
        quotations = summary.get("quotations", [])
        
        if language == "sw":
            message_lines = [
                "🔍 Hakuna oda za mauzo za hivi karibuni zilizopatikana.",
                "",
                f"📊 **Kiwango cha Ushirikiano:** {engagement}",
                "",
                "📈 **Muhtasari wa Shughuli za Mteja**",
                f"🧾 Ankara: {len(invoices)}",
                f"🚚 Usafirishaji: {len(deliveries)}",
                f"📝 Nukuu: {len(quotations)}",
            ]
        else:
            message_lines = [
                "🔍 No recent sales orders found.",
                "",
                f"📊 **Engagement Level:** {engagement}",
                "",
                "📈 **Customer Activity Summary**",
                f"🧾 Invoices: {len(invoices)}",
                f"🚚 Deliveries: {len(deliveries)}",
                f"📝 Quotations: {len(quotations)}",
            ]
        
        message_lines.append("")
        message_lines.append(cls._get_closer(language))
        return {"message": "\n".join(message_lines), "data": summary}
    
    @classmethod
    def format_customer(cls, data, language: str = "en") -> dict:
        """Format customer list."""
        status, payload = cls._extract_list(data)
        if status == "error":
            return cls._not_available(payload)
        if not payload:
            return cls._not_available("I couldn't find that customer.")
        customers = payload[:cls.MAX_RESULTS]
        
        if language == "sw":
            lines = ["👥 **Wateja Wanaolingana:**\n"]
            for c in customers:
                if isinstance(c, dict):
                    lines.append(f"• **{c.get('CardName', 'N/A')}** (Msimbo: {c.get('CardCode', 'N/A')})")
                    if c.get('PhoneNumber'):
                        lines.append(f"  📞 {c.get('PhoneNumber')}")
                    if c.get('EmailAddress'):
                        lines.append(f"  ✉️ {c.get('EmailAddress')}")
                    lines.append("")
        else:
            lines = ["👥 **Matching Customers:**\n"]
            for c in customers:
                if isinstance(c, dict):
                    lines.append(f"• **{c.get('CardName', 'N/A')}** (Code: {c.get('CardCode', 'N/A')})")
                    if c.get('PhoneNumber'):
                        lines.append(f"  📞 {c.get('PhoneNumber')}")
                    if c.get('EmailAddress'):
                        lines.append(f"  ✉️ {c.get('EmailAddress')}")
                    lines.append("")
        
        lines.append(cls._get_closer(language))
        return {"message": "\n".join(lines), "data": customers}