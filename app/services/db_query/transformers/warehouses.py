"""Warehouse data transformer"""

from typing import List, Dict
from .base import BaseTransformer


class WarehouseTransformer(BaseTransformer):
    """Transforms raw warehouse data into clean format"""
    
    @classmethod
    def transform(cls, raw_warehouses: List[Dict], max_items: int = 12) -> List[Dict]:
        """Transform warehouse data"""
        if not raw_warehouses:
            return []
        
        transformed = []
        for w in raw_warehouses[:max_items]:
            warehouse = {
                "code": w.get("WhsCode", w.get("code", "")),
                "name": w.get("WhsName", w.get("name", "")),
                "id": w.get("id"),
            }
            
            location_parts = []
            if w.get("City"):
                location_parts.append(w.get("City"))
            if w.get("County"):
                location_parts.append(w.get("County"))
            if w.get("State"):
                location_parts.append(w.get("State"))
            if w.get("Country"):
                location_parts.append(w.get("Country"))
            
            if location_parts:
                warehouse["location"] = ", ".join(location_parts)
            
            # Add status
            if w.get("Status"):
                warehouse["status"] = w.get("Status")
            elif w.get("Locked"):
                warehouse["status"] = "Inactive" if w.get("Locked") == "Y" else "Active"
            else:
                warehouse["status"] = "Active"
            
            # Add stock summary if available
            if w.get("total_items") is not None:
                warehouse["total_items"] = w.get("total_items")
                warehouse["total_units"] = w.get("total_units", 0)
                warehouse["total_available"] = w.get("total_available", 0)
            
            transformed.append(warehouse)
        
        return cls.add_summary_if_truncated(transformed, len(raw_warehouses), max_items)
    
    @classmethod
    def transform_from_summary(cls, warehouses_summary: List[Dict], max_items: int = 12) -> List[Dict]:
        """Transform warehouse summary data from WarehouseService"""
        if not warehouses_summary:
            return []
        
        transformed = []
        for w in warehouses_summary[:max_items]:
            warehouse = {
                "code": w.get("WhsCode", ""),
                "name": w.get("WhsName", ""),
                "location": "",
                "status": "Active",
                "total_items": w.get("total_items", 0),
                "total_units": w.get("total_units", 0),
                "total_available": w.get("total_available", 0),
            }
            
            # Add location from details
            details = w.get("details", {})
            location_parts = []
            if details.get("City"):
                location_parts.append(details.get("City"))
            if details.get("County"):
                location_parts.append(details.get("County"))
            if details.get("Country"):
                location_parts.append(details.get("Country"))
            if location_parts:
                warehouse["location"] = ", ".join(location_parts)
            
            transformed.append(warehouse)
        
        return cls.add_summary_if_truncated(transformed, len(warehouses_summary), max_items)