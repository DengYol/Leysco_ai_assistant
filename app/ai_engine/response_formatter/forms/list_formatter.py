"""Generic list formatting for items and customers"""

from ..base import BaseFormatter
from .customer_formatter import CustomerFormatter


class ListFormatter(BaseFormatter):
    """Formatter for generic list responses"""
    
    @classmethod
    def format_list(cls, title: str, data, language: str = "en") -> dict:
        """Format generic list of items or customers."""
        status, payload = cls._extract_list(data)
        if status == "error":
            return cls._not_available(payload)
        if not payload:
            return cls._not_available(f"I couldn't find any {title}.")
        
        limited = payload[:cls.MAX_RESULTS]
        
        if title == "items":
            if language == "sw":
                lines = ["📦 **Bidhaa Zinazolingana:**\n"]
                for i in limited:
                    if isinstance(i, dict):
                        item_name = i.get('ItemName', 'N/A')
                        item_code = i.get('ItemCode', 'N/A')
                        stock = i.get('OnHand')
                        lines.append(f"• **{item_name}** ({item_code})")
                        if stock is not None:
                            lines.append(f"  📦 Hisa: {stock:,.0f}")
                        lines.append("")
            else:
                lines = ["📦 **Matching Items:**\n"]
                for i in limited:
                    if isinstance(i, dict):
                        item_name = i.get('ItemName', 'N/A')
                        item_code = i.get('ItemCode', 'N/A')
                        stock = i.get('OnHand')
                        lines.append(f"• **{item_name}** ({item_code})")
                        if stock is not None:
                            lines.append(f"  📦 Stock: {stock:,.0f}")
                        lines.append("")
            
            lines.append(cls._get_closer(language))
            return {"message": "\n".join(lines), "data": limited}
        
        if title == "customers":
            return CustomerFormatter.format_customer(data, language)
        
        return {"message": f"I found some {title}.", "data": limited}
    
    @classmethod
    def format_stock(cls, data: dict, language: str = "en") -> dict:
        """Format stock information."""
        if "error" in data or data.get("stock") is None:
            return cls._not_available()
        
        stock = data.get('stock')
        item_name = data.get('item_name')
        warehouse = data.get('warehouse', '')
        
        if stock <= 0:
            if language == "sw":
                msg = f"📦 **{item_name}** imeisha kwa sasa."
                if warehouse:
                    msg += f" (Ghala: {warehouse})"
                msg += "\n\n💡 Tafadhali wasiliana na timu ya mauzo kwa usaidizi."
            else:
                msg = f"📦 **{item_name}** is currently out of stock."
                if warehouse:
                    msg += f" (Warehouse: {warehouse})"
                msg += "\n\n💡 Please contact the sales team for assistance."
        else:
            if language == "sw":
                msg = f"📦 **{item_name}** tuna vitengo **{stock:,.0f}** hisani."
                if warehouse:
                    msg += f" (Ghala: {warehouse})"
                msg += "\n\n💡 Unahitaji kuangalia bidhaa nyingine?"
            else:
                msg = f"📦 **{item_name}** we have **{stock:,.0f}** units in stock."
                if warehouse:
                    msg += f" (Warehouse: {warehouse})"
                msg += "\n\n💡 Need to check another product?"
        
        msg += "\n" + cls._get_closer(language)
        return {"message": msg, "data": [{"item": item_name, "stock": stock, "warehouse": warehouse}]}
    
    @classmethod
    def format_sales_orders(cls, data: list, language: str = "en") -> dict:
        """Format sales orders."""
        if not data:
            return {"message": "No sales orders found.", "data": []}
        
        if language == "sw":
            lines = ["📋 **Oda za Mauzo Zilizopatikana:**\n"]
        else:
            lines = ["📋 **Sales Orders Found:**\n"]
        
        structured = []
        for idx, item in enumerate(data[:cls.MAX_RESULTS], 1):
            if isinstance(item, dict):
                name = item.get("name") or item.get("ItemName") or "N/A"
                warehouse = item.get("warehouse") or item.get("Warehouse") or "N/A"
                quantity = item.get("quantity") or item.get("Quantity") or "N/A"
            else:
                name = str(item)
                warehouse = "N/A"
                quantity = "N/A"
            
            if language == "sw":
                lines.append(f"{idx}. **{name}**")
                lines.append(f"   🏭 Ghala: {warehouse}")
                if quantity != "N/A":
                    lines.append(f"   📦 Kiasi: {quantity}")
            else:
                lines.append(f"{idx}. **{name}**")
                lines.append(f"   🏭 Warehouse: {warehouse}")
                if quantity != "N/A":
                    lines.append(f"   📦 Quantity: {quantity}")
            lines.append("")
            structured.append({"name": name, "warehouse": warehouse, "quantity": quantity})
        
        lines.append(cls._get_closer(language))
        return {"message": "\n".join(lines), "data": structured}
    
    @classmethod
    def format_quotations(cls, quotations, customer_name: str = None, language: str = "en") -> dict:
        """Format quotations list."""
        if not quotations:
            return {"message": "No quotations found.", "data": []}
        if isinstance(quotations, str):
            return {"message": quotations, "data": []}
        if isinstance(quotations, dict):
            quotations = quotations.get("value") or quotations.get("data") or []
        if isinstance(quotations, list) and quotations and isinstance(quotations[0], str):
            return {"message": "\n".join(quotations), "data": quotations}
        if not quotations:
            return {"message": "No quotations found.", "data": []}
        
        if customer_name:
            quotations = [
                q for q in quotations
                if customer_name.lower() in str(q.get("CardName", "")).lower()
            ]
            if not quotations:
                if language == "sw":
                    msg = f"No quotations found for {customer_name}."
                else:
                    msg = f"Hakuna nukuu zilizopatikana kwa {customer_name}."
                return {"message": msg, "data": []}
        
        if language == "sw":
            text = f"📄 **Nukuu ({len(quotations)} zilizopatikana):**\n\n"
        else:
            text = f"📄 **Quotations ({len(quotations)} found):**\n\n"
        
        grand_total = 0
        for i, q in enumerate(quotations[:cls.MAX_RESULTS], 1):
            total = float(q.get("DocTotal", 0))
            grand_total += total
            if language == "sw":
                text += (
                    f"{i}. **Nukuu #{q.get('DocNum', 'N/A')}**\n"
                    f"   📅 Tarehe: {cls._format_date(q.get('DocDate'))}\n"
                    f"   👤 Mteja: {q.get('CardName', 'N/A')}\n"
                    f"   💰 Jumla: KES {total:,.2f}\n"
                    f"   📍 Hali: {q.get('DocStatus', 'N/A')}\n\n"
                )
            else:
                text += (
                    f"{i}. **Quotation #{q.get('DocNum', 'N/A')}**\n"
                    f"   📅 Date: {cls._format_date(q.get('DocDate'))}\n"
                    f"   👤 Customer: {q.get('CardName', 'N/A')}\n"
                    f"   💰 Total: KES {total:,.2f}\n"
                    f"   📍 Status: {q.get('DocStatus', 'N/A')}\n\n"
                )
        
        if language == "sw":
            text += f"💰 **Jumla Kuu:** KES {grand_total:,.2f}"
        else:
            text += f"💰 **Grand Total:** KES {grand_total:,.2f}"
        
        text += "\n" + cls._get_closer(language)
        return {"message": text, "data": quotations}