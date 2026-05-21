"""Customer data transformer"""

from typing import List, Dict
from .base import BaseTransformer


class CustomerTransformer(BaseTransformer):
    """Transforms raw customer data into clean format"""
    
    @classmethod
    def transform(cls, raw_customers: List[Dict], max_items: int = 15) -> List[Dict]:
        """Transform customer data"""
        if not raw_customers:
            return []
        
        transformed = []
        for customer in raw_customers[:max_items]:
            transformed_customer = {
                "code": customer.get("CardCode", ""),
                "name": customer.get("CardName", customer.get("name", "")),
                "id": customer.get("id"),
            }
            
            if customer.get("Phone1"):
                transformed_customer["phone"] = customer.get("Phone1")
            if customer.get("EmailAddress"):
                transformed_customer["email"] = customer.get("EmailAddress")
            if customer.get("City"):
                transformed_customer["city"] = customer.get("City")
            
            transformed.append(transformed_customer)
        
        return cls.add_summary_if_truncated(transformed, len(raw_customers), max_items)