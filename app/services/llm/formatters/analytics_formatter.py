"""Analytics data formatter for top/slow moving items"""

from typing import Any, List
from .base import BaseFormatter


class AnalyticsFormatter(BaseFormatter):
    """Format analytics data for LLM"""
    
    def format(self, data: Any, language: str = "en") -> str:
        """
        Base format method required by BaseFormatter.
        Delegates to specific formatters based on data type.
        """
        if not data:
            return "No analytics data available."
        
        # Check if it's top selling data (has PopularityScore or velocity)
        if isinstance(data, list) and data:
            first_item = data[0]
            if "PopularityScore" in first_item or "Velocity" in first_item:
                return self.format_top_selling(data, language)
            if "TurnoverRate" in first_item or "Severity" in first_item:
                return self.format_slow_moving(data, language)
        
        # Check if it's a dict with items
        if isinstance(data, dict):
            if "items" in data:
                items = data["items"]
                if items and ("PopularityScore" in items[0] or "Velocity" in items[0]):
                    return self.format_top_selling(items, language)
                if items and ("TurnoverRate" in items[0] or "Severity" in items[0]):
                    return self.format_slow_moving(items, language)
        
        # Default - return string representation
        return str(data)
    
    def format_top_selling(self, data: Any, language: str = "en") -> str:
        """Format top selling items naturally without markdown"""
        items = data if isinstance(data, list) else [data]
        if not items:
            return "No top selling data available."
        
        lines = ["TOP SELLING ITEMS (ranked by popularity):"]
        for i, item in enumerate(items[:15], 1):
            name = item.get("ItemName", "Unknown")
            score = item.get("PopularityScore", 0)
            velocity = item.get("Velocity", "MEDIUM")
            
            velocity_icon = {"VERY_HIGH": "🔥🔥", "HIGH": "🔥", "MEDIUM": "📈", "LOW": "📉"}.get(velocity, "⭐")
            lines.append(f"{i}. {velocity_icon} {name} - Score: {score:.0f}/100")
        
        return "\n".join(lines)
    
    def format_slow_moving(self, data: Any, language: str = "en") -> str:
        """Format slow moving items naturally without markdown"""
        items = data if isinstance(data, list) else [data]
        if not items:
            return "No slow moving data available."
        
        lines = ["SLOW MOVING ITEMS (need attention):"]
        lines.append("These items have low sales velocity and may require action:\n")
        
        for i, item in enumerate(items[:15], 1):
            item_name = item.get("ItemName", item.get("name", "Unknown"))
            item_code = item.get("ItemCode", item.get("code", ""))
            turnover = item.get("TurnoverRate", item.get("turnover", 0))
            on_hand = self._safe_float(item.get("CurrentOnHand", item.get("on_hand", 0)))
            severity = item.get("Severity", item.get("severity", "monitor"))
            recommendation = item.get("Recommendation", item.get("recommendation", "Monitor sales"))
            
            if severity == "critical":
                icon = "🔴 CRITICAL"
            elif severity == "warning":
                icon = "🟡 WARNING"
            else:
                icon = "🟢 MONITOR"
            
            lines.append(f"{i}. {icon} - {item_name}")
            if item_code:
                lines.append(f"   Code: {item_code}")
            lines.append(f"   Turnover rate: {turnover:.2f}x/year")
            if on_hand > 0:
                lines.append(f"   Current stock: {on_hand:,.0f} units")
            lines.append(f"   Recommendation: {recommendation}")
            lines.append("")
        
        return "\n".join(lines)