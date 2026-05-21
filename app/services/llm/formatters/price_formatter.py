"""Price data formatter"""

from typing import Any, List
from .base import BaseFormatter


class PriceFormatter(BaseFormatter):
    """Format price data for LLM"""
    
    def format(self, data: Any, language: str = "en") -> str:
        """Format price data naturally without markdown"""
        items = data if isinstance(data, list) else [data]
        if not items:
            return "No price data available."
        
        lines = ["PRICE INFORMATION:"]
        for i, item in enumerate(items[:20], 1):
            name = item.get("ItemName", "Unknown")
            code = item.get("ItemCode", "")
            price = item.get("Price")
            currency = item.get("Currency", "KES")
            price_list = item.get("PriceListName", "Standard")
            
            if price and price > 0:
                # Removed ** for markdown
                lines.append(f"{i}. {name} (Code: {code}) - {currency} {price:,.2f} [{price_list}]")
            else:
                lines.append(f"{i}. {name} (Code: {code}) - No price configured")
        
        return "\n".join(lines)