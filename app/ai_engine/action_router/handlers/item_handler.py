"""Item and warehouse related intent handlers"""

from typing import Dict, Any
import logging
import re
from ..base_handler import BaseHandler
from ..constants import SKIP_GROUPS, SKIP_PREFIXES
from app.services.leysco_api.utils import normalize_response  # FIXED: was self.api._normalize()

logger = logging.getLogger(__name__)


class ItemHandler(BaseHandler):
    """Handler for item and warehouse related intents"""

    def get_items(self, item_name: str, quantity: int, language: str) -> dict:
        """Optimized GET_ITEMS with single API call."""
        try:
            url = f"{self.api.base_url}/item_masterdata"
            params = {"page": 1, "per_page": min(quantity * 2, 200), "search": item_name}
            resp = self.api.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                items = normalize_response(resp.json())  # FIXED
            else:
                logger.error(f"Error fetching items: {resp.status_code} {resp.text[:300]}")
                items = []
        except Exception as e:
            logger.error(f"Error fetching items: {e}")
            items = []

        if not items:
            if language == "sw":
                return {"message": "Hakuna bidhaa zilizopatikana. Jaribu kutafuta bidhaa mahususi kama 'kabeji' au 'vegimax'.", "data": []}
            return {"message": "No items found. Try searching for a specific product like 'cabbage' or 'vegimax'.", "data": []}

        # Filter out packing materials
        filtered = []
        packing_count = 0

        for itm in items:
            code = itm.get("ItemCode", "")
            group = (itm.get("item_group") or {}).get("ItmsGrpNam", "").upper()
            is_packing = group in SKIP_GROUPS or any(code.startswith(p) for p in SKIP_PREFIXES)
            if is_packing:
                packing_count += 1
                if itm.get("SellItem") == "Y" or itm.get("PrchseItem") == "Y":
                    filtered.append(itm)
            else:
                filtered.append(itm)

        items_to_show = (filtered if filtered else items)[:quantity]

        if language == "sw":
            text = f"Imepatikana bidhaa {len(items_to_show)}:\n\n"
            for i, itm in enumerate(items_to_show, 1):
                name = itm.get('ItemName', 'Unknown')
                code = itm.get('ItemCode', 'N/A')
                group = (itm.get("item_group") or {}).get("ItmsGrpNam", "Unknown")
                on_hand = float(itm.get("OnHand", 0))
                stock_info = f" | Hisa: {on_hand:,.0f}" if on_hand > 0 else ""
                text += f"{i}. {name} ({code}) — {group}{stock_info}\n"
        else:
            text = f"Found {len(items_to_show)} items:\n\n"
            for i, itm in enumerate(items_to_show, 1):
                name = itm.get('ItemName', 'Unknown')
                code = itm.get('ItemCode', 'N/A')
                group = (itm.get("item_group") or {}).get("ItmsGrpNam", "Unknown")
                on_hand = float(itm.get("OnHand", 0))
                stock_info = f" | Stock: {on_hand:,.0f}" if on_hand > 0 else ""
                text += f"{i}. {name} ({code}) — {group}{stock_info}\n"

        if len(items) > quantity:
            text += f"\n... and {len(items) - quantity} more items."

        if packing_count > 0:
            if language == "sw":
                text += f"\n\nKumbuka: Bidhaa {packing_count} za vifaa vya kufungashia zimefichwa. Uliza 'nionyeshe bidhaa zote pamoja na vifungashio' kuziona."
            else:
                text += f"\n\nNote: {packing_count} packing/raw material items were hidden. Ask for 'show me all items including packing' to see them."

        return {"message": text, "data": items_to_show}

    def get_sellable_items(self, item_name: str, quantity: int, language: str) -> dict:
        """Get items that can be sold."""
        return self._get_filtered_items(item_name, quantity, "SellItem", "Sellable", language)

    def get_purchasable_items(self, item_name: str, quantity: int, language: str) -> dict:
        """Get items that can be purchased."""
        return self._get_filtered_items(item_name, quantity, "PrchseItem", "Purchasable", language)

    def get_inventory_items(self, item_name: str, quantity: int, language: str) -> dict:
        """Get inventory items."""
        return self._get_filtered_items(item_name, quantity, "InvntItem", "Inventory", language)

    def _get_filtered_items(self, item_name: str, quantity: int, flag: str, label: str, language: str) -> dict:
        """Helper to get filtered items."""
        all_items = []
        try:
            url = f"{self.api.base_url}/item_masterdata"
            resp = self.api.session.get(url, params={"page": 1, "per_page": 200, "search": item_name}, timeout=15)
            if resp.status_code == 200:
                all_items = normalize_response(resp.json())  # FIXED
            else:
                logger.error(f"Error fetching items: {resp.status_code} {resp.text[:300]}")
        except Exception as e:
            logger.error(f"Error fetching items: {e}")

        if not all_items:
            if language == "sw":
                return {"message": "Hakuna bidhaa zilizopatikana kwenye mfumo.", "data": []}
            return {"message": "No items found in the system.", "data": []}

        filtered = [i for i in all_items if i.get(flag) == "Y"]
        items_to_show = (filtered if filtered else all_items)[:quantity]

        if language == "sw":
            text = f"Bidhaa za {label} ({len(items_to_show)} kati ya {len(filtered)} zilizopatikana):\n\n"
        else:
            text = f"{label} Items ({len(items_to_show)} of {len(filtered)} found):\n\n"

        for i, itm in enumerate(items_to_show, 1):
            text += f"{i}. {itm.get('ItemName')} ({itm.get('ItemCode')})\n"

        return {"message": text, "data": items_to_show}

    def get_item_details(self, item_name: str, language: str) -> dict:
        """Get detailed information about a specific item."""
        if not item_name:
            return self._missing("the item you want details for", language)

        item = self.api.get_item_by_name(item_name)
        if not item:
            return self._not_found("Item", item_name, language)

        on_hand = float(item.get("OnHand", 0))
        committed = float(item.get("IsCommited", 0))

        if language == "sw":
            text = f"Maelezo ya Bidhaa\n\nJina: {item.get('ItemName')}\nMsimbo: {item.get('ItemCode')}\nKundi: {item.get('item_group', {}).get('ItmsGrpNam', 'N/A')}\nHisa: {on_hand:,.0f}\nIliyoahidiwa: {committed:,.0f}\nInayopatikana: {on_hand - committed:,.0f}\n"
        else:
            text = f"Item Details\n\nName: {item.get('ItemName')}\nCode: {item.get('ItemCode')}\nGroup: {item.get('item_group', {}).get('ItmsGrpNam', 'N/A')}\nOn Hand: {on_hand:,.0f}\nCommitted: {committed:,.0f}\nAvailable: {on_hand - committed:,.0f}\n"

        return {"message": text, "data": [item]}

    def get_items_advanced(self, item_name: str, quantity: int, warehouse_name: str, language: str) -> dict:
        """Get advanced inventory information."""
        inventory = self.api.get_inventory_report(search=item_name, limit=200)
        if not inventory:
            if language == "sw":
                return {"message": "Hakuna rekodi za hisa zilizopatikana.", "data": []}
            return {"message": "No inventory records found.", "data": []}

        warehouses = self.api.get_warehouses()
        wh_map = {wh.get("WhsCode"): wh.get("WhsName", wh.get("WhsCode")) for wh in warehouses}
        items_map = {}

        for row in inventory:
            code = row.get("ItemCode")
            wh_code = row.get("WhsCode")
            wh = wh_map.get(wh_code, wh_code or "Unknown")
            qty = float(row.get("CurrentOnHand") or 0)

            if warehouse_name and warehouse_name.lower() not in wh.lower():
                continue

            if code not in items_map:
                items_map[code] = {"ItemCode": code, "ItemName": row.get("ItemName"), "TotalStock": 0, "warehouses": []}
            items_map[code]["TotalStock"] += qty
            items_map[code]["warehouses"].append(f"{wh} ({qty:,.0f})")

        items = list(items_map.values())[:quantity]

        if language == "sw":
            text = f"Bidhaa za Hisa ({len(items)} zilizopatikana):\n"
        else:
            text = f"Inventory Items ({len(items)} found):\n"

        for i, itm in enumerate(items, 1):
            text += f"{i}. {itm['ItemName']} — {'Jumla ya Hisa' if language == 'sw' else 'Total Stock'}: {itm['TotalStock']:,.0f}\n"

        return {"message": text, "data": items}

    def get_warehouses(self, warehouse_name: str, language: str) -> dict:
        """Get warehouse information."""
        if warehouse_name:
            warehouses = self.warehouse.search_warehouses(query=warehouse_name, active_only=True)
            if not warehouses:
                if language == "sw":
                    return {"message": f"Hakuna ghala lililopatikana linalolingana na '{warehouse_name}'.", "data": []}
                return {"message": f"No warehouses found matching '{warehouse_name}'.", "data": []}

            wh = warehouses[0]
            stock_summary = self.warehouse.get_warehouse_stock_summary(wh.get("WhsCode"))

            if language == "sw":
                text = f"{wh.get('WhsName')} ({wh.get('WhsCode')})\n\nMuhtasari wa Hisa:\n"
                text += f"   Jumla ya Bidhaa: {stock_summary.get('total_items', 0):,}\n"
                text += f"   Inayopatikana: {stock_summary.get('total_available', 0):,}\n"
            else:
                text = f"{wh.get('WhsName')} ({wh.get('WhsCode')})\n\nStock Summary:\n"
                text += f"   Total Items: {stock_summary.get('total_items', 0):,}\n"
                text += f"   Available: {stock_summary.get('total_available', 0):,}\n"

            return {"message": text, "data": [stock_summary]}
        else:
            summaries = self.warehouse.get_all_warehouses_summary()
            active = [s for s in summaries if s["details"].get("Inactive") != "Y"]

            if not active:
                if language == "sw":
                    return {"message": "Hakuna maghala yanayotumika yaliyopatikana.", "data": []}
                return {"message": "No active warehouses found.", "data": []}

            if language == "sw":
                text = f"Imepatikana maghala {len(active)} yanayotumika:\n\n"
                for s in active[:15]:
                    text += f"{s['WhsName']} ({s['WhsCode']}) — Bidhaa: {s['total_items']:,} | Inayopatikana: {s['total_available']:,}\n"
            else:
                text = f"Found {len(active)} active warehouses:\n\n"
                for s in active[:15]:
                    text += f"{s['WhsName']} ({s['WhsCode']}) — Items: {s['total_items']:,} | Available: {s['total_available']:,}\n"

            return {"message": text, "data": active}

    def get_warehouse_stock(self, warehouse_name: str, language: str) -> dict:
        """Get stock for a specific warehouse."""
        if not warehouse_name:
            return {"message": "Tafadhali taja jina la ghala au msimbo." if language == "sw" else "Please specify a warehouse name or code.", "data": []}

        warehouses = self.warehouse.search_warehouses(query=warehouse_name)
        if not warehouses:
            if language == "sw":
                return {"message": f"Ghala '{warehouse_name}' halijapatikana.", "data": []}
            return {"message": f"Warehouse '{warehouse_name}' not found.", "data": []}

        wh = warehouses[0]
        stock_summary = self.warehouse.get_warehouse_stock_summary(wh.get("WhsCode"))

        if "error" in stock_summary:
            return {"message": stock_summary["error"], "data": []}

        if language == "sw":
            text = f"Ripoti ya Hisa: {wh.get('WhsName')}\n\n"
            text += f"Jumla ya Bidhaa: {stock_summary['total_items']:,} | Inayopatikana: {stock_summary['total_available']:,}\n\n"
            for i, itm in enumerate(stock_summary.get("top_items", [])[:10], 1):
                text += f"{i}. {itm['ItemName']} — Hisa: {itm['OnHand']:,}\n"
        else:
            text = f"Stock Report: {wh.get('WhsName')}\n\n"
            text += f"Total Items: {stock_summary['total_items']:,} | Available: {stock_summary['total_available']:,}\n\n"
            for i, itm in enumerate(stock_summary.get("top_items", [])[:10], 1):
                text += f"{i}. {itm['ItemName']} — On Hand: {itm['OnHand']:,}\n"

        return {"message": text, "data": [stock_summary]}

    def get_low_stock_alerts(self, warehouse_name: str, language: str) -> dict:
        """Get low stock alerts."""
        if warehouse_name:
            warehouses = self.warehouse.search_warehouses(query=warehouse_name)
            if not warehouses:
                if language == "sw":
                    return {"message": f"Ghala '{warehouse_name}' halijapatikana.", "data": []}
                return {"message": f"Warehouse '{warehouse_name}' not found.", "data": []}
            alerts = self.warehouse.get_low_stock_alerts(whscode=warehouses[0].get("WhsCode"))
            title = f"Low Stock Alerts: {warehouses[0].get('WhsName')}"
        else:
            alerts = self.warehouse.get_low_stock_alerts()
            title = "Low Stock Alerts (All Warehouses)"

        if not alerts:
            if language == "sw":
                return {"message": "Hakuna arifa za hisa chache kwa sasa.", "data": []}
            return {"message": "No low stock alerts at this time.", "data": []}

        critical = [a for a in alerts if a["Severity"] == "CRITICAL"]
        low = [a for a in alerts if a["Severity"] == "LOW"]

        if language == "sw":
            text = f"{title}\n\n"
            if critical:
                text += f"MUHIMU ({len(critical)} bidhaa):\n"
                for a in critical[:10]:
                    text += f"• {a['ItemName']} @ {a['WhsCode']} — Inayopatikana: {a['Available']:,}\n"
            if low:
                text += f"\nCHACHE ({len(low)} bidhaa):\n"
                for a in low[:10]:
                    text += f"• {a['ItemName']} @ {a['WhsCode']} — Inayopatikana: {a['Available']:,}\n"
        else:
            text = f"{title}\n\n"
            if critical:
                text += f"CRITICAL ({len(critical)} items):\n"
                for a in critical[:10]:
                    text += f"• {a['ItemName']} @ {a['WhsCode']} — Available: {a['Available']:,}\n"
            if low:
                text += f"\nLOW ({len(low)} items):\n"
                for a in low[:10]:
                    text += f"• {a['ItemName']} @ {a['WhsCode']} — Available: {a['Available']:,}\n"

        return {"message": text, "data": alerts}