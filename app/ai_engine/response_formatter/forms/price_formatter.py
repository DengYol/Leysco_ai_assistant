"""Price formatting for items"""

from ..base import BaseFormatter


class PriceFormatter(BaseFormatter):
    """Formatter for price-related responses"""
    
    @classmethod
    def format_prices(cls, data: dict, language: str = "en") -> dict:
        """Format price data (delegates to format_item_price)."""
        return cls.format_item_price(data, language)
    
    @classmethod
    def format_item_price(cls, data: dict, language: str = "en") -> dict:
        """Format item price response."""
        if not data or "item" not in data:
            return cls._not_available(
                cls._get_no_results_message("GET_ITEM_PRICE", language)
            )

        item = data.get("item", {})
        prices = data.get("prices", [])
        uom = data.get("uom", "Unit")

        item_name = item.get("ItemName") or item.get("full_name") or "Unknown Item"
        item_code = item.get("ItemCode", "")

        if not prices:
            if language == "sw":
                msg = f"Hmm, nimeipata {item_name} ({item_code}) lakini bei yake haijasanidiwa bado. 🤔\n\n💡 Jaribu kuuliza kuhusu bidhaa nyingine au wasiliana na mauzo kwa usaidizi!"
            else:
                msg = f"Hmm, I found {item_name} ({item_code}) but no price is configured for it yet. 🤔\n\n💡 Try asking for a different product or contact sales for assistance!"
            return {"message": msg, "data": []}

        opener = cls._get_opener("GET_ITEM_PRICE", language)

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"💰 **Bei za {item_name}**")
            if item_code:
                lines.append(f"   (Msimbo: {item_code})")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"💰 **Prices for {item_name}**")
            if item_code:
                lines.append(f"   (Code: {item_code})")
            lines.append("")

        structured = []
        for p in prices[:cls.MAX_RESULTS]:
            list_name = p.get("ListName", "Price List")
            price = cls._format_price(p.get("Price"))
            currency = p.get("Currency", "KES")

            if language == "sw":
                lines.append(f"• **{list_name}:** {price} {currency} kwa {uom}")
            else:
                lines.append(f"• **{list_name}:** {price} {currency} per {uom}")

            structured.append({
                "price_list": list_name,
                "price": price,
                "currency": currency,
                "uom": uom
            })

        lines.append(cls._get_tip("GET_ITEM_PRICE", language))
        lines.append(cls._get_closer(language))

        return {"message": "\n".join(lines), "data": structured}