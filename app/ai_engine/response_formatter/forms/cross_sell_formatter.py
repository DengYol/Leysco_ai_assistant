"""Cross-sell and recommendation formatting"""

from ..base import BaseFormatter


class CrossSellFormatter(BaseFormatter):
    """Formatter for cross-sell and recommendation responses"""
    
    @classmethod
    def format_cross_sell(cls, data: dict, language: str = "en") -> dict:
        """Format cross-sell recommendations."""
        if not data or not isinstance(data, dict):
            return cls._not_available("I couldn't find any cross-sell recommendations.")
        
        item_name = data.get("item_name", "this item")
        recommendations = data.get("recommendations", [])
        
        if not recommendations:
            if language == "sw":
                msg = f"Hakuna bidhaa nyingine zinazonunuliwa pamoja na {item_name}."
            else:
                msg = f"I couldn't find any items commonly purchased with {item_name}."
            return {"message": msg, "data": []}
        
        if language == "sw":
            lines = [f"🛒 **Wateja walionunua {item_name} pia walinunua:**\n"]
        else:
            lines = [f"🛒 **Customers who bought {item_name} also bought:**\n"]
        
        for idx, item in enumerate(recommendations[:cls.MAX_RESULTS], 1):
            name = (item.get("ItemName") or item.get("name") or "Unknown Item")
            item_code = (item.get("ItemCode") or item.get("item_code") or "")
            price = item.get("Price") or item.get("price")
            reason = item.get("Reason") or item.get("reason") or ""
            stock_status = item.get("StockStatus") or item.get("stock_status") or ""
            stock = item.get("stock", 0)
            
            display_name = f"{name} ({item_code})" if item_code else name
            lines.append(f"{idx}. **{display_name}**")
            
            if price and isinstance(price, (int, float)) and price > 0:
                lines.append(f"   💰 Bei: {cls._format_price(price)} KES")
            else:
                lines.append(f"   ⚠️ Bei: Haijulikani")
            
            if reason:
                lines.append(f"   💡 Sababu: {reason}")
            
            if stock_status:
                lines.append(f"   {stock_status}")
            elif stock <= 0:
                lines.append(f"   ⚠️ Hali: Imeisha")
            elif stock > 0:
                lines.append(f"   ✅ Hali: Ipo (vitengo {stock})")
            lines.append("")
        
        if recommendations:
            if language == "sw":
                lines.append("💡 **Kidokezo:** Fungasha bidhaa hizi pamoja na uokoe 10%!")
            else:
                lines.append("💡 **Tip:** Bundle these items together and save 10%!")
        
        lines.append(cls._get_closer(language))
        return {"message": "\n".join(lines).strip(), "data": recommendations}
    
    @classmethod
    def format_recommended_items(cls, data: list, language: str = "en") -> str:
        """Format recommended items as string."""
        if not data:
            return "No item recommendations available."
        
        if language == "sw":
            text = f"🎯 **Bidhaa {min(len(data), cls.MAX_RESULTS)} Zilizopendekezwa:**\n"
        else:
            text = f"🎯 **Top {min(len(data), cls.MAX_RESULTS)} Recommended Items:**\n"
        
        for idx, item in enumerate(data[:cls.MAX_RESULTS], 1):
            if isinstance(item, dict):
                name = item.get("ItemName") or item.get("name") or "N/A"
                code = item.get("ItemCode") or item.get("code") or "N/A"
            else:
                name = str(item)
                code = "N/A"
            text += f"{idx}. **{name}** (Code: {code})\n"
        
        return text
    
    @classmethod
    def format_recommended_customers(cls, data: list, language: str = "en") -> str:
        """Format recommended customers as string."""
        if not data:
            return "No customer recommendations available."
        
        if language == "sw":
            text = f"👥 **Wateja {min(len(data), cls.MAX_RESULTS)} Walio Pendekezwa:**\n"
        else:
            text = f"👥 **Top {min(len(data), cls.MAX_RESULTS)} Recommended Customers:**\n"
        
        for idx, cust in enumerate(data[:cls.MAX_RESULTS], 1):
            if isinstance(cust, dict):
                name = cust.get("CardName") or cust.get("name") or "N/A"
                code = cust.get("CardCode") or cust.get("code") or "N/A"
            else:
                name = str(cust)
                code = "N/A"
            text += f"{idx}. **{name}** (Code: {code})\n"
        
        return text
    
    @classmethod
    def format_generic_error(cls, data: dict, language: str = "en") -> dict:
        """Format generic error response."""
        if language == "sw":
            msg = "❌ Samahani, kuna hitilafu ilitokea. Tafadhali jaribu tena baadaye. 😔"
        else:
            msg = "❌ Sorry, something went wrong. Please try again in a moment. 😔"
        return cls._not_available(msg)