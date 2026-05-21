"""Item data transformer"""

from typing import List, Dict, Any
from .base import BaseTransformer


class ItemTransformer(BaseTransformer):
    """Transforms raw item data into clean format for LLM narration"""
    
    @classmethod
    def transform(cls, raw_items: List[Dict], max_items: int = 15) -> List[Dict]:
        """Transform items with proper stock level extraction"""
        if not raw_items:
            return []
        
        transformed = []
        for item in raw_items[:max_items]:
            transformed_item = {
                "code": item.get("ItemCode", item.get("itemCode", "")),
                "name": item.get("ItemName", item.get("itemName", "")),
                "id": item.get("id"),
            }
            
            # Extract price
            if item.get("Price"):
                transformed_item["price"] = item.get("Price")
            
            # Extract stock level from inventory API fields
            on_hand = item.get("CurrentOnHand") or item.get("OnHand") or item.get("on_hand") or 0
            if on_hand:
                transformed_item["stock"] = round(cls.safe_float(on_hand), 1)
                transformed_item["on_hand"] = round(cls.safe_float(on_hand), 1)
            
            # Extract committed quantity
            committed = item.get("CurrentIsCommited") or item.get("IsCommited") or item.get("is_commited") or 0
            if committed:
                transformed_item["committed"] = round(cls.safe_float(committed), 1)
                available = cls.safe_float(on_hand) - cls.safe_float(committed)
                transformed_item["available"] = round(available, 1)
            
            # Add warehouse if available
            if item.get("WhsCode"):
                transformed_item["warehouse"] = item.get("WhsCode")
            
            # Add last transaction date
            if item.get("LastTransactionDate"):
                transformed_item["last_transaction"] = item.get("LastTransactionDate")
            
            # Add sellable flag
            if item.get("SellItem"):
                transformed_item["sellable"] = item.get("SellItem") == "Y"
            
            # Add item group
            if item.get("item_group") and isinstance(item.get("item_group"), dict):
                transformed_item["group"] = item.get("item_group").get("ItmsGrpNam", "Unknown")
            elif item.get("ItmsGrpNam"):
                transformed_item["group"] = item.get("ItmsGrpNam")
            
            transformed.append(transformed_item)
        
        return cls.add_summary_if_truncated(transformed, len(raw_items), max_items)
    
    @classmethod
    def transform_low_stock(cls, raw_items: List[Dict], max_items: int = 20) -> List[Dict]:
        """Transform inventory items into low stock alert format"""
        if not raw_items:
            return []
        
        # Sort by severity
        raw_items.sort(key=lambda x: (
            0 if x.get("AlertLevel") == "CRITICAL" else 
            1 if x.get("AlertLevel") == "LOW" else 
            2 if x.get("AlertLevel") == "MEDIUM" else 3,
            x.get("Available", 999)
        ))
        
        transformed = []
        for item in raw_items[:max_items]:
            transformed_item = {
                "code": item.get("ItemCode", ""),
                "name": item.get("ItemName", ""),
                "on_hand": round(cls.safe_float(item.get("CurrentOnHand", item.get("OnHand", 0))), 1),
                "committed": round(cls.safe_float(item.get("CurrentIsCommited", item.get("IsCommited", 0))), 1),
                "available": round(cls.safe_float(item.get("Available", 0)), 1),
                "alert_level": item.get("AlertLevel", "UNKNOWN"),
            }
            
            if item.get("WhsCode"):
                transformed_item["warehouse"] = item.get("WhsCode")
            
            transformed.append(transformed_item)
        
        # Add summary statistics
        critical = sum(1 for x in raw_items if x.get("AlertLevel") == "CRITICAL")
        low = sum(1 for x in raw_items if x.get("AlertLevel") == "LOW")
        medium = sum(1 for x in raw_items if x.get("AlertLevel") == "MEDIUM")
        
        summary = {
            "_summary": True,
            "total": len(raw_items),
            "critical": critical,
            "low": low,
            "medium": medium,
            "displayed": min(len(raw_items), max_items),
        }
        transformed.append(summary)
        
        return transformed