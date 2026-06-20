"""Pricing related intent handlers"""

import re
from typing import Dict, Any
import logging
from ..base_handler import BaseHandler
from ..constants import SKIP_GROUPS, SKIP_PREFIXES

logger = logging.getLogger(__name__)


class PricingHandler(BaseHandler):
    """Handler for pricing related intents"""
    
    def get_item_price(self, item_name: str, language: str, entities: dict = None) -> dict:
        """
        Get price for an item.
        
        Behavior:
        - If a specific size was requested (e.g., "vegimax 250ml"), return only that item
        - If no size was specified (e.g., "price of vegimax"), return ALL matching items with prices
        """
        if not item_name:
            return self._missing("an item name", language)
        
        # ====================================================================
        # FIX: Check if a specific size was requested in the original query
        # ====================================================================
        has_size_in_query = False
        if entities:
            original_query = entities.get("_original_query", "")
            # Check for size patterns in the original query
            has_size_in_query = bool(re.search(
                r'\d+(?:ml|ML|mL|kg|KG|g|G|l|L|lt|LT)',
                original_query
            ))
            logger.info(f"Item: '{item_name}', has_size_in_query: {has_size_in_query}")
        
        items = self.api.get_items(search=item_name, limit=50)
        if not items:
            if language == "sw":
                return {"message": f"Hakuna bidhaa iliyopatikana inayolingana na '{item_name}'.", "data": []}
            return {"message": f"No items found matching '{item_name}'.", "data": []}
        
        results = []
        
        # ====================================================================
        # FIX: If no specific size was requested, show ALL matching items
        # ====================================================================
        if not has_size_in_query:
            if language == "sw":
                text_lines = [f"Bei zote za '{item_name}'\n"]
            else:
                text_lines = [f"All prices for '{item_name}'\n"]
            
            priced_items = []
            skipped_items = []
            
            for itm in items:
                group = (itm.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                code = (itm.get("ItemCode") or "").upper()
                
                # Skip internal items
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
            
            # ================================================================
            # Get prices for ALL priced items
            # ================================================================
            priced_results = []
            unpriced_results = []
            
            for itm in priced_items:
                item_code = itm.get("ItemCode")
                item_name_full = itm.get("ItemName")
                on_hand = itm.get("OnHand", 0)
                
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
                
                result_data = {
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
                    "OnHand": on_hand,
                }
                results.append(result_data)
                
                if price_result["found"]:
                    priced_results.append((itm, price_result, type_str))
                else:
                    unpriced_results.append((itm, price_result, type_str))
            
            # ================================================================
            # Show priced items first
            # ================================================================
            if priced_results:
                for itm, price_result, type_str in priced_results:
                    gross_tag = " (incl. VAT)" if price_result["is_gross_price"] else ""
                    uom_tag = f" per UOM-{price_result['uom_entry']}" if price_result["uom_entry"] else ""
                    on_hand = itm.get("OnHand", 0)
                    stock_info = f" | Stock: {on_hand:,}" if on_hand > 0 else ""
                    
                    text_lines.append(
                        f"• **{itm.get('ItemName')}** ({itm.get('ItemCode')}){type_str}\n"
                        f"  💰 KES {price_result['price']:,.2f}{gross_tag}{uom_tag}{stock_info}\n"
                        f"  📋 {price_result['price_list_name']}"
                    )
            
            # ================================================================
            # Show unpriced items with a note
            # ================================================================
            if unpriced_results:
                if language == "sw":
                    text_lines.append(f"\nℹ️ Bidhaa bila bei:")
                else:
                    text_lines.append(f"\nℹ️ Items without prices:")
                
                for itm, price_result, type_str in unpriced_results[:5]:
                    text_lines.append(f"• {itm.get('ItemName')} ({itm.get('ItemCode')}) — No price set")
                
                if len(unpriced_results) > 5:
                    if language == "sw":
                        text_lines.append(f"... na nyingine {len(unpriced_results) - 5}")
                    else:
                        text_lines.append(f"... and {len(unpriced_results) - 5} more")
            
            # ================================================================
            # Add tip for specific sizes
            # ================================================================
            if len(priced_results) > 1:
                if language == "sw":
                    text_lines.append(f"\n💡 **Kidokezo:** Taja ukubwa maalum kama 'vegimax 250ml' kupata bei ya bidhaa moja.")
                else:
                    text_lines.append(f"\n💡 **Tip:** Specify a size like 'vegimax 250ml' to get a single item price.")
            
            final_message = "\n".join(text_lines)
            logger.info(f"GET_ITEM_PRICE (all items) returning {len(results)} items")
            return {"message": final_message, "data": results}
        
        # ====================================================================
        # FIX: Specific size was requested - return only the exact match
        # ====================================================================
        else:
            if language == "sw":
                text_lines = [f"Bei ya '{item_name}'\n"]
            else:
                text_lines = [f"Price for '{item_name}'\n"]
            
            # Find the specific item matching the name
            specific_item = None
            for itm in items:
                if itm.get("ItemName") == item_name:
                    specific_item = itm
                    break
            
            # If not found by exact name, try partial match
            if not specific_item:
                for itm in items:
                    if item_name.lower() in itm.get("ItemName", "").lower():
                        specific_item = itm
                        break
            
            if not specific_item:
                if language == "sw":
                    return {"message": f"Bidhaa '{item_name}' haikupatikana. Jaribu kutafuta 'vegimax' kuona toleo zote.", "data": []}
                return {"message": f"Item '{item_name}' not found. Try searching for 'vegimax' to see all variants.", "data": []}
            
            # Get price for the specific item
            item_code = specific_item.get("ItemCode")
            item_name_full = specific_item.get("ItemName")
            on_hand = specific_item.get("OnHand", 0)
            
            is_sellable = specific_item.get("SellItem") == "Y"
            is_purchasable = specific_item.get("PrchseItem") == "Y"
            is_inventory = specific_item.get("InvntItem") == "Y"
            
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
            
            result_data = {
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
                "OnHand": on_hand,
            }
            results.append(result_data)
            
            if price_result["found"]:
                gross_tag = " (incl. VAT)" if price_result["is_gross_price"] else ""
                uom_tag = f" per UOM-{price_result['uom_entry']}" if price_result["uom_entry"] else ""
                stock_info = f" | Stock: {on_hand:,}" if on_hand > 0 else ""
                
                if language == "sw":
                    text_lines.append(
                        f"• **{item_name_full}** ({item_code}){type_str}\n"
                        f"  💰 KES {price_result['price']:,.2f}{gross_tag}{uom_tag}{stock_info}\n"
                        f"  📋 {price_result['price_list_name']}"
                    )
                else:
                    text_lines.append(
                        f"• **{item_name_full}** ({item_code}){type_str}\n"
                        f"  💰 KES {price_result['price']:,.2f}{gross_tag}{uom_tag}{stock_info}\n"
                        f"  📋 {price_result['price_list_name']}"
                    )
            else:
                if language == "sw":
                    text_lines.append(
                        f"• **{item_name_full}** ({item_code}){type_str}\n"
                        f"  ❌ Bei haijasajiliwa"
                    )
                else:
                    text_lines.append(
                        f"• **{item_name_full}** ({item_code}){type_str}\n"
                        f"  ❌ No price set"
                    )
            
            final_message = "\n".join(text_lines)
            logger.info(f"GET_ITEM_PRICE (specific item) returning 1 item")
            return {"message": final_message, "data": results}
    
    def get_customer_price(self, item_name: str, customer_name: str, language: str, entities: dict = None) -> dict:
        """Get customer-specific price for an item."""
        if not item_name:
            return self._missing("an item name", language)
        if not customer_name:
            return self._missing("a customer name", language)
        
        customer, search_name = self.router._resolve_customer(customer_name, item_name)
        if not customer:
            return self._not_found("Customer", search_name, language)
        
        # ====================================================================
        # Check if a specific size was requested
        # ====================================================================
        has_size_in_query = False
        if entities:
            original_query = entities.get("_original_query", "")
            has_size_in_query = bool(re.search(
                r'\d+(?:ml|ML|mL|kg|KG|g|G|l|L|lt|LT)',
                original_query
            ))
        
        items = self.api.get_items(search=item_name, limit=50)
        if not items:
            return self._not_found("Item", item_name, language)
        
        results = []
        if language == "sw":
            text_lines = [f"{customer.get('CardName')} - Bei\n"]
        else:
            text_lines = [f"{customer.get('CardName')} - Pricing\n"]
        
        # ====================================================================
        # If no specific size, show all items with customer prices
        # ====================================================================
        for itm in items:
            # Skip internal items
            group = (itm.get("item_group") or {}).get("ItmsGrpNam", "").upper()
            code = (itm.get("ItemCode") or "").upper()
            if group in SKIP_GROUPS or code.startswith(SKIP_PREFIXES):
                continue
            
            pr = self.pricing.get_price_for_customer(item_code=itm.get("ItemCode"), customer=customer)
            if pr["found"]:
                on_hand = itm.get("OnHand", 0)
                stock_info = f" | Stock: {on_hand:,}" if on_hand > 0 else ""
                text_lines.append(f"• {itm.get('ItemName')}: KES {pr['price']:,.2f}{stock_info}")
                results.append({
                    "ItemCode": itm.get("ItemCode"),
                    "ItemName": itm.get("ItemName"),
                    "Price": pr["price"],
                    "Currency": "KES",
                    "Customer": customer.get("CardName"),
                    "OnHand": on_hand,
                })
        
        if not results:
            if language == "sw":
                text_lines.append("Hakuna bei zilizopatikana kwa bidhaa hizi.")
            else:
                text_lines.append("No prices available for these items.")
        
        return {"message": "\n".join(text_lines), "data": results}