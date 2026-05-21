"""Pricing related intent handlers"""

from typing import Dict, Any
import logging
from ..base_handler import BaseHandler
from ..constants import SKIP_GROUPS, SKIP_PREFIXES

logger = logging.getLogger(__name__)


class PricingHandler(BaseHandler):
    """Handler for pricing related intents"""
    
    def get_item_price(self, item_name: str, language: str) -> dict:
        """Get price for an item."""
        if not item_name:
            return self._missing("an item name", language)
        
        items = self.api.get_items(search=item_name, limit=50)
        if not items:
            if language == "sw":
                return {"message": f"Hakuna bidhaa iliyopatikana inayolingana na '{item_name}'.", "data": []}
            return {"message": f"No items found matching '{item_name}'.", "data": []}
        
        results = []
        if language == "sw":
            text_lines = [f"Bei za '{item_name}'\n"]
        else:
            text_lines = [f"Prices for '{item_name}'\n"]
        
        priced_items = []
        skipped_items = []
        
        for itm in items:
            group = (itm.get("item_group") or {}).get("ItmsGrpNam", "").upper()
            code = (itm.get("ItemCode") or "").upper()
            
            if group in SKIP_GROUPS or code.startswith(SKIP_PREFIXES):
                skipped_items.append({
                    "name": itm.get("ItemName"),
                    "code": code,
                    "reason": f"{group} - internal use only"
                })
                continue
            
            priced_items.append(itm)
        
        if not priced_items:
            if skipped_items:
                if language == "sw":
                    text = f"Imepatikana bidhaa {len(skipped_items)} zinazolingana na '{item_name}', lakini ni nyenzo za ndani:\n\n"
                else:
                    text = f"Found {len(skipped_items)} items matching '{item_name}', but they are internal materials:\n\n"
                
                for skip in skipped_items[:5]:
                    text += f"• {skip['name']} ({skip['code']})\n"
                    text += f"  {skip['reason']}\n"
                
                if len(skipped_items) > 5:
                    if language == "sw":
                        text += f"\n... na nyingine {len(skipped_items) - 5}\n"
                    else:
                        text += f"\n... and {len(skipped_items) - 5} more\n"
                
                if language == "sw":
                    text += "\nKidokezo: Jaribu kutafuta bidhaa zilizokamilika kama 'kabeji', 'vegimax', au 'nyanya'."
                else:
                    text += "\nTip: Try searching for finished products like 'cabbage', 'vegimax', or 'tomato'."
                
                return {"message": text, "data": []}
            else:
                if language == "sw":
                    return {"message": f"Hakuna bidhaa iliyopatikana inayolingana na '{item_name}'.", "data": []}
                return {"message": f"No items found matching '{item_name}'.", "data": []}
        
        for itm in priced_items:
            item_code = itm.get("ItemCode")
            item_name_full = itm.get("ItemName")
            
            is_sellable = itm.get("SellItem") == "Y"
            is_purchasable = itm.get("PrchseItem") == "Y"
            is_inventory = itm.get("InvntItem") == "Y"
            
            price_result = self.pricing.get_price(item_code=item_code)
            if not price_result["found"]:
                price_result = self.pricing.get_price_any_list(item_code=item_code)
            
            item_type = []
            if is_sellable:
                item_type.append("For Sale" if language != "sw" else "Inauzwa")
            if is_purchasable:
                item_type.append("Purchase" if language != "sw" else "Inanunuliwa")
            if is_inventory:
                item_type.append("Inventory" if language != "sw" else "Hisa")
            type_str = f" [{', '.join(item_type)}]" if item_type else ""
            
            if price_result["found"]:
                gross_tag = " (incl. VAT)" if price_result["is_gross_price"] else ""
                uom_tag = f" per UOM-{price_result['uom_entry']}" if price_result["uom_entry"] else ""
                text_lines.append(
                    f"• {item_name_full} ({item_code}){type_str}\n"
                    f"  KES {price_result['price']:,.2f}{gross_tag}{uom_tag} [{price_result['price_list_name']}]"
                )
            else:
                text_lines.append(
                    f"• {item_name_full} ({item_code}){type_str}\n"
                    f"  No price set"
                )
            
            results.append({
                "ItemCode": item_code,
                "ItemName": item_name_full,
                "Price": price_result["price"],
                "Currency": "KES",
                "PriceListName": price_result["price_list_name"],
                "IsGrossPrice": price_result["is_gross_price"],
                "UomEntry": price_result["uom_entry"],
                "Found": price_result["found"],
                "Note": price_result["note"],
                "IsSellable": is_sellable,
                "IsPurchasable": is_purchasable,
                "IsInventory": is_inventory,
            })
        
        final_message = "\n".join(text_lines)
        if not final_message or final_message in [f"Bei za '{item_name}'\n", f"Prices for '{item_name}'\n"]:
            if language == "sw":
                final_message = f"Imepatikana bidhaa {len(results)} zinazolingana na '{item_name}' zenye bei."
            else:
                final_message = f"Found {len(results)} items matching '{item_name}' with pricing information."
        
        logger.info(f"GET_ITEM_PRICE returning message length: {len(final_message)} chars, {len(results)} items")
        return {"message": final_message, "data": results}
    
    def get_customer_price(self, item_name: str, customer_name: str, language: str) -> dict:
        """Get customer-specific price for an item."""
        if not item_name:
            return self._missing("an item name", language)
        if not customer_name:
            return self._missing("a customer name", language)
        
        customer, search_name = self.router._resolve_customer(customer_name, item_name)
        if not customer:
            return self._not_found("Customer", search_name, language)
        
        items = self.api.get_items(search=item_name, limit=20)
        if not items:
            return self._not_found("Item", item_name, language)
        
        results = []
        if language == "sw":
            text_lines = [f"{customer.get('CardName')} - Bei\n"]
        else:
            text_lines = [f"{customer.get('CardName')} - Pricing\n"]
        
        for itm in items:
            pr = self.pricing.get_price_for_customer(item_code=itm.get("ItemCode"), customer=customer)
            if pr["found"]:
                text_lines.append(f"• {itm.get('ItemName')}: KES {pr['price']:,.2f}")
                results.append(pr)
        
        if not results:
            if language == "sw":
                text_lines.append("Hakuna bei zilizopatikana kwa bidhaa hizi.")
            else:
                text_lines.append("No prices available for these items.")
        
        return {"message": "\n".join(text_lines), "data": results}