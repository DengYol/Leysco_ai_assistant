"""Quotation formatting - success and error responses"""

from typing import List, Dict, Any
from datetime import datetime
from ..base import BaseFormatter


class QuotationFormatter(BaseFormatter):
    """Formatter for quotation-related responses"""
    
    @classmethod
    def format_quotation_creation_success(
        cls,
        customer_name: str,
        items: list,
        total_amount: float,
        valid_until: str,
        doc_num: str = None,
        language: str = "en"
    ) -> dict:
        """Format quotation creation response with clean, professional layout."""
        opener = cls._get_opener("CREATE_QUOTATION", language)

        # Format the date properly
        try:
            if valid_until and len(valid_until) > 10:
                valid_date = datetime.strptime(valid_until[:10], "%Y-%m-%d")
                valid_until_fmt = valid_date.strftime("%b %d, %Y")
            else:
                valid_until_fmt = valid_until
        except:
            valid_until_fmt = valid_until

        # Build structured items list
        structured_items = []
        for item in items:
            item_name = item.get("ItemName") or item.get("item_name") or item.get("name", "Unknown")
            quantity = item.get("Quantity") or item.get("quantity", 1)
            price = item.get("Price") or item.get("price", 0)
            line_total = float(quantity) * float(price) if quantity and price else 0
            structured_items.append({
                "name": item_name,
                "quantity": quantity,
                "price": float(price),
                "subtotal": line_total
            })

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            
            if doc_num:
                lines.append(f"✅ **Nukuu #{doc_num} Imeundwa Kikamilifu**")
            else:
                lines.append("✅ **Nukuu Imeundwa Kikamilifu**")
            lines.append("")
            lines.append(f"**Mteja:** {customer_name}")
            lines.append(f"**Jumla:** KES {total_amount:,.2f}")
            lines.append(f"**Inaisha:** {valid_until_fmt}")
            lines.append("")
            lines.append("**Bidhaa:**")
            for item in structured_items:
                lines.append(f"• {item['quantity']} x **{item['name']}** @ KES {item['price']:,.2f} = KES {item['subtotal']:,.2f}")
            lines.append("")
            if doc_num:
                lines.append(f"📋 **Nukuu #{doc_num} imehifadhiwa kwenye mfumo.**")
            else:
                lines.append("📋 **Nukuu imehifadhiwa kwenye mfumo.**")
            lines.append("Unaweza kuituma kwa mteja au kuichapisha.")
            lines.append("")
            lines.append("**Vitendo:**")
            lines.append("• Tazama nukuu - Fungua maelezo kamili")
            lines.append("• Chapisha - Toa nakala ya nukuu")
            lines.append("• Tuma - Shiriki kwa barua pepe au ujumbe")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            
            if doc_num:
                lines.append(f"✅ **Quotation #{doc_num} Created Successfully**")
            else:
                lines.append("✅ **Quotation Created Successfully**")
            lines.append("")
            lines.append(f"**Customer:** {customer_name}")
            lines.append(f"**Total:** KES {total_amount:,.2f}")
            lines.append(f"**Valid Until:** {valid_until_fmt}")
            lines.append("")
            lines.append("**Items:**")
            for item in structured_items:
                lines.append(f"• {item['quantity']} x **{item['name']}** @ KES {item['price']:,.2f} = KES {item['subtotal']:,.2f}")
            lines.append("")
            if doc_num:
                lines.append(f"📋 **Quotation #{doc_num} has been saved to the system.**")
            else:
                lines.append("📋 **Quotation has been saved to the system.**")
            lines.append("You can send it to the customer or print a copy.")
            lines.append("")
            lines.append("**Actions:**")
            lines.append("• View Quotation - See full details")
            lines.append("• Print - Get a printable copy")
            lines.append("• Send - Share via email or message")
            lines.append("")

        lines.append(cls._get_closer(language))

        return {
            "message": "\n".join(lines),
            "data": [{
                "customer_name": customer_name,
                "items": structured_items,
                "total_amount": total_amount,
                "valid_until": valid_until_fmt,
                "doc_num": doc_num,
                "success": True
            }],
            "quotation_id": doc_num
        }

    @classmethod
    def format_quotation_creation_error(
        cls,
        error_message: str,
        invalid_items: list = None,
        language: str = "en"
    ) -> dict:
        """Format quotation creation error response."""
        if language == "sw":
            lines = [
                "❌ **Hitilafu Wakati wa Kuunda Nukuu**",
                "",
                f"**Sababu:** {error_message}"
            ]
            if invalid_items:
                lines.append("")
                lines.append("**Bidhaa Zilizorukwa:**")
                for item in invalid_items[:5]:
                    item_name = item.get("ItemName") or item.get("name", "Unknown")
                    reason = item.get("reason", "Sababu haijulikani")
                    lines.append(f"• {item_name}: {reason}")
                if len(invalid_items) > 5:
                    lines.append(f"... na {len(invalid_items) - 5} nyingine")
            lines.append("")
            lines.append("**💡 Mapendekezo:**")
            lines.append("• Angalia majina ya bidhaa")
            lines.append("• Hakikisha bidhaa zina bei")
            lines.append("• Uliza 'nionyeshe bidhaa' kuona orodha")
        else:
            lines = [
                "❌ **Error Creating Quotation**",
                "",
                f"**Reason:** {error_message}"
            ]
            if invalid_items:
                lines.append("")
                lines.append("**Skipped Items:**")
                for item in invalid_items[:5]:
                    item_name = item.get("ItemName") or item.get("name", "Unknown")
                    reason = item.get("reason", "Unknown reason")
                    lines.append(f"• {item_name}: {reason}")
                if len(invalid_items) > 5:
                    lines.append(f"... and {len(invalid_items) - 5} more")
            lines.append("")
            lines.append("**💡 Suggestions:**")
            lines.append("• Check item names")
            lines.append("• Ensure items have prices")
            lines.append("• Ask 'show me items' to browse")

        lines.append("")
        lines.append(cls._get_closer(language))

        return {
            "message": "\n".join(lines),
            "data": [{"error": error_message, "invalid_items": invalid_items, "success": False}]
        }