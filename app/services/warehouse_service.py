"""
warehouse_service.py
====================
Warehouse intelligence layer for Leysco ERP.

Features:
1. Stock level summaries per warehouse
2. Warehouse details (address, manager, status)
3. Search/filter by name or region
4. Low stock alerts per warehouse
"""

import logging
from typing import Dict, List, Optional
from app.services.leysco_api_service import LeyscoAPIService

logger = logging.getLogger(__name__)


class WarehouseService:
    def __init__(self):
        self.api = LeyscoAPIService()
    
    # ------------------------------------------------------------------
    # FEATURE 1: Stock Level Summaries
    # ------------------------------------------------------------------
    
    def get_warehouse_stock_summary(self, whscode: str) -> Dict:
        """
        Get aggregated stock summary for a warehouse.
        
        Returns:
        {
            "warehouse_code": str,
            "warehouse_name": str,
            "total_items": int,
            "total_units": int,
            "total_committed": int,
            "total_available": int,
            "top_items": [{"ItemCode", "ItemName", "OnHand", "Committed", "Available"}],
            "low_stock_items": [...]  # items below threshold
        }
        """
        inventory = self.api.get_inventory_report(search="")
        
        # Filter to this warehouse
        wh_items = [
            itm for itm in inventory
            if (itm.get("WhsCode") or "").upper() == whscode.upper()
        ]
        
        if not wh_items:
            return {"error": f"No inventory found for warehouse {whscode}"}
        
        # Aggregate by item
        items_map = {}
        for itm in wh_items:
            code = itm.get("ItemCode")
            if code not in items_map:
                items_map[code] = {
                    "ItemCode": code,
                    "ItemName": itm.get("ItemName"),
                    "OnHand": itm.get("CurrentOnHand", 0),
                    "Committed": itm.get("CurrentIsCommited", 0),
                    "Available": itm.get("CurrentOnHand", 0) - itm.get("CurrentIsCommited", 0),
                }
        
        items = list(items_map.values())
        
        # Low stock detection (available < 10% of on-hand OR available < 100)
        low_stock = [
            itm for itm in items
            if itm["Available"] < max(itm["OnHand"] * 0.1, 100) and itm["OnHand"] > 0
        ]
        
        return {
            "warehouse_code": whscode.upper(),
            "warehouse_name": wh_items[0].get("WhsName", whscode) if wh_items else whscode,
            "total_items": len(items),
            "total_units": sum(i["OnHand"] for i in items),
            "total_committed": sum(i["Committed"] for i in items),
            "total_available": sum(i["Available"] for i in items),
            "top_items": sorted(items, key=lambda x: x["OnHand"], reverse=True)[:10],
            "low_stock_items": sorted(low_stock, key=lambda x: x["Available"])[:20],
        }
    
    def get_all_warehouses_summary(self) -> List[Dict]:
        """
        Get stock summaries for all warehouses.
        
        Returns list of warehouse summaries sorted by total units.
        """
        warehouses = self.api.get_warehouses()
        inventory = self.api.get_inventory_report(search="")
        
        summaries = []
        for wh in warehouses:
            whscode = wh.get("WhsCode")
            if not whscode:
                continue
            
            # Filter inventory to this warehouse
            wh_items = [
                itm for itm in inventory
                if (itm.get("WhsCode") or "").upper() == whscode.upper()
            ]
            
            total_units = sum(itm.get("CurrentOnHand", 0) for itm in wh_items)
            total_committed = sum(itm.get("CurrentIsCommited", 0) for itm in wh_items)
            
            summaries.append({
                "WhsCode": whscode,
                "WhsName": wh.get("WhsName", whscode),
                "total_items": len(set(itm.get("ItemCode") for itm in wh_items)),
                "total_units": total_units,
                "total_committed": total_committed,
                "total_available": total_units - total_committed,
                "details": wh,  # full warehouse record
            })
        
        return sorted(summaries, key=lambda x: x["total_units"], reverse=True)
    
    # ------------------------------------------------------------------
    # FEATURE 2: Warehouse Details
    # ------------------------------------------------------------------
    
    def get_warehouse_details(self, whscode: str) -> Optional[Dict]:
        """
        Get full details for a warehouse.
        
        Returns warehouse record with all available fields:
        - WhsCode, WhsName
        - Address fields (if available)
        - Manager/contact (if available)
        - Active/inactive status
        - Plus stock summary
        """
        warehouses = self.api.get_warehouses(search=whscode)
        
        if not warehouses:
            return None
        
        # Exact match on code
        wh = next(
            (w for w in warehouses if (w.get("WhsCode") or "").upper() == whscode.upper()),
            warehouses[0]  # fallback to first result
        )
        
        # Enrich with stock summary
        stock_summary = self.get_warehouse_stock_summary(wh.get("WhsCode", whscode))
        
        return {
            **wh,
            "stock_summary": stock_summary,
        }
    
    # ------------------------------------------------------------------
    # FEATURE 3: Search/Filter
    # ------------------------------------------------------------------
    
    def search_warehouses(
        self,
        query: str = "",
        region: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict]:
        """
        Search warehouses by name, code, or region.
        
        Args:
            query: Search term (matches name or code)
            region: Filter by region/territory (if field exists)
            active_only: Only return active warehouses
        
        Returns list of matching warehouses with basic info.
        """
        warehouses = self.api.get_warehouses(search=query)
        
        # Apply filters
        results = []
        for wh in warehouses:
            # Active filter (if Inactive field exists)
            if active_only and wh.get("Inactive") == "Y":
                continue
            
            # Region filter (if field exists - check common SAP field names)
            if region:
                wh_region = (
                    wh.get("Region") or
                    wh.get("Territory") or
                    wh.get("Location") or
                    ""
                ).lower()
                if region.lower() not in wh_region:
                    continue
            
            results.append(wh)
        
        return results
    
    # ------------------------------------------------------------------
    # FEATURE 4: Low Stock Alerts
    # ------------------------------------------------------------------
    
    def get_low_stock_alerts(
        self,
        whscode: Optional[str] = None,
        threshold_pct: float = 0.1,
        min_available: int = 100,
    ) -> List[Dict]:
        """
        Find items with low available stock across warehouses.
        
        Low stock = Available < max(OnHand * threshold_pct, min_available)
        
        Args:
            whscode: Optional - filter to specific warehouse
            threshold_pct: % threshold (default 10%)
            min_available: Minimum units threshold (default 100)
        
        Returns list of low stock items sorted by severity.
        """
        inventory = self.api.get_inventory_report(search="")
        
        # Filter by warehouse if specified
        if whscode:
            inventory = [
                itm for itm in inventory
                if (itm.get("WhsCode") or "").upper() == whscode.upper()
            ]
        
        # Aggregate by item+warehouse
        alerts = []
        for itm in inventory:
            on_hand = itm.get("CurrentOnHand", 0)
            committed = itm.get("CurrentIsCommited", 0)
            available = on_hand - committed
            
            # Skip if no stock at all
            if on_hand == 0:
                continue
            
            # Check threshold
            threshold = max(on_hand * threshold_pct, min_available)
            if available < threshold:
                alerts.append({
                    "ItemCode": itm.get("ItemCode"),
                    "ItemName": itm.get("ItemName"),
                    "WhsCode": itm.get("WhsCode"),
                    "OnHand": on_hand,
                    "Committed": committed,
                    "Available": available,
                    "Threshold": int(threshold),
                    "Severity": "CRITICAL" if available < threshold * 0.5 else "LOW",
                })
        
        # Sort by available quantity (lowest first)
        return sorted(alerts, key=lambda x: x["Available"])
    
    def get_warehouse_low_stock_summary(self) -> Dict[str, List[Dict]]:
        """
        Group low stock alerts by warehouse.
        
        Returns:
        {
            "KDISPAT1": [{"ItemCode", "ItemName", "Available", "Severity"}, ...],
            "KKJSHWS1": [...],
        }
        """
        alerts = self.get_low_stock_alerts()
        
        by_warehouse = {}
        for alert in alerts:
            whscode = alert["WhsCode"]
            if whscode not in by_warehouse:
                by_warehouse[whscode] = []
            by_warehouse[whscode].append(alert)
        
        return by_warehouse