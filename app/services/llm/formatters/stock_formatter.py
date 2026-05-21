"""Stock level data formatter"""

from typing import Any, List, Dict
from .base import BaseFormatter


class StockFormatter(BaseFormatter):
    """Format stock level data for LLM"""
    
    def format(self, data: Any, language: str = "en") -> str:
        """Format stock data naturally without markdown"""
        items = data if isinstance(data, list) else [data]
        if not items:
            return "No stock data available."
        
        # Group by item
        by_item = self._group_by_item(items)
        
        lines = ["STOCK LEVEL INFORMATION:"]
        
        for item_data in by_item.values():
            # Removed ** for markdown
            lines.append(f"\n📦 {item_data['name']} (Code: {item_data['code']})")
            for wh in item_data["warehouses"]:
                lines.append(f"   🏭 {wh['warehouse']}:")
                lines.append(f"      • On Hand: {wh['on_hand']:,.1f} units")
                if wh['committed'] > 0:
                    lines.append(f"      • Committed: {wh['committed']:,.1f} units")
                    if wh['available'] < 0:
                        lines.append(f"      • Available: {wh['available']:,.1f} units ⚠️ (Backorder exists)")
                    else:
                        lines.append(f"      • Available: {wh['available']:,.1f} units")
                else:
                    lines.append(f"      • Available: {wh['available']:,.1f} units")
        
        return "\n".join(lines)
    
    def _group_by_item(self, items: List[Dict]) -> Dict:
        """Group stock items by item code/name"""
        by_item = {}
        
        for item in items:
            item_code = item.get("code", item.get("ItemCode", ""))
            item_name = item.get("name", item.get("ItemName", "Unknown"))
            key = f"{item_code}|{item_name}"
            
            if key not in by_item:
                by_item[key] = {
                    "code": item_code,
                    "name": item_name,
                    "warehouses": []
                }
            
            warehouse = item.get("warehouse", item.get("WhsCode", "Unknown"))
            on_hand = self._safe_float(item.get("stock", item.get("on_hand", item.get("CurrentOnHand", 0))))
            committed = self._safe_float(item.get("committed", item.get("CurrentIsCommited", 0)))
            available = on_hand - committed if committed else on_hand
            
            by_item[key]["warehouses"].append({
                "warehouse": warehouse,
                "on_hand": round(on_hand, 1),
                "committed": round(committed, 1),
                "available": round(available, 1)
            })
        
        return by_item