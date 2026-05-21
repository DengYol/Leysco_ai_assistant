"""Recommendation intent handlers"""

from typing import Dict, Any
import logging
import re
from datetime import datetime
from ..base_handler import BaseHandler

logger = logging.getLogger(__name__)


class RecommendationHandler(BaseHandler):
    """Handler for recommendation related intents"""
    
    def recommend_items(self, item_name: str, customer_name: str, limit: int, language: str) -> dict:
        """Get item recommendations."""
        try:
            logger.info(f"Recommendations - item: {item_name}, customer: {customer_name}, limit: {limit}")
            
            recommended = []
            
            if item_name:
                items = self.api.get_items(search=item_name, limit=1)
                if items:
                    recommended = self.recommender.get_related_items(items[0].get("ItemCode"), limit=limit)
                    logger.info(f"Got {len(recommended)} related items for {item_name}")
                else:
                    recommended = self.recommender.get_recommended_items(limit=limit)
                    logger.info(f"Item not found, returning {len(recommended)} popular items")
            elif customer_name:
                customer, _ = self.router._resolve_customer(customer_name)
                if customer:
                    recommended = self.recommender.get_items_for_customer(
                        customer_code=customer.get("CardCode"), 
                        limit=limit
                    )
                    logger.info(f"Got {len(recommended)} personalized items for {customer_name}")
                else:
                    recommended = self.recommender.get_recommended_items(limit=limit)
                    logger.info(f"Customer not found, returning {len(recommended)} popular items")
            else:
                recommended = self.recommender.get_recommended_items(limit=limit)
                logger.info(f"No context, returning {len(recommended)} popular items")
            
            if not recommended:
                if language == "sw":
                    return {"message": "Hakuna mapendekezo yanayopatikana kwa sasa. Tafadhali jaribu tena baadaye.", "data": []}
                return {"message": "No recommendations available at this time. Please try again later.", "data": []}
            
            # Format the response nicely
            if language == "sw":
                title = f"📋 Mapendekezo {len(recommended)} ya Bidhaa"
                if customer_name:
                    title = f"📋 Mapendekezo ya Bidhaa kwa {customer_name}"
                elif item_name:
                    title = f"📋 Bidhaa Zinazohusiana na {item_name}"
            else:
                title = f"📋 Top {len(recommended)} Recommended Items"
                if customer_name:
                    title = f"📋 Recommended Items for {customer_name}"
                elif item_name:
                    title = f"📋 Items Related to {item_name}"
            
            lines = [title, ""]
            
            for i, item in enumerate(recommended[:limit], 1):
                item_code = item.get("ItemCode")
                item_name_display = item.get("ItemName", "Unknown")
                price = item.get("Price")
                reason = item.get("Reason", "Popular choice")
                stock_status = item.get("StockStatus", "")
                
                lines.append(f"{i}. **{item_name_display}**")
                if item_code:
                    lines.append(f"   📦 Code: {item_code}")
                if price:
                    lines.append(f"   💰 Price: KES {price:,.2f}")
                if stock_status:
                    lines.append(f"   📊 Stock: {stock_status}")
                lines.append(f"   💡 {reason}")
                lines.append("")
            
            lines.append("💬 Would you like more details about any of these items?")
            
            return {
                "message": "\n".join(lines),
                "data": recommended[:limit]
            }
            
        except Exception as e:
            logger.error(f"Error in recommend_items: {e}", exc_info=True)
            if language == "sw":
                return {"message": "Samahani, nilikumbana na hitilafu wakati wa kupata mapendekezo. Tafadhali jaribu tena.", "data": []}
            return {"message": "Sorry, I encountered an error while getting recommendations. Please try again.", "data": []}
    
    def recommend_customers(self, item_name: str, customer_name: str, limit: int, language: str) -> dict:
        """Get customer recommendations."""
        try:
            logger.info(f"Customer recommendations - item: {item_name}, customer: {customer_name}, limit: {limit}")
            
            recommended = []
            
            if item_name:
                items = self.api.get_items(search=item_name, limit=1)
                if items:
                    recommended = self.recommender.get_customers_for_item(
                        item_code=items[0].get("ItemCode"), 
                        limit=limit
                    )
                    logger.info(f"Got {len(recommended)} customers for item {item_name}")
                else:
                    recommended = self.recommender.get_recommended_customers(limit=limit)
                    logger.info(f"Item not found, returning {len(recommended)} recommended customers")
            elif customer_name:
                customer, _ = self.router._resolve_customer(customer_name)
                if customer:
                    recommended = self.recommender.get_similar_customers(
                        customer_code=customer.get("CardCode"), 
                        limit=limit
                    )
                    logger.info(f"Got {len(recommended)} similar customers for {customer_name}")
                else:
                    recommended = self.recommender.get_recommended_customers(limit=limit)
                    logger.info(f"Customer not found, returning {len(recommended)} recommended customers")
            else:
                recommended = self.recommender.get_recommended_customers(limit=limit)
                logger.info(f"No context, returning {len(recommended)} recommended customers")
            
            if not recommended:
                if language == "sw":
                    return {"message": "Hakuna mapendekezo ya wateja yanayopatikana kwa sasa. Tafadhali jaribu tena baadaye.", "data": []}
                return {"message": "No customer recommendations available at this time. Please try again later.", "data": []}
            
            # Format the response nicely
            if language == "sw":
                title = f"📋 Wateja {len(recommended)} Walio Pendekezwa"
                if item_name:
                    title = f"📋 Wateja Wanaonunua {item_name}"
                elif customer_name:
                    title = f"📋 Wateja Wanafanana na {customer_name}"
            else:
                title = f"📋 Top {len(recommended)} Recommended Customers"
                if item_name:
                    title = f"📋 Customers Who Buy {item_name}"
                elif customer_name:
                    title = f"📋 Customers Similar to {customer_name}"
            
            lines = [title, ""]
            
            for i, cust in enumerate(recommended[:limit], 1):
                cust_name = cust.get("CardName", "Unknown")
                cust_code = cust.get("CardCode", "N/A")
                purchase_qty = cust.get("PurchaseQuantity", 0)
                last_purchase = cust.get("LastPurchaseDate", "")
                reason = cust.get("RecommendationReason", "")
                
                lines.append(f"{i}. **{cust_name}**")
                lines.append(f"   📦 Code: {cust_code}")
                if purchase_qty > 0:
                    lines.append(f"   📊 Quantity purchased: {purchase_qty:,.0f} units")
                if last_purchase:
                    lines.append(f"   📅 Last purchase: {last_purchase[:10]}")
                if reason:
                    lines.append(f"   💡 {reason}")
                lines.append("")
            
            lines.append("💬 Would you like more details about any of these customers?")
            
            return {
                "message": "\n".join(lines),
                "data": recommended[:limit]
            }
            
        except Exception as e:
            logger.error(f"Error in recommend_customers: {e}", exc_info=True)
            if language == "sw":
                return {"message": "Samahani, nilikumbana na hitilafu wakati wa kupata mapendekezo ya wateja. Tafadhali jaribu tena.", "data": []}
            return {"message": "Sorry, I encountered an error while getting customer recommendations. Please try again.", "data": []}
    
    def get_cross_sell(self, item_name: str, limit: int, language: str) -> dict:
        """Get cross-sell recommendations."""
        try:
            if not item_name:
                return self._missing("an item name", language)
            
            suggestions = self.recommender.get_cross_sell_suggestions(item_name, limit=limit or 5)
            
            if not suggestions:
                if language == "sw":
                    return {"message": f"Hakuna mapendekezo ya bidhaa zinazouzwa pamoja na '{item_name}'.", "data": []}
                return {"message": f"No cross-sell recommendations found for '{item_name}'.", "data": []}
            
            # Format the response
            if language == "sw":
                lines = [f"📋 Bidhaa Zinazouzwa Pamoja na {item_name}", ""]
            else:
                lines = [f"📋 Customers who bought {item_name} also bought:", ""]
            
            for i, item in enumerate(suggestions[:limit], 1):
                item_name_display = item.get("ItemName", "Unknown")
                price = item.get("Price")
                reason = item.get("Reason", "Frequently bought together")
                
                lines.append(f"{i}. **{item_name_display}**")
                if price:
                    lines.append(f"   💰 Price: KES {price:,.2f}")
                lines.append(f"   💡 {reason}")
                lines.append("")
            
            return {
                "message": "\n".join(lines),
                "data": suggestions
            }
            
        except Exception as e:
            logger.error(f"Error in get_cross_sell: {e}", exc_info=True)
            if language == "sw":
                return {"message": "Samahani, nilikumbana na hitilafu wakati wa kupata mapendekezo ya bidhaa.", "data": []}
            return {"message": "Sorry, I encountered an error while getting cross-sell recommendations.", "data": []}
    
    def get_upsell(self, item_name: str, limit: int, language: str) -> dict:
        """Get upsell recommendations."""
        try:
            if not item_name:
                return self._missing("an item name", language)
            
            suggestions = self.recommender.get_upsell_suggestions(item_name, limit=limit or 3)
            
            if not suggestions:
                if language == "sw":
                    return {"message": f"Hakuna mapendekezo ya bidhaa bora zaidi kuliko '{item_name}'.", "data": []}
                return {"message": f"No upsell recommendations found for '{item_name}'.", "data": []}
            
            # Format the response
            if language == "sw":
                lines = [f"📋 Bidhaa Bora Zaidi Kuliko {item_name}", ""]
            else:
                lines = [f"📋 Premium alternatives to {item_name}", ""]
            
            for i, item in enumerate(suggestions[:limit], 1):
                item_name_display = item.get("ItemName", "Unknown")
                price = item.get("Price")
                reason = item.get("Reason", "Better value alternative")
                
                lines.append(f"{i}. **{item_name_display}**")
                if price:
                    lines.append(f"   💰 Price: KES {price:,.2f}")
                lines.append(f"   💡 {reason}")
                lines.append("")
            
            return {
                "message": "\n".join(lines),
                "data": suggestions
            }
            
        except Exception as e:
            logger.error(f"Error in get_upsell: {e}", exc_info=True)
            if language == "sw":
                return {"message": "Samahani, nilikumbana na hitilafu wakati wa kupata mapendekezo ya bidhaa bora.", "data": []}
            return {"message": "Sorry, I encountered an error while getting upsell recommendations.", "data": []}
    
    def get_seasonal(self, message: str, limit: int, language: str) -> dict:
        """Get seasonal recommendations."""
        try:
            month = next((m for m in ["january","february","march","april","may","june","july","august","september","october","november","december"] 
                         if m in message.lower()), None)
            
            suggestions = self.recommender.get_seasonal_recommendations(month=month, limit=limit or 5)
            
            current_month = month or datetime.now().strftime("%B").lower()
            month_name = current_month.title()
            
            if not suggestions:
                if language == "sw":
                    return {"message": f"Hakuna mapendekezo ya msimu wa {month_name}.", "data": []}
                return {"message": f"No seasonal recommendations found for {month_name}.", "data": []}
            
            # Format the response
            if language == "sw":
                lines = [f"🌱 Mapendekezo ya Msimu wa {month_name}", ""]
            else:
                lines = [f"🌱 Seasonal Recommendations for {month_name}", ""]
            
            for i, item in enumerate(suggestions[:limit], 1):
                item_name_display = item.get("ItemName", "Unknown")
                price = item.get("Price")
                tip = item.get("Tip", f"Perfect for {month_name} season")
                reason = item.get("Reason", tip)
                
                lines.append(f"{i}. **{item_name_display}**")
                if price:
                    lines.append(f"   💰 Price: KES {price:,.2f}")
                lines.append(f"   💡 {reason}")
                lines.append("")
            
            return {
                "message": "\n".join(lines),
                "data": suggestions
            }
            
        except Exception as e:
            logger.error(f"Error in get_seasonal: {e}", exc_info=True)
            if language == "sw":
                return {"message": "Samahani, nilikumbana na hitilafu wakati wa kupata mapendekezo ya msimu.", "data": []}
            return {"message": "Sorry, I encountered an error while getting seasonal recommendations.", "data": []}
    
    def get_trending(self, message: str, limit: int, language: str) -> dict:
        """Get trending products."""
        try:
            days = 30
            m = re.search(r'(\d+)\s+days', message.lower())
            if m:
                days = int(m.group(1))
            
            suggestions = self.recommender.get_trending_products(days=days, limit=limit or 5)
            
            if not suggestions:
                if language == "sw":
                    return {"message": f"Hakuna bidhaa zinazovuma kwa siku {days} zilizopita.", "data": []}
                return {"message": f"No trending products found for the last {days} days.", "data": []}
            
            # Format the response
            if language == "sw":
                lines = [f"🔥 Bidhaa Zinazovuma (Siku {days} zilizopita)", ""]
            else:
                lines = [f"🔥 Trending Products (Last {days} days)", ""]
            
            for i, item in enumerate(suggestions[:limit], 1):
                item_name_display = item.get("ItemName", "Unknown")
                price = item.get("Price")
                sales_volume = item.get("SalesVolume", 0)
                trend = item.get("Trend", "Popular")
                reason = item.get("Reason", f"{sales_volume} units sold recently")
                
                lines.append(f"{i}. **{item_name_display}**")
                if price:
                    lines.append(f"   💰 Price: KES {price:,.2f}")
                if sales_volume > 0:
                    lines.append(f"   📊 Sales: {sales_volume:,.0f} units")
                lines.append(f"   📈 {trend}")
                lines.append(f"   💡 {reason}")
                lines.append("")
            
            return {
                "message": "\n".join(lines),
                "data": suggestions
            }
            
        except Exception as e:
            logger.error(f"Error in get_trending: {e}", exc_info=True)
            if language == "sw":
                return {"message": "Samahani, nilikumbana na hitilafu wakati wa kupata bidhaa zinazovuma.", "data": []}
            return {"message": "Sorry, I encountered an error while getting trending products.", "data": []}
    
    def find_customers_by_item(self, item_name: str, limit: int, language: str) -> dict:
        """Find customers who buy a specific item."""
        try:
            if not item_name:
                return self._missing("an item name", language)
            
            logger.info(f"Finding customers for item: {item_name}")
            
            # Check cache first
            cache_key = f"customers_for_item:{item_name.lower()}:{limit}"
            cached_result = self.cache.get("FIND_CUSTOMERS_BY_ITEM", {"item_name": item_name, "quantity": limit}, "")
            if cached_result:
                logger.info(f"Cache hit for FIND_CUSTOMERS_BY_ITEM: {item_name}")
                return cached_result
            
            items = self.api.get_items(search=item_name, limit=5)
            if not items:
                return self._smart_not_found_item(item_name, language)
            
            # Find best matching item
            matched_item = None
            for candidate in items:
                candidate_name = candidate.get("ItemName", "").lower()
                if item_name.lower() in candidate_name or candidate_name in item_name.lower():
                    matched_item = candidate
                    break
            
            if not matched_item:
                matched_item = items[0]
            
            item_code = matched_item.get("ItemCode")
            item_full_name = matched_item.get("ItemName")
            
            logger.info(f"Matched item: {item_full_name} ({item_code})")
            
            customers = self.recommender.get_customers_for_item(
                item_code=item_code, 
                limit=limit or 10
            )
            
            if not customers:
                if language == "sw":
                    text = f"Hakuna wateja waliojitokeza kwa '{item_full_name}'\n\nMapendekezo:\n"
                    text += "• Angalia bidhaa kama 'vegimax', 'easeed', au 'maize'\n"
                    text += "• Jaribu neno tofauti la bidhaa\n"
                    text += "• Uliza 'nionyeshe wateja wanaonunua bidhaa kama hizi'"
                else:
                    text = f"No customers found for '{item_full_name}'\n\nSuggestions:\n"
                    text += "• Check similar products like 'vegimax', 'easeed', or 'maize'\n"
                    text += "• Try a different product name\n"
                    text += "• Ask 'show me customers who buy similar products'"
                
                return {"message": text, "data": []}
            
            # Format the response
            if language == "sw":
                lines = [f"📋 Wateja Wanaonunua {item_full_name}", ""]
                lines.append(f"Wateja {len(customers)} waliojitokeza:")
                lines.append("")
            else:
                lines = [f"📋 Customers Who Buy {item_full_name}", ""]
                lines.append(f"Found {len(customers)} customers:")
                lines.append("")
            
            for i, cust in enumerate(customers[:limit], 1):
                cust_name = cust.get("CardName", "Unknown")
                cust_code = cust.get("CardCode", "N/A")
                qty = cust.get("PurchaseQuantity", 0)
                last_purchase = cust.get("LastPurchaseDate", "")
                reason = cust.get("RecommendationReason", "")
                
                lines.append(f"{i}. **{cust_name}**")
                lines.append(f"   📦 Code: {cust_code}")
                if qty > 0:
                    lines.append(f"   📊 Quantity: {qty:,.0f} units")
                if last_purchase:
                    lines.append(f"   📅 Last purchase: {last_purchase[:10]}")
                if reason:
                    lines.append(f"   💡 {reason}")
                lines.append("")
            
            lines.append("💬 Next Steps:")
            lines.append("• Ask 'show customer details' for more information")
            lines.append("• Ask 'create quotation for these customers' to generate quotes")
            lines.append("• Ask 'show orders for these customers' to see purchase history")
            
            result = {"message": "\n".join(lines), "data": customers}
            
            # Cache the result
            self.cache.set("FIND_CUSTOMERS_BY_ITEM", {"item_name": item_name, "quantity": limit}, "", result)
            return result
            
        except Exception as e:
            logger.error(f"Error in find_customers_by_item: {e}", exc_info=True)
            if language == "sw":
                return {"message": "Samahani, nilikumbana na hitilafu wakati wa kutafuta wateja. Tafadhali jaribu tena.", "data": []}
            return {"message": "Sorry, I encountered an error while finding customers. Please try again.", "data": []}
    
    def _smart_not_found_item(self, item_name: str, language: str) -> dict:
        """Not-found with up to 3 closest item matches."""
        try:
            SKIP = {"PACKING MATERIAL", "RAW MATERIAL", "PACKAGING"}
            raw = self.api.get_items(search=item_name, limit=8)
            suggestions = [
                i for i in raw
                if (i.get("item_group") or {}).get("ItmsGrpNam", "").upper() not in SKIP
                and i.get("SellItem") == "Y"
            ][:3]
        except Exception:
            suggestions = []
        
        if suggestions:
            if language == "sw":
                lines = [f"Bidhaa '{item_name}' haijapatikana.\n\nUlimaanisha mojawapo ya hizi?"]
                for s in suggestions:
                    lines.append(f"• {s.get('ItemName')} ({s.get('ItemCode')})")
                lines.append("\nJaribu kutumia jina kamili zaidi.")
            else:
                lines = [f"Item '{item_name}' not found.\n\nDid you mean one of these?"]
                for s in suggestions:
                    lines.append(f"• {s.get('ItemName')} ({s.get('ItemCode')})")
                lines.append("\nTry using a more specific name.")
            return {
                "message": "\n".join(lines),
                "data": [],
                "_suggestions": [s.get("ItemName") for s in suggestions],
            }
        
        if language == "sw":
            return {"message": (
                f"Bidhaa '{item_name}' haijapatikana.\n\nVidokezo:\n"
                f"• Angalia tahajia\n• Jaribu jina fupi\n• Uliza 'nionyeshe bidhaa' kuona orodha kamili"
            ), "data": []}
        return {"message": (
            f"Item '{item_name}' not found.\n\nTips:\n"
            f"• Check spelling (e.g. 'vegimax' not 'vegimx')\n"
            f"• Try a shorter name (e.g. 'cabbage' instead of 'cabbage seeds drumhead')\n"
            f"• Ask 'show me items' to browse the full catalogue"
        ), "data": []}
    
    def _missing(self, what: str, language: str) -> dict:
        """Return a missing parameter message."""
        if language == "sw":
            return {"message": f"Tafadhali taja {what}.", "data": []}
        return {"message": f"Please specify {what}.", "data": []}