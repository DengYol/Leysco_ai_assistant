"""Customer data formatter"""

from typing import Any, List, Dict
from .base import BaseFormatter


class CustomerFormatter(BaseFormatter):
    """Format customer data for LLM"""
    
    def format(self, data: Any, language: str = "en") -> str:
        """Format customer data naturally without markdown"""
        customers = data if isinstance(data, list) else [data]
        if not customers:
            return "No customer data available."
        
        lines = ["CUSTOMER INFORMATION:"]
        for customer in customers[:10]:
            name = customer.get('CardName', 'Unknown')
            code = customer.get('CardCode', 'N/A')
            phone = customer.get('Phone1', '')
            city = customer.get('City', '')
            credit_limit = customer.get('CreditLimit', 0)
            
            # Removed ** for markdown
            lines.append(f"• {name} (Code: {code})")
            if phone:
                lines.append(f"  📞 Phone: {phone}")
            if city:
                lines.append(f"  📍 Location: {city}")
            if credit_limit:
                lines.append(f"  💰 Credit Limit: KES {credit_limit:,.2f}")
            lines.append("")
        
        return "\n".join(lines)
    
    def format_segmentation(self, data: Any, language: str = "en") -> str:
        """Format customer segmentation data without markdown"""
        customers = data if isinstance(data, list) else [data]
        if not customers:
            return "No customer data available."
        
        lines = ["CUSTOMERS WHO BUY THIS PRODUCT:"]
        for i, cust in enumerate(customers[:15], 1):
            name = cust.get("CardName", "Unknown")
            code = cust.get("CardCode", "N/A")
            qty = cust.get("PurchaseQuantity", 0)
            last_purchase = cust.get("LastPurchaseDate", "")
            reason = cust.get("RecommendationReason", "")
            
            # Removed ** for markdown
            lines.append(f"{i}. {name} (Code: {code})")
            if qty > 0:
                lines.append(f"   📦 Purchased: {qty:,.0f} units")
            if last_purchase:
                lines.append(f"   🕒 Last purchase: {last_purchase[:10]}")
            if reason:
                lines.append(f"   💡 Why: {reason}")
            lines.append("")
        
        return "\n".join(lines)