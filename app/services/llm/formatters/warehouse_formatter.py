"""Warehouse data formatter"""

from typing import Any, List
from .base import BaseFormatter


class WarehouseFormatter(BaseFormatter):
    """Format warehouse data for LLM"""
    
    def format(self, data: Any, language: str = "en") -> str:
        """Format warehouse data naturally without markdown"""
        warehouses = data if isinstance(data, list) else [data]
        if not warehouses:
            return "No warehouse data available."
        
        lines = ["WAREHOUSE LOCATIONS:"]
        for wh in warehouses[:15]:
            code = wh.get("code", wh.get("WhsCode", "Unknown"))
            name = wh.get("name", wh.get("WhsName", "Unknown"))
            location = wh.get("location", "")
            total_items = wh.get("total_items", 0)
            total_units = wh.get("total_units", 0)
            
            # Removed ** for markdown
            lines.append(f"🏭 {name} (Code: {code})")
            if location:
                lines.append(f"   📍 Location: {location}")
            if total_items > 0:
                lines.append(f"   📊 Items: {total_items} | Total Units: {total_units:,.0f}")
            lines.append("")
        
        return "\n".join(lines)
    
    def format_low_stock(self, data: Any, language: str = "en") -> str:
        """Format low stock alerts naturally without markdown"""
        items = data if isinstance(data, list) else [data]
        if not items:
            return "No low stock alerts at this time."
        
        lines = ["⚠️ LOW STOCK ALERTS:"]
        for item in items[:20]:
            name = item.get("name", item.get("ItemName", "Unknown"))
            code = item.get("code", item.get("ItemCode", ""))
            available = item.get("available", item.get("Available", 0))
            warehouse = item.get("warehouse", item.get("WhsCode", "Unknown"))
            alert_level = item.get("alert_level", "LOW")
            
            icon = {"CRITICAL": "🔴", "LOW": "🟡", "MEDIUM": "🟠"}.get(alert_level, "⚠️")
            # Removed ** for markdown
            lines.append(f"{icon} {name} (Code: {code})")
            lines.append(f"   🏭 Warehouse: {warehouse}")
            lines.append(f"   📦 Available: {available:,.0f} units")
            lines.append("")
        
        return "\n".join(lines)