from app.services.leysco_api_service import LeyscoAPIService, clean_customer_search_term
from app.services.pricing_service import PricingService
from app.services.warehouse_service import WarehouseService
from app.services.recommendation_service import RecommendationService
from app.services.delivery_tracking_service import DeliveryTrackingService
from app.services.quotation_service import QuotationService
from app.ai_engine import leysco_knowledge_base as kb
from app.ai_engine.response_formatter import ResponseFormatter
from app.ai_engine.training_actions import TrainingActions
from app.ai_engine.decision_support import DecisionSupport
from app.ai_engine.conversation_enhancer import ConversationEnhancer
import logging
import random
import difflib
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class ActionRouter:
    def __init__(self):
        self.api = LeyscoAPIService()
        self.pricing = PricingService()
        self.warehouse = WarehouseService()
        self.recommender = RecommendationService(self.api)
        self.delivery = DeliveryTrackingService(self.api)
        self.quotation = QuotationService(self.api)
        self.training = TrainingActions()
        self.decision_support = DecisionSupport(
            api=self.api,
            pricing=self.pricing,
            warehouse=self.warehouse,
            recommender=self.recommender
        )
        self.conversation = ConversationEnhancer()
        self.formatter = ResponseFormatter()

    # =========================================================
    # 🔧 INTERNAL HELPERS
    # =========================================================

    def _resolve_customer(self, customer_name: str, item_name: str = ""):
        """
        Single authoritative customer lookup with enhanced matching.
        """
        name = customer_name or item_name
        if not name:
            return None, None

        name = name.strip()
        
        # Use the enhanced customer resolution from API service
        customer = self.api.resolve_customer(name)
        if customer:
            return customer, name
            
        # Fallback to original method
        results = self.api.get_customers(search=name)

        if not results:
            return None, name

        # Exact match first
        name_lower = name.lower()
        for c in results:
            if (c.get("CardName") or "").lower() == name_lower:
                return c, name

        # Fuzzy match
        card_names = [c.get("CardName") for c in results if c.get("CardName")]
        matches = difflib.get_close_matches(name, card_names, n=1, cutoff=0.6)
        if matches:
            customer = next((c for c in results if c.get("CardName") == matches[0]), None)
            if customer:
                logger.info(f"Fuzzy matched customer: '{name}' → '{matches[0]}'")
                return customer, name

        return None, name

    def _missing(self, what: str, language: str = "en"):
        """Return missing parameter message in appropriate language"""
        if language == "sw":
            swahili_what = {
                "an item name": "jina la bidhaa",
                "a customer name": "jina la mteja",
                "a warehouse name": "jina la ghala",
                "a delivery number": "namba ya usafirishaji",
                "the item you want details for": "bidhaa unayotaka maelezo yake",
            }.get(what, what)
            return {"message": f"Tafadhali taja {swahili_what}.", "data": []}
        return {"message": f"Please specify {what}.", "data": []}

    def _not_found(self, what: str, value: str, language: str = "en"):
        """Return not found message in appropriate language"""
        if language == "sw":
            swahili_what = {
                "Item": "Bidhaa",
                "Customer": "Mteja",
                "Warehouse": "Ghala",
                "Order": "Oda",
                "Quotation": "Nukuu",
            }.get(what, what)
            return {"message": f"{swahili_what} '{value}' haipatikani.", "data": []}
        return {"message": f"{what} '{value}' not found.", "data": []}

    def _extract_quotation_items(self, message: str, customer: dict) -> tuple:
        """
        Extract items and quantities from quotation request.
        Now returns (items_to_quote, skipped_items) tuple.
        Enhanced pattern matching for better extraction.
        """
        items_to_quote = []
        skipped_items = []
        
        logger.info(f"🔍 Extracting items from: {message}")
        
        # Common patterns in quotation requests
        patterns = [
            # Pattern: "5 vegimax", "3 cabbage seeds"
            r'(\d+)\s+([a-zA-Z0-9\s\-]+?)(?:\s+and|\s+na|\s*,\s*|$)',
            
            # Pattern: "5 units of vegimax"
            r'(\d+)\s+(?:units?|pieces?|vitengo)\s+(?:of|za)?\s+([a-zA-Z0-9\s\-]+?)(?:\s+and|\s+na|\s*,\s*|$)',
            
            # Pattern: "vegimax 5"
            r'([a-zA-Z0-9\s\-]+?)\s+(\d+)(?:\s+and|\s+na|\s*,\s*|$)',
        ]
        
        matches = []
        for pattern in patterns:
            found = re.findall(pattern, message.lower())
            if found:
                matches = found
                logger.info(f"   Pattern matches: {matches}")
                break
        
        # If no matches with patterns, try the original method
        if not matches:
            # Extract part after "with" or ":" or "na"
            item_section = message
            if " with " in message.lower():
                item_section = message.lower().split(" with ", 1)[1]
            elif " na " in message.lower():
                item_section = message.lower().split(" na ", 1)[1]
            elif ":" in message:
                item_section = message.split(":", 1)[1]
            
            pattern = r'(\d+)\s+(?:units?\s+of\s+)?([a-z0-9\s\-]+?)(?:\s+and\s+\d|\s+na\s+\d|\s*,\s*\d|$)'
            matches = re.findall(pattern, item_section.lower())
            logger.info(f"   Fallback pattern matches: {matches}")
        
        # Define item types to skip
        SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL", "PACKAGING"}
        SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK", "PACK", "BAG", "BOX")
        
        for match in matches:
            try:
                # Handle different pattern formats
                if len(match) == 2:
                    if match[0].isdigit():
                        qty = int(match[0])
                        item_search = match[1].strip()
                    else:
                        # Try to see if the second part is a number
                        if match[1].isdigit():
                            qty = int(match[1])
                            item_search = match[0].strip()
                        else:
                            continue
                else:
                    continue
                
                # Clean up item name
                item_search = re.sub(r'\s+(and|na|with|for|units?|pieces?|vitengo)$', '', item_search).strip()
                
                logger.info(f"   Searching for: '{item_search}' (qty: {qty})")
                
                # Search for item in SAP
                items = self.api.get_items(search=item_search, limit=10)
                
                if items:
                    # Take best match (first result)
                    item = items[0]
                    item_code = item.get("ItemCode")
                    item_name = item.get("ItemName")
                    item_group = (item.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                    
                    # Check if item is sellable
                    is_sellable = item.get("SellItem") == "Y"
                    is_packing = item_group in SKIP_GROUPS or any(item_code.startswith(prefix) for prefix in SKIP_PREFIXES)
                    
                    # Skip non-sellable items
                    if not is_sellable or is_packing:
                        skipped_items.append({
                            "name": item_name,
                            "code": item_code,
                            "reason": f"Non-sellable item (Group: {item_group})"
                        })
                        logger.warning(f"   ⚠️ Skipping non-sellable item: {item_code}")
                        continue
                    
                    # Get price for this customer
                    price_result = self.pricing.get_price_for_customer(
                        item_code=item_code,
                        customer=customer
                    )
                    
                    price = price_result.get("price", 0) if price_result.get("found") else 0
                    
                    # Skip items with zero price
                    if price <= 0:
                        skipped_items.append({
                            "name": item_name,
                            "code": item_code,
                            "reason": "No price set for this customer"
                        })
                        logger.warning(f"   ⚠️ Skipping item with zero price: {item_code}")
                        continue
                    
                    items_to_quote.append({
                        "ItemCode": item_code,
                        "ItemName": item_name,
                        "Quantity": qty,
                        "Price": price,
                        "ItemGroup": item_group
                    })
                    
                    logger.info(f"   ✅ Found sellable item: {qty} x {item_name} @ KES {price}")
                else:
                    logger.warning(f"   ❌ No items found for: '{item_search}'")
                    skipped_items.append({
                        "name": item_search,
                        "reason": "Item not found in system"
                    })
            except Exception as e:
                logger.error(f"   ❌ Failed to parse item: {match} - {e}")
                continue
        
        logger.info(f"📦 Total items extracted: {len(items_to_quote)}")
        if skipped_items:
            logger.info(f"⏭️ Skipped {len(skipped_items)} invalid items")
        
        return items_to_quote, skipped_items

    # =========================================================
    # 🎯 ROUTE METHOD
    # =========================================================

    def route(self, intent: str, entities: dict, message: str = "", language: str = "en"):
        """Main routing method."""
        item_name     = (entities.get("item_name") or "").strip()
        customer_name = (entities.get("customer_name") or "").strip()
        quantity      = entities.get("quantity") or 10
        warehouse_name = (entities.get("warehouse") or "").strip()
        
        result = None

        # =========================================================
        # 💬 CONVERSATIONAL INTENTS
        # =========================================================
        if intent == "GREETING":
            if language == "sw":
                greetings = [
                    "Habari! Mimi ni msaidizi wako wa Leysco. Nikusaidie vipi leo?",
                    "Mambo! Ninaweza kukusaidia na:\n• Bei za bidhaa na hisa\n• Taarifa za wateja\n• Maelezo ya maghala\n• Mapendekezo\n\nUngependa kujua nini?",
                    "Sasa! Niko tayari kukusaidia na bidhaa, wateja, au hisa. Unahitaji nini?",
                ]
            else:
                greetings = [
                    "Hello! I'm your Leysco AI assistant. How can I help you today?",
                    "Hi there! I can help you with:\n• Product prices and stock\n• Customer information\n• Warehouse details\n• Recommendations\n\nWhat would you like to know?",
                    "Hey! Ready to assist you with anything related to products, customers, or inventory. What do you need?",
                ]
            result = {"message": random.choice(greetings), "data": []}
        
        elif intent == "THANKS":
            if language == "sw":
                result = {"message": "Karibu! Najulishe kama unahitaji kitu kingine chochote.", "data": []}
            else:
                result = {"message": "You're welcome! Let me know if you need anything else.", "data": []}
        
        elif intent == "SMALL_TALK":
            if language == "sw":
                result = {"message": "Kwaheri! Karibu wakati wowote unapohitaji msaada.", "data": []}
            else:
                result = {"message": "Goodbye! Feel free to come back anytime you need help.", "data": []}
        
        elif intent == "FAQ":
            if language == "sw":
                result = {
                    "message": "Ninaweza kukusaidia na:\n\n"
                              "📦 **Bidhaa**: Angalia bei, hisa, aina\n"
                              "👥 **Wateja**: Tazama maelezo, oda, bei\n"
                              "🏭 **Maghala**: Angalia hisa, maeneo\n"
                              "🎯 **Mapendekezo**: Pendekeza bidhaa au wateja\n"
                              "ℹ️ **Taarifa za Kampuni**: Kuhusu Leysco, mawasiliano\n\n"
                              "Uliza swali lako kwa urahisi!",
                    "data": None
                }
            else:
                result = {
                    "message": "I can help you with:\n\n"
                              "📦 **Products**: Check prices, stock, variants\n"
                              "👥 **Customers**: View details, orders, pricing\n"
                              "🏭 **Warehouses**: Check stock levels, locations\n"
                              "🎯 **Recommendations**: Suggest items or customers\n"
                              "ℹ️ **Company Info**: About Leysco, contact details\n\n"
                              "Just ask your question naturally!",
                    "data": None
                }

        # =========================================================
        # 🎓 TRAINING & ONBOARDING INTENTS
        # =========================================================
        elif intent == "TRAINING_MODULE":
            result = {"message": self.training.handle_training_module(entities, message, language), "data": []}

        elif intent == "TRAINING_VIDEO":
            result = {"message": self.training.handle_training_video(entities, message, language), "data": []}

        elif intent == "TRAINING_GUIDE":
            result = {"message": self.training.handle_training_guide(entities, message, language), "data": []}

        elif intent == "TRAINING_FAQ":
            result = {"message": self.training.handle_training_faq(entities, message, language), "data": []}

        elif intent == "TRAINING_GLOSSARY":
            result = {"message": self.training.handle_training_glossary(entities, message, language), "data": []}

        elif intent == "TRAINING_WEBINAR":
            result = {"message": self.training.handle_training_webinar(entities, message, language), "data": []}

        elif intent == "TRAINING_ONBOARDING":
            result = {"message": self.training.handle_onboarding_welcome(language), "data": []}

        # =========================================================
        # 🧠 DECISION SUPPORT INTENTS
        # =========================================================
        elif intent == "ANALYZE_INVENTORY_HEALTH":
            warehouse = entities.get("warehouse")
            analysis = self.decision_support.analyze_inventory_health(warehouse)
            
            if "error" in analysis:
                result = {"message": analysis["error"], "data": []}
            else:
                summary = analysis["summary"]
                
                if language == "sw":
                    text = f"📊 **Ripoti ya Afya ya Hisa**\n\n"
                    text += f"📍 **Ghala:** {summary['warehouse']}\n"
                    text += f"📦 **Jumla ya Bidhaa:** {summary['total_items']}\n"
                    text += f"💰 **Jumla ya Thamani:** KES {summary['total_inventory_value']:,.2f}\n\n"
                    
                    if analysis["critical_items"]:
                        text += f"⚠️ **HISA MUHIMU - AGIZA MARA MOJA** ({summary['critical_items_count']} bidhaa)\n"
                        for item in analysis["critical_items"][:5]:
                            text += f"• {item['name']}: siku {item['days_left']} zimesalia (Hisa: {item['available']})\n"
                        text += "\n"
                    
                    if analysis["reorder_recommendations"]:
                        text += f"🔄 **Mapendekezo ya Kuagiza Tena** ({summary['reorder_recommendations_count']} bidhaa)\n"
                        for rec in analysis["reorder_recommendations"][:5]:
                            text += f"• {rec['name']}: Agiza {rec['recommended_qty']} vitengo (kipaumbele cha {rec['urgency']})\n"
                        text += "\n"
                    
                    if analysis["overstock_items"]:
                        text += f"📦 **Bidhaa Zaidi ya Hisa** ({summary['overstock_items_count']} bidhaa)\n"
                        for item in analysis["overstock_items"][:5]:
                            text += f"• {item['name']}: hisa ya siku {item['days_left']}\n"
                        text += "\n"
                    
                    if analysis["fast_movers"]:
                        text += f"⚡ **Bidhaa Zinazouza Haraka** ({summary['fast_movers_count']} bidhaa)\n"
                        for item in analysis["fast_movers"][:5]:
                            text += f"• {item['name']}: {item['daily_avg']}/siku, siku {item['days_left']} zimesalia\n"
                        text += "\n"
                    
                    if analysis["slow_movers"]:
                        text += f"🐢 **Bidhaa Zinazokaa Kwa muda** ({summary['slow_movers_count']} bidhaa)\n"
                        for item in analysis["slow_movers"][:5]:
                            text += f"• {item['name']}: {item['on_hand']} vitengo, thamani KES {item['value']:,.0f}\n"
                else:
                    text = f"📊 **Inventory Health Report**\n\n"
                    text += f"📍 **Warehouse:** {summary['warehouse']}\n"
                    text += f"📦 **Total Items:** {summary['total_items']}\n"
                    text += f"💰 **Total Value:** KES {summary['total_inventory_value']:,.2f}\n\n"
                    
                    if analysis["critical_items"]:
                        text += f"⚠️ **CRITICAL STOCK - ORDER IMMEDIATELY** ({summary['critical_items_count']} items)\n"
                        for item in analysis["critical_items"][:5]:
                            text += f"• {item['name']}: {item['days_left']} days left (Stock: {item['available']})\n"
                        text += "\n"
                    
                    if analysis["reorder_recommendations"]:
                        text += f"🔄 **Reorder Recommendations** ({summary['reorder_recommendations_count']} items)\n"
                        for rec in analysis["reorder_recommendations"][:5]:
                            text += f"• {rec['name']}: Order {rec['recommended_qty']} units ({rec['urgency']} priority)\n"
                        text += "\n"
                    
                    if analysis["overstock_items"]:
                        text += f"📦 **Overstock Items** ({summary['overstock_items_count']} items)\n"
                        for item in analysis["overstock_items"][:5]:
                            text += f"• {item['name']}: {item['days_left']} days stock\n"
                        text += "\n"
                    
                    if analysis["fast_movers"]:
                        text += f"⚡ **Fast Movers - Keep Stocked** ({summary['fast_movers_count']} items)\n"
                        for item in analysis["fast_movers"][:5]:
                            text += f"• {item['name']}: {item['daily_avg']}/day, {item['days_left']} days left\n"
                        text += "\n"
                    
                    if analysis["slow_movers"]:
                        text += f"🐢 **Slow Movers - Consider Promotion** ({summary['slow_movers_count']} items)\n"
                        for item in analysis["slow_movers"][:5]:
                            text += f"• {item['name']}: {item['on_hand']} units, value KES {item['value']:,.0f}\n"
                
                result = {"message": text, "data": [analysis]}

        elif intent == "GET_REORDER_DECISIONS":
            item = entities.get("item_name")
            decisions = self.decision_support.get_reorder_decisions(item)
            
            if language == "sw":
                text = "🔄 **Maamuzi ya Kuagiza Tena**\n\n"
                
                if decisions["immediate_orders"]:
                    text += "**⚠️ Maagizo ya Haraka Yanahitajika:**\n"
                    for order in decisions["immediate_orders"][:5]:
                        text += f"• **{order['name']}**\n"
                        text += f"  Hisa: {order['current']} | Wastani wa kila siku: {order['daily_avg']}\n"
                        text += f"  Siku zilizobaki: {order['days_left']} | Kipaumbele: {order['priority']}\n"
                        text += f"  Agiza: {order['recommended_qty']} vitengo (KES {order['estimated_cost']:,.0f})\n\n"
                else:
                    text += "✅ Hakuna maagizo ya haraka yanayohitajika. Hisa ziko sawa.\n"
            else:
                text = "🔄 **Reorder Decisions**\n\n"
                
                if decisions["immediate_orders"]:
                    text += "**⚠️ Immediate Orders Required:**\n"
                    for order in decisions["immediate_orders"][:5]:
                        text += f"• **{order['name']}**\n"
                        text += f"  Current: {order['current']} units | Daily avg: {order['daily_avg']}\n"
                        text += f"  Days left: {order['days_left']} | Priority: {order['priority']}\n"
                        text += f"  Order: {order['recommended_qty']} units (KES {order['estimated_cost']:,.0f})\n\n"
                else:
                    text += "✅ No immediate reorders needed. Stock levels are healthy.\n"
            
            result = {"message": text, "data": [decisions]}

        elif intent == "ANALYZE_PRICING_OPPORTUNITIES":
            customer = entities.get("customer_name")
            opportunities = self.decision_support.analyze_pricing_opportunities(customer)
            
            if language == "sw":
                text = "💰 **Fursa za Bei na Uchambuzi**\n\n"
                
                if opportunities["price_drops"]:
                    text += "📉 **Kushuka kwa Bei - NUNUA SASA!**\n"
                    for opp in opportunities["price_drops"][:5]:
                        text += f"• {opp['name']}: KES {opp['current']:,.0f} ({opp['drop_percent']}% chini ya wastani)\n"
                        text += f"  Hatua: {opp['action']}\n"
                    text += "\n"
                
                if opportunities["price_hikes"]:
                    text += "📈 **Kupanda kwa Bei - Tafuta Njia Mbadala**\n"
                    for opp in opportunities["price_hikes"][:5]:
                        text += f"• {opp['name']}: KES {opp['current']:,.0f} ({opp['hike_percent']}% juu ya wastani)\n"
                        text += f"  Hatua: {opp['action']}\n"
                    text += "\n"
                
                if opportunities["best_value"]:
                    text += "✨ **Bidhaa za Thamani Bora**\n"
                    for opp in opportunities["best_value"][:5]:
                        text += f"• {opp['name']}: KES {opp['price']:,.0f} ({opp['category']})\n"
            else:
                text = "💰 **Pricing Opportunities & Insights**\n\n"
                
                if opportunities["price_drops"]:
                    text += "📉 **Price Drops - BUY NOW!**\n"
                    for opp in opportunities["price_drops"][:5]:
                        text += f"• {opp['name']}: KES {opp['current']:,.0f} ({opp['drop_percent']}% below avg)\n"
                        text += f"  Action: {opp['action']}\n"
                    text += "\n"
                
                if opportunities["price_hikes"]:
                    text += "📈 **Price Hikes - Consider Alternatives**\n"
                    for opp in opportunities["price_hikes"][:5]:
                        text += f"• {opp['name']}: KES {opp['current']:,.0f} ({opp['hike_percent']}% above avg)\n"
                        text += f"  Action: {opp['action']}\n"
                    text += "\n"
                
                if opportunities["best_value"]:
                    text += "✨ **Best Value Items**\n"
                    for opp in opportunities["best_value"][:5]:
                        text += f"• {opp['name']}: KES {opp['price']:,.0f} ({opp['category']})\n"
            
            result = {"message": text, "data": [opportunities]}

        elif intent == "ANALYZE_CUSTOMER_BEHAVIOR":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                analysis = self.decision_support.analyze_customer_behavior(customer_name)
                
                if "error" in analysis:
                    result = {"message": analysis["error"], "data": []}
                else:
                    if language == "sw":
                        text = f"👥 **Uchambuzi wa Mteja: {analysis['customer']['name']}**\n\n"
                        
                        patterns = analysis["purchase_patterns"]
                        if patterns:
                            text += f"📊 **Mifumo ya Ununuzi**\n"
                            text += f"• Jumla ya Oda: {patterns.get('total_orders', 0)}\n"
                            text += f"• Jumla ya Matumizi: KES {patterns.get('total_spent', 0):,.2f}\n"
                            text += f"• Wastani wa Oda: KES {patterns.get('avg_order_value', 0):,.2f}\n"
                            text += f"• Mara kwa mara ya Ununuzi: Kila siku {patterns.get('purchase_frequency_days', 0)}\n"
                            text += f"• Makadirio ya Matumizi ya Kila Mwezi: KES {patterns.get('estimated_monthly_spend', 0):,.2f}\n\n"
                            
                            if patterns.get("top_items"):
                                text += f"**Bidhaa Zinazonunuliwa Zaidi:**\n"
                                for item in patterns["top_items"][:3]:
                                    text += f"• {item['code']}: oda {item['count']}\n"
                                text += "\n"
                        
                        if analysis["recommendations"]:
                            text += "💡 **Mapendekezo**\n"
                            for rec in analysis["recommendations"]:
                                text += f"• {rec}\n"
                            text += "\n"
                        
                        if analysis["upsell_opportunities"]:
                            text += "📈 **Fursa za Kuuza Zaidi**\n"
                            for opp in analysis["upsell_opportunities"]:
                                text += f"• {opp}\n"
                            text += "\n"
                        
                        if analysis["risk_factors"]:
                            text += "⚠️ **Sababu za Hatari**\n"
                            for risk in analysis["risk_factors"]:
                                text += f"• {risk}\n"
                    else:
                        text = f"👥 **Customer Insights: {analysis['customer']['name']}**\n\n"
                        
                        patterns = analysis["purchase_patterns"]
                        if patterns:
                            text += f"📊 **Purchase Patterns**\n"
                            text += f"• Total Orders: {patterns.get('total_orders', 0)}\n"
                            text += f"• Total Spent: KES {patterns.get('total_spent', 0):,.2f}\n"
                            text += f"• Avg Order Value: KES {patterns.get('avg_order_value', 0):,.2f}\n"
                            text += f"• Purchase Frequency: Every {patterns.get('purchase_frequency_days', 0)} days\n"
                            text += f"• Est. Monthly Spend: KES {patterns.get('estimated_monthly_spend', 0):,.2f}\n\n"
                            
                            if patterns.get("top_items"):
                                text += f"**Top Purchased Items:**\n"
                                for item in patterns["top_items"][:3]:
                                    text += f"• {item['code']}: {item['count']} orders\n"
                                text += "\n"
                        
                        if analysis["recommendations"]:
                            text += "💡 **Recommendations**\n"
                            for rec in analysis["recommendations"]:
                                text += f"• {rec}\n"
                            text += "\n"
                        
                        if analysis["upsell_opportunities"]:
                            text += "📈 **Upsell Opportunities**\n"
                            for opp in analysis["upsell_opportunities"]:
                                text += f"• {opp}\n"
                            text += "\n"
                        
                        if analysis["risk_factors"]:
                            text += "⚠️ **Risk Factors**\n"
                            for risk in analysis["risk_factors"]:
                                text += f"• {risk}\n"
                    
                    result = {"message": text, "data": [analysis]}

        elif intent == "FORECAST_DEMAND":
            if not item_name:
                result = self._missing("an item name", language)
            else:
                days = quantity or 30
                forecast = self.decision_support.forecast_demand(item_name, days)
                
                if "error" in forecast:
                    result = {"message": forecast["error"], "data": []}
                else:
                    if language == "sw":
                        text = f"📈 **Utabiri wa Mahitaji: {forecast['item_name']}**\n\n"
                        text += f"📍 **Hisa ya Sasa:** {forecast['current_stock']} vitengo\n"
                        text += f"📊 **Wastani wa Kila Siku:** {forecast['daily_avg']} vitengo\n"
                        text += f"📉 **Tofauti ya Kila Siku:** ±{forecast['daily_std_dev']} vitengo\n\n"
                        
                        text += f"**Utabiri wa siku {days} zijazo:**\n"
                        text += f"• Inatarajiwa: {forecast['forecast_next_30_days']} vitengo\n"
                        text += f"• Kiwango: {forecast['confidence_interval']['low']} - {forecast['confidence_interval']['high']} vitengo\n\n"
                        
                        if "trend" in forecast:
                            text += f"**Mwelekeo:** {forecast['trend']}\n\n"
                        
                        text += f"💡 **Mapendekezo:** {forecast['recommendation']}"
                    else:
                        text = f"📈 **Demand Forecast: {forecast['item_name']}**\n\n"
                        text += f"📍 **Current Stock:** {forecast['current_stock']} units\n"
                        text += f"📊 **Daily Average:** {forecast['daily_avg']} units\n"
                        text += f"📉 **Daily Variation:** ±{forecast['daily_std_dev']} units\n\n"
                        
                        text += f"**Forecast for next {days} days:**\n"
                        text += f"• Expected: {forecast['forecast_next_30_days']} units\n"
                        text += f"• Range: {forecast['confidence_interval']['low']} - {forecast['confidence_interval']['high']} units\n\n"
                        
                        if "trend" in forecast:
                            text += f"**Trend:** {forecast['trend']}\n\n"
                        
                        text += f"💡 **Recommendation:** {forecast['recommendation']}"
                    
                    result = {"message": text, "data": [forecast]}

        # =========================================================
        #  GET ITEMS
        # =========================================================
        elif intent == "GET_ITEMS":
            # Fetch more items from multiple pages
            items = []
            
            # Try to get more items by making multiple requests with pagination
            for page in range(1, 4):  # Try first 3 pages
                try:
                    url = f"{self.api.base_url}/item_masterdata"
                    params = {"page": page, "per_page": 100, "search": item_name}
                    resp = self.api.session.get(url, params=params, timeout=15)
                    if resp.status_code == 200:
                        data = resp.json()
                        page_items = self.api._normalize(data)
                        items.extend(page_items)
                        logger.info(f"📄 Page {page}: fetched {len(page_items)} items")
                        if len(page_items) < 100:  # Last page
                            break
                except Exception as e:
                    logger.error(f"Error fetching page {page}: {e}")
                    break
            
            logger.info(f"📦 Total items fetched: {len(items)}")
            
            if not items:
                if language == "sw":
                    result = {
                        "message": "Hakuna bidhaa zilizopatikana. Jaribu kutafuta bidhaa mahususi kama 'kabeji' au 'vegimax'.",
                        "data": []
                    }
                else:
                    result = {
                        "message": "No items found. Try searching for a specific product like 'cabbage' or 'vegimax'.",
                        "data": []
                    }
            else:
                # Define what to skip - only skip obvious non-product items
                SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL", "PACKAGING"}
                SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK", "PACK", "BAG", "BOX")
                
                # Product groups we want to see
                TARGET_GROUPS = {"FINISHED GOOD", "FINISHED GOODS", "TRADING GOODS", "MERCHANDISE", "PRODUCTS"}
                
                filtered_items = []
                skipped_count = 0
                packing_count = 0
                
                for itm in items:
                    code = itm.get("ItemCode", "")
                    group = (itm.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                    
                    # Check if it's a packing/raw material
                    is_packing = group in SKIP_GROUPS or any(code.startswith(prefix) for prefix in SKIP_PREFIXES)
                    
                    if is_packing:
                        packing_count += 1
                        # Still include some packing items if they have sellable flags
                        if itm.get("SellItem") == "Y" or itm.get("PrchseItem") == "Y":
                            filtered_items.append(itm)
                        else:
                            skipped_count += 1
                    else:
                        # Always include non-packing items
                        filtered_items.append(itm)
                
                logger.info(f"📊 After filtering: {len(filtered_items)} items kept, {skipped_count} skipped, {packing_count} packing materials")
                
                # If we have no items after filtering, show packing materials with warning
                if not filtered_items:
                    if language == "sw":
                        warning = "⚠️ Hakuna bidhaa zilizokamilika zilizopatikana. Inaonyesha vifaa vya kufungashia badala yake.\n\n"
                    else:
                        warning = "⚠️ No finished goods found. Showing packing materials instead.\n\n"
                    items_to_show = items[:quantity]
                else:
                    warning = ""
                    items_to_show = filtered_items[:quantity]
                
                # Build response showing item properties
                if len(items_to_show) < quantity and len(items) > quantity:
                    # We have more items but they were filtered out
                    if language == "sw":
                        text = f"{warning}Imepatikana jumla ya bidhaa {len(items)}, inaonyesha bidhaa {len(items_to_show)} muhimu:\n\n"
                    else:
                        text = f"{warning}Found {len(items)} total items, showing {len(items_to_show)} relevant items:\n\n"
                else:
                    if language == "sw":
                        text = f"{warning}Imepatikana bidhaa {len(items_to_show)}:\n\n"
                    else:
                        text = f"{warning}Found {len(items_to_show)} items:\n\n"
                
                for i, itm in enumerate(items_to_show, 1):
                    name = itm.get('ItemName', 'Unknown')
                    code = itm.get('ItemCode', 'N/A')
                    group = (itm.get("item_group") or {}).get("ItmsGrpNam", "Unknown")
                    
                    # Show item capabilities
                    capabilities = []
                    if itm.get("SellItem") == "Y":
                        capabilities.append("💰 Uza" if language == "sw" else "💰 Sell")
                    if itm.get("PrchseItem") == "Y":
                        capabilities.append("📦 Nunua" if language == "sw" else "📦 Buy")
                    if itm.get("InvntItem") == "Y":
                        capabilities.append("📊 Hisa" if language == "sw" else "📊 Stock")
                    
                    caps_str = f" [{', '.join(capabilities)}]" if capabilities else ""
                    
                    # Show stock if available
                    on_hand = float(itm.get("OnHand", 0))
                    stock_info = f" | Hisa: {on_hand:,.0f}" if on_hand > 0 else ""
                    
                    # Indicate if it's packing material
                    is_packing = group in SKIP_GROUPS or any(code.startswith(prefix) for prefix in SKIP_PREFIXES)
                    packing_tag = " 📦 Kifungashio" if is_packing else ""
                    
                    if language == "sw":
                        text += f"{i}. {name} ({code}){caps_str}{packing_tag}\n"
                        text += f"   Kundi: {group}{stock_info}\n"
                    else:
                        text += f"{i}. {name} ({code}){caps_str}{packing_tag}\n"
                        text += f"   Group: {group}{stock_info}\n"
                
                # If there are more items available
                total_available = len(items)
                if total_available > quantity:
                    if language == "sw":
                        text += f"\n... na bidhaa nyingine {total_available - quantity}. "
                        text += f"Uliza 'nionyeshe bidhaa {total_available}' kuona zote."
                    else:
                        text += f"\n... and {total_available - quantity} more items. "
                        text += f"Ask for 'show me {total_available} items' to see all."
                
                # Show summary of filtered items
                if packing_count > 0:
                    if language == "sw":
                        text += f"\n\n📦 Kumbuka: Bidhaa {packing_count} za vifaa vya kufungashia zimefichwa. "
                        text += "Uliza 'nionyeshe bidhaa zote pamoja na vifungashio' kuziona."
                    else:
                        text += f"\n\n📦 Note: {packing_count} packing/raw material items were hidden. "
                        text += "Ask for 'show me all items including packing' to see them."
                
                result = {"message": text, "data": items_to_show}

        # =========================================================
        #  GET SELLABLE/PURCHASABLE/INVENTORY ITEMS
        # =========================================================
        elif intent in ["GET_SELLABLE_ITEMS", "GET_PURCHASABLE_ITEMS", "GET_INVENTORY_ITEMS"]:
            # Fetch many more items from multiple pages
            all_items = []
            
            # Try to get more items by making multiple requests with pagination
            for page in range(1, 4):  # Try first 3 pages
                try:
                    url = f"{self.api.base_url}/item_masterdata"
                    params = {"page": page, "per_page": 100, "search": item_name}
                    resp = self.api.session.get(url, params=params, timeout=15)
                    if resp.status_code == 200:
                        data = resp.json()
                        page_items = self.api._normalize(data)
                        all_items.extend(page_items)
                        logger.info(f"📄 Page {page}: fetched {len(page_items)} items")
                        if len(page_items) < 100:  # Last page
                            break
                except Exception as e:
                    logger.error(f"Error fetching page {page}: {e}")
                    break
            
            if not all_items:
                if language == "sw":
                    result = {"message": "Hakuna bidhaa zilizopatikana kwenye mfumo.", "data": []}
                else:
                    result = {"message": "No items found in the system.", "data": []}
            else:
                logger.info(f"📦 Fetched {len(all_items)} total items from API")
                
                # Define what to skip - only skip obvious non-product items
                SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL", "PACKAGING"}
                SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK", "PACK", "BAG", "BOX")
                
                # Product groups we want to see
                TARGET_GROUPS = {"FINISHED GOOD", "FINISHED GOODS", "TRADING GOODS", "MERCHANDISE", "PRODUCTS"}
                
                filtered_items = []
                packing_count = 0
                skipped_count = 0
                
                for itm in all_items:
                    code = itm.get("ItemCode", "")
                    group = (itm.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                    
                    # Check if it's a packing/raw material
                    is_packing = group in SKIP_GROUPS or any(code.startswith(prefix) for prefix in SKIP_PREFIXES)
                    
                    # Determine item type based on intent
                    if intent == "GET_SELLABLE_ITEMS":
                        matches_type = itm.get("SellItem") == "Y"
                    elif intent == "GET_PURCHASABLE_ITEMS":
                        matches_type = itm.get("PrchseItem") == "Y"
                    else:  # GET_INVENTORY_ITEMS
                        matches_type = itm.get("InvntItem") == "Y"
                    
                    # Include if:
                    # 1. It matches the type flag, OR
                    # 2. It's in target groups (finished goods), OR
                    # 3. It's packing but has the type flag (some packing might be sellable)
                    if matches_type or group in TARGET_GROUPS or (is_packing and matches_type):
                        filtered_items.append(itm)
                        if is_packing:
                            packing_count += 1
                    else:
                        skipped_count += 1
                
                logger.info(f"📊 After filtering: {len(filtered_items)} items kept, {skipped_count} skipped ({packing_count} packing items included)")
                
                warning = ""
                # If we don't have enough items, try using all items
                if len(filtered_items) < quantity and len(all_items) > 0:
                    items_to_show = all_items[:quantity]
                    filter_type = "sellable" if intent == "GET_SELLABLE_ITEMS" else "purchasable" if intent == "GET_PURCHASABLE_ITEMS" else "inventory"
                    if language == "sw":
                        warning = f"⚠️ Ni bidhaa {len(filtered_items)} tu za aina hii zilizopatikana. Inaonyesha bidhaa zote badala yake.\n\n"
                    else:
                        warning = f"⚠️ Only {len(filtered_items)} specific {filter_type} items found. Showing all items instead.\n\n"
                else:
                    items_to_show = filtered_items[:quantity]
                
                if not items_to_show:
                    filter_type = "sellable" if intent == "GET_SELLABLE_ITEMS" else "purchasable" if intent == "GET_PURCHASABLE_ITEMS" else "inventory"
                    if language == "sw":
                        result = {
                            "message": f"Hakuna bidhaa za aina hii zilizopatikana. Jaribu:\n\n"
                                      f"• Kuuliza bidhaa nyingi zaidi (mfano, 'nionyeshe bidhaa 20')\n"
                                      f"• Kutafuta bidhaa mahususi (mfano, 'nionyeshe kabeji zinazouzwa')\n"
                                      f"• Kuangalia bidhaa zote kwa 'nionyeshe bidhaa'",
                            "data": []
                        }
                    else:
                        result = {
                            "message": f"No {filter_type} items found. Try:\n\n"
                                      f"• Asking for more items (e.g., 'show me 20 items')\n"
                                      f"• Searching for specific products (e.g., 'show sellable cabbage')\n"
                                      f"• Checking all items with 'show me items'",
                            "data": []
                        }
                else:
                    if language == "sw":
                        filter_name_sw = {
                            "GET_SELLABLE_ITEMS": "Zinazouzwa",
                            "GET_PURCHASABLE_ITEMS": "Zinazonunuliwa",
                            "GET_INVENTORY_ITEMS": "Za Hisa",
                        }.get(intent, "Bidhaa")
                        filter_name = filter_name_sw
                    else:
                        filter_name = "Sellable" if intent == "GET_SELLABLE_ITEMS" else "Purchasable" if intent == "GET_PURCHASABLE_ITEMS" else "Inventory"
                    
                    # Count total available in this category
                    total_available = len(filtered_items) if filtered_items else len(all_items)
                    
                    if language == "sw":
                        text = f"{warning}📦 **Bidhaa {filter_name}** (inaonyesha {len(items_to_show)} kati ya {total_available} zilizopatikana):\n\n"
                    else:
                        text = f"{warning}📦 **{filter_name} Items** (showing {len(items_to_show)} of {total_available} found):\n\n"
                    
                    for i, itm in enumerate(items_to_show, 1):
                        name = itm.get('ItemName', 'Unknown')
                        code = itm.get('ItemCode', 'N/A')
                        group = (itm.get("item_group") or {}).get("ItmsGrpNam", "Unknown")
                        
                        # Show item flags
                        flags = []
                        if itm.get("SellItem") == "Y":
                            flags.append("💰 Uza" if language == "sw" else "💰 Sell")
                        if itm.get("PrchseItem") == "Y":
                            flags.append("📦 Nunua" if language == "sw" else "📦 Buy")
                        if itm.get("InvntItem") == "Y":
                            flags.append("📊 Hisa" if language == "sw" else "📊 Inv")
                        flag_str = f" [{', '.join(flags)}]" if flags else ""
                        
                        # Show stock if available
                        on_hand = float(itm.get("OnHand", 0))
                        stock_info = f" | Hisa: {on_hand:,.0f}" if on_hand > 0 else ""
                        
                        # Indicate if it's packing material
                        is_packing = group in SKIP_GROUPS or any(code.startswith(prefix) for prefix in SKIP_PREFIXES)
                        packing_tag = " 📦 Kifungashio" if is_packing else ""
                        
                        if language == "sw":
                            text += f"{i}. {name} ({code}){flag_str}{packing_tag}\n"
                            text += f"   Kundi: {group}{stock_info}\n"
                        else:
                            text += f"{i}. {name} ({code}){flag_str}{packing_tag}\n"
                            text += f"   Group: {group}{stock_info}\n"
                    
                    # If there are more items available
                    if total_available > quantity:
                        if language == "sw":
                            text += f"\n... na bidhaa nyingine {total_available - quantity}. "
                            text += f"Uliza 'nionyeshe bidhaa {total_available}' kuona zote."
                        else:
                            text += f"\n... and {total_available - quantity} more items. "
                            text += f"Ask for 'show me {total_available} items' to see all."
                    
                    result = {"message": text, "data": items_to_show}

        # =========================================================
        # 📊 GET ITEMS ADVANCED
        # =========================================================
        elif intent == "GET_ITEMS_ADVANCED":
            inventory = self.api.get_inventory_report(search=item_name, limit=200)
            if not inventory:
                if language == "sw":
                    result = {"message": "Hakuna rekodi za hisa zilizopatikana.", "data": []}
                else:
                    result = {"message": "No inventory records found.", "data": []}
            else:
                warehouses = self.api.get_warehouses()
                wh_map = {wh.get("WhsCode"): wh.get("WhsName", wh.get("WhsCode")) for wh in warehouses}

                items_map = {}
                for row in inventory:
                    code = row.get("ItemCode")
                    name = row.get("ItemName")
                    wh_code = row.get("WhsCode")
                    wh = wh_map.get(wh_code, wh_code or "Unknown Warehouse")
                    qty = float(row.get("CurrentOnHand") or 0)

                    if warehouse_name and warehouse_name.lower() not in wh.lower():
                        continue

                    if code not in items_map:
                        items_map[code] = {"ItemCode": code, "ItemName": name, "TotalStock": 0, "warehouses": []}

                    items_map[code]["TotalStock"] += qty
                    items_map[code]["warehouses"].append(f"{wh} ({qty:,.0f})")

                items = list(items_map.values())[:quantity]
                if not items:
                    if warehouse_name:
                        if language == "sw":
                            result = {"message": f"Hakuna bidhaa zilizopatikana katika {warehouse_name}.", "data": []}
                        else:
                            result = {"message": f"No items found in {warehouse_name}.", "data": []}
                    else:
                        if language == "sw":
                            result = {"message": f"Hakuna bidhaa zinazolingana na '{item_name}' zilizopatikana katika ghala lolote.", "data": []}
                        else:
                            result = {"message": f"No items matching '{item_name}' found in any warehouse.", "data": []}
                else:
                    if warehouse_name:
                        if language == "sw":
                            text = f"📊 Hisa katika {warehouse_name.title()} (bidhaa {len(items)}):\n"
                        else:
                            text = f"📊 Stock in {warehouse_name.title()} ({len(items)} items):\n"
                    elif item_name:
                        if language == "sw":
                            text = f"📊 Maeneo ya Ghala kwa '{item_name}' (aina {len(items)}):\n"
                        else:
                            text = f"📊 Warehouse Locations for '{item_name}' ({len(items)} variants):\n"
                    else:
                        if language == "sw":
                            text = f"📊 Bidhaa za Hisa (zilizopatikana {len(items)}):\n"
                        else:
                            text = f"📊 Inventory Items ({len(items)} found):\n"
                    
                    for i, itm in enumerate(items, 1):
                        if language == "sw":
                            text += (
                                f"{i}. {itm['ItemName']} (Msimbo: {itm['ItemCode']})\n"
                                f"   Jumla ya Hisa: {itm['TotalStock']:,.0f} | Maghala: {', '.join(itm['warehouses'])}\n"
                            )
                        else:
                            text += (
                                f"{i}. {itm['ItemName']} (Code: {itm['ItemCode']})\n"
                                f"   Total Stock: {itm['TotalStock']:,.0f} | Warehouses: {', '.join(itm['warehouses'])}\n"
                            )
                    result = {"message": text, "data": items}

        # =========================================================
        #  GET ITEM DETAILS
        # =========================================================
        elif intent == "GET_ITEM_DETAILS":
            if not item_name:
                result = self._missing("the item you want details for", language)
            else:
                item = self.api.get_item_by_name(item_name)
                if not item:
                    result = self._not_found("Item", item_name, language)
                else:
                    on_hand   = float(item.get("OnHand", 0))
                    committed = float(item.get("IsCommited", 0))
                    available = on_hand - committed

                    if language == "sw":
                        text = (
                            f"📋 **Maelezo ya Bidhaa**\n\n"
                            f"**Jina:** {item.get('ItemName')}\n"
                            f"**Msimbo:** {item.get('ItemCode')}\n"
                            f"**Kundi:** {item.get('item_group', {}).get('ItmsGrpNam', 'N/A')}\n"
                            f"**Hisa:** {on_hand:,.0f}\n"
                            f"**Iliyoahidiwa:** {committed:,.0f}\n"
                            f"**Inayopatikana:** {available:,.0f}\n"
                        )
                    else:
                        text = (
                            f"📋 **Item Details**\n\n"
                            f"**Name:** {item.get('ItemName')}\n"
                            f"**Code:** {item.get('ItemCode')}\n"
                            f"**Group:** {item.get('item_group', {}).get('ItmsGrpNam', 'N/A')}\n"
                            f"**On Hand:** {on_hand:,.0f}\n"
                            f"**Committed:** {committed:,.0f}\n"
                            f"**Available:** {available:,.0f}\n"
                        )

                    result = {"message": text, "data": [item]}

        # =========================================================
        #  PRICING
        # =========================================================
        elif intent == "GET_CUSTOMER_PRICE":
            if not item_name:
                result = self._missing("an item name", language)
            elif not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name, item_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    items = self.api.get_items(search=item_name, limit=20)
                    if not items:
                        result = self._not_found("Item", item_name, language)
                    else:
                        results = []
                        if language == "sw":
                            text_lines = [f"💰 **{customer.get('CardName')} - Bei**\n"]
                        else:
                            text_lines = [f"💰 **{customer.get('CardName')} - Pricing**\n"]

                        for itm in items:
                            price_result = self.pricing.get_price_for_customer(
                                item_code=itm.get("ItemCode"),
                                customer=customer
                            )

                            if price_result["found"]:
                                gross_tag = " (incl. VAT)" if price_result["is_gross_price"] else " (excl. VAT)"
                                uom_tag = f" per UOM-{price_result['uom_entry']}" if price_result["uom_entry"] else " per EA"
                                text_lines.append(
                                    f"• **{itm.get('ItemName')}** ({itm.get('ItemCode')}): "
                                    f"KES {price_result['price']:,.2f}{gross_tag}{uom_tag}"
                                )
                                results.append(price_result)

                        if not results:
                            if language == "sw":
                                text_lines.append("Hakuna bei zilizopatikana kwa bidhaa hizi.")
                            else:
                                text_lines.append("No prices available for these items.")

                        result = {"message": "\n".join(text_lines), "data": results}

        elif intent == "GET_ITEM_PRICE":
            if not item_name:
                result = self._missing("an item name", language)
            else:
                items = self.api.get_items(search=item_name, limit=50)
                if not items:
                    if language == "sw":
                        result = {"message": f"Hakuna bidhaa iliyopatikana inayolingana na '{item_name}'.", "data": []}
                    else:
                        result = {"message": f"No items found matching '{item_name}'.", "data": []}
                else:
                    results = []
                    if language == "sw":
                        text_lines = [f"💰 **Bei za '{item_name}'**\n"]
                    else:
                        text_lines = [f"💰 **Prices for '{item_name}'**\n"]

                    # Only skip obvious internal materials
                    SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL"}
                    SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK")
                    
                    priced_items = []
                    skipped_items = []
                    
                    for itm in items:
                        group = (itm.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                        code  = (itm.get("ItemCode") or "").upper()
                        
                        # Skip only internal materials
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
                                text += "\n💡 Kidokezo: Jaribu kutafuta bidhaa zilizokamilika kama 'kabeji', 'vegimax', au 'nyanya'."
                            else:
                                text += "\n💡 Tip: Try searching for finished products like 'cabbage', 'vegimax', or 'tomato'."
                            result = {"message": text, "data": []}
                        else:
                            if language == "sw":
                                result = {"message": f"Hakuna bidhaa iliyopatikana inayolingana na '{item_name}'.", "data": []}
                            else:
                                result = {"message": f"No items found matching '{item_name}'.", "data": []}
                    else:
                        for itm in priced_items:
                            item_code      = itm.get("ItemCode")
                            item_name_full = itm.get("ItemName")
                            
                            # Check item properties
                            is_sellable = itm.get("SellItem") == "Y"
                            is_purchasable = itm.get("PrchseItem") == "Y"
                            is_inventory = itm.get("InvntItem") == "Y"

                            price_result = self.pricing.get_price(item_code=item_code)
                            if not price_result["found"]:
                                price_result = self.pricing.get_price_any_list(item_code=item_code)

                            # Build item type indicator
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
                                uom_tag   = f" per UOM-{price_result['uom_entry']}" if price_result["uom_entry"] else ""
                                text_lines.append(
                                    f"• **{item_name_full}** ({item_code}){type_str}\n"
                                    f"  KES {price_result['price']:,.2f}{gross_tag}{uom_tag} [{price_result['price_list_name']}]"
                                )
                            else:
                                text_lines.append(
                                    f"• **{item_name_full}** ({item_code}){type_str}\n"
                                    f"  No price set"
                                )

                            results.append({
                                "ItemCode":      item_code,
                                "ItemName":      item_name_full,
                                "Price":         price_result["price"],
                                "Currency":      "KES",
                                "PriceListName": price_result["price_list_name"],
                                "IsGrossPrice":  price_result["is_gross_price"],
                                "UomEntry":      price_result["uom_entry"],
                                "Found":         price_result["found"],
                                "Note":          price_result["note"],
                                "IsSellable":    is_sellable,
                                "IsPurchasable": is_purchasable,
                                "IsInventory":   is_inventory,
                            })

                        # Build final message
                        final_message = "\n".join(text_lines)
                        
                        # Ensure message is not empty
                        if not final_message or (language == "sw" and final_message == f"💰 **Bei za '{item_name}'**\n") or (language != "sw" and final_message == f"💰 **Prices for '{item_name}'**\n"):
                            if language == "sw":
                                final_message = f"Imepatikana bidhaa {len(results)} zinazolingana na '{item_name}' zenye bei."
                            else:
                                final_message = f"Found {len(results)} items matching '{item_name}' with pricing information."
                        
                        logger.info(f"📤 GET_ITEM_PRICE returning message length: {len(final_message)} chars, {len(results)} items")
                        
                        result = {"message": final_message, "data": results}

        # =========================================================
        # 📞 CUSTOMERS
        # =========================================================
        elif intent == "GET_CUSTOMERS":
            try:
                customers = self.api.get_customers(search=customer_name, limit=quantity)
                
                if not customers:
                    if language == "sw":
                        result = {"message": "Hakuna wateja waliopatikana.", "data": []}
                    else:
                        result = {"message": "No customers found.", "data": []}
                else:
                    if language == "sw":
                        text = f"👥 **Wateja {len(customers)} waliopatikana:**\n\n"
                    else:
                        text = f"👥 **Found {len(customers)} customers:**\n\n"
                    for i, c in enumerate(customers, 1):
                        text += f"{i}. **{c.get('CardName')}** (Code: {c.get('CardCode')})\n"

                    result = {"message": text, "data": customers}
                    
            except Exception as e:
                logger.error(f"Error in GET_CUSTOMERS: {e}")
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    if language == "sw":
                        result = {
                            "message": "Hifadhidata ya wateja inachukua muda mrefu kujibu. Jaribu:\n\n"
                                      "• Kutafuta mteja mahususi (mfano, 'nionyeshe mteja Magomano')\n"
                                      "• Kuuliza matokeo machache (mfano, 'nionyeshe wateja 3')\n"
                                      "• Kujaribu tena baadaye",
                            "data": []
                        }
                    else:
                        result = {
                            "message": "The customer database is taking too long to respond. Try:\n\n"
                                      "• Searching for a specific customer (e.g., 'show customer Magomano')\n"
                                      "• Asking for fewer results (e.g., 'show me 3 customers')\n"
                                      "• Trying again in a moment",
                            "data": []
                        }
                else:
                    if language == "sw":
                        result = {
                            "message": f"Hitilafu wakati wa kupata wateja: {str(e)}\n\nTafadhali jaribu tena.",
                            "data": []
                        }
                    else:
                        result = {
                            "message": f"Error fetching customers: {str(e)}\n\nPlease try again.",
                            "data": []
                        }

        elif intent == "GET_CUSTOMER_DETAILS":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    # Safely handle nested objects that might be None
                    territory = customer.get("territory") or {}
                    octg = customer.get("octg") or {}

                    # Safely get values with fallbacks
                    territory_desc = "N/A"
                    if territory and isinstance(territory, dict):
                        territory_desc = territory.get("descript", "N/A")
                    
                    payment_terms = "N/A"
                    credit_limit = 0
                    if octg and isinstance(octg, dict):
                        payment_terms = octg.get("PymntGroup", "N/A")
                        credit_limit = float(octg.get("CredLimit", 0))

                    if language == "sw":
                        text = (
                            f"👤 **Maelezo ya Mteja**\n\n"
                            f"**Jina:** {customer.get('CardName', 'N/A')}\n"
                            f"**Msimbo:** {customer.get('CardCode', 'N/A')}\n"
                            f"**Eneo:** {territory_desc}\n"
                            f"**Masharti ya Malipo:** {payment_terms}\n"
                            f"**Kikomo cha Mkopo:** KES {credit_limit:,.2f}\n"
                            f"**Simu:** {customer.get('Phone1', 'N/A')}\n"
                            f"**Anwani:** {customer.get('Address', 'N/A')}\n"
                        )
                    else:
                        text = (
                            f"👤 **Customer Details**\n\n"
                            f"**Name:** {customer.get('CardName', 'N/A')}\n"
                            f"**Code:** {customer.get('CardCode', 'N/A')}\n"
                            f"**Territory:** {territory_desc}\n"
                            f"**Payment Terms:** {payment_terms}\n"
                            f"**Credit Limit:** KES {credit_limit:,.2f}\n"
                            f"**Phone:** {customer.get('Phone1', 'N/A')}\n"
                            f"**Address:** {customer.get('Address', 'N/A')}\n"
                        )

                    # Add group info if available
                    group_code = customer.get("GroupCode")
                    if group_code:
                        text += f"**Group Code:** {group_code}\n"

                    result = {"message": text, "data": [customer]}

        # =========================================================
        #  WAREHOUSES
        # =========================================================
        elif intent == "GET_WAREHOUSES":
            warehouse_name = (entities.get("warehouse") or "").strip()
            
            if warehouse_name:
                warehouses = self.warehouse.search_warehouses(query=warehouse_name, active_only=True)
                if not warehouses:
                    if language == "sw":
                        result = {"message": f"Hakuna ghala lililopatikana linalolingana na '{warehouse_name}'.", "data": []}
                    else:
                        result = {"message": f"No warehouses found matching '{warehouse_name}'.", "data": []}
                elif len(warehouses) == 1:
                    wh = warehouses[0]
                    whscode = wh.get("WhsCode")
                    stock_summary = self.warehouse.get_warehouse_stock_summary(whscode)
                    
                    if language == "sw":
                        text = f"🏭 **{wh.get('WhsName')}** ({whscode})\n"
                        text += f"   **Hali:** {'Inatumika' if wh.get('Inactive') != 'Y' else 'Haitumiki'}\n"
                        text += f"   **Aina:** {wh.get('U_WHS_TYPE', 'N/A')}\n"
                        if wh.get("City"):
                            text += f"   **Mahali:** {wh.get('City')}, {wh.get('Country', 'Kenya')}\n"
                        text += f"\n📊 **Muhtasari wa Hisa:**\n"
                        text += f"   **Jumla ya Bidhaa:** {stock_summary.get('total_items', 0):,}\n"
                        text += f"   **Jumla ya Vitengo:** {stock_summary.get('total_units', 0):,}\n"
                        text += f"   **Iliyoahidiwa:** {stock_summary.get('total_committed', 0):,}\n"
                        text += f"   **Inayopatikana:** {stock_summary.get('total_available', 0):,}\n"
                    else:
                        text = f"🏭 **{wh.get('WhsName')}** ({whscode})\n"
                        text += f"   **Status:** {'Active' if wh.get('Inactive') != 'Y' else 'Inactive'}\n"
                        text += f"   **Type:** {wh.get('U_WHS_TYPE', 'N/A')}\n"
                        if wh.get("City"):
                            text += f"   **Location:** {wh.get('City')}, {wh.get('Country', 'Kenya')}\n"
                        text += f"\n📊 **Stock Summary:**\n"
                        text += f"   **Total Items:** {stock_summary.get('total_items', 0):,}\n"
                        text += f"   **Total Units:** {stock_summary.get('total_units', 0):,}\n"
                        text += f"   **Committed:** {stock_summary.get('total_committed', 0):,}\n"
                        text += f"   **Available:** {stock_summary.get('total_available', 0):,}\n"
                    
                    top_items = stock_summary.get("top_items", [])[:5]
                    if top_items:
                        if language == "sw":
                            text += f"\n🔝 **Bidhaa Bora:**\n"
                        else:
                            text += f"\n🔝 **Top Items:**\n"
                        for itm in top_items:
                            text += f"   • {itm['ItemName']} ({itm['ItemCode']}): {itm['OnHand']:,} units\n"
                    
                    result = {"message": text, "data": [stock_summary]}
            else:
                summaries = self.warehouse.get_all_warehouses_summary()
                active_summaries = [s for s in summaries if s["details"].get("Inactive") != "Y"]
                
                if not active_summaries:
                    if language == "sw":
                        result = {"message": "Hakuna maghala yanayotumika yaliyopatikana.", "data": []}
                    else:
                        result = {"message": "No active warehouses found.", "data": []}
                else:
                    if language == "sw":
                        text = f"🏭 **Maghala {len(active_summaries)} yanayotumika yaliyopatikana:**\n\n"
                    else:
                        text = f"🏭 **Found {len(active_summaries)} active warehouses:**\n\n"
                    for s in active_summaries[:15]:
                        text += f"**{s['WhsName']}** ({s['WhsCode']})\n"
                        text += f"   Items: {s['total_items']:,} | Units: {s['total_units']:,} | Available: {s['total_available']:,}\n"
                    
                    if len(active_summaries) > 15:
                        if language == "sw":
                            text += f"\n... na maghala mengine {len(active_summaries) - 15}"
                        else:
                            text += f"\n... and {len(active_summaries) - 15} more warehouses"
                    
                    result = {"message": text, "data": active_summaries}

        elif intent == "GET_WAREHOUSE_STOCK":
            warehouse_name = (entities.get("warehouse") or "").strip()
            
            if not warehouse_name:
                if language == "sw":
                    result = {"message": "Tafadhali taja jina la ghala au msimbo.", "data": []}
                else:
                    result = {"message": "Please specify a warehouse name or code.", "data": []}
            else:
                warehouses = self.warehouse.search_warehouses(query=warehouse_name)
                if not warehouses:
                    if language == "sw":
                        result = {"message": f"Ghala '{warehouse_name}' halijapatikana.", "data": []}
                    else:
                        result = {"message": f"Warehouse '{warehouse_name}' not found.", "data": []}
                else:
                    wh = warehouses[0]
                    whscode = wh.get("WhsCode")
                    stock_summary = self.warehouse.get_warehouse_stock_summary(whscode)
                    
                    if "error" in stock_summary:
                        result = {"message": stock_summary["error"], "data": []}
                    else:
                        if language == "sw":
                            text = f"📊 **Ripoti ya Hisa: {wh.get('WhsName')}** ({whscode})\n\n"
                            text += f"**Jumla ya Bidhaa:** {stock_summary['total_items']:,}\n"
                            text += f"**Jumla ya Vitengo:** {stock_summary['total_units']:,}\n"
                            text += f"**Iliyoahidiwa:** {stock_summary['total_committed']:,}\n"
                            text += f"**Inayopatikana:** {stock_summary['total_available']:,}\n\n"
                        else:
                            text = f"📊 **Stock Report: {wh.get('WhsName')}** ({whscode})\n\n"
                            text += f"**Total Items:** {stock_summary['total_items']:,}\n"
                            text += f"**Total Units:** {stock_summary['total_units']:,}\n"
                            text += f"**Committed:** {stock_summary['total_committed']:,}\n"
                            text += f"**Available:** {stock_summary['total_available']:,}\n\n"
                        
                        top_items = stock_summary.get("top_items", [])[:10]
                        if top_items:
                            if language == "sw":
                                text += "🔝 **Bidhaa 10 Bora kwa Wingi:**\n"
                            else:
                                text += "🔝 **Top 10 Items by Quantity:**\n"
                            for i, itm in enumerate(top_items, 1):
                                if language == "sw":
                                    text += f"{i}. **{itm['ItemName']}** ({itm['ItemCode']})\n"
                                    text += f"   Hisa: {itm['OnHand']:,} | Iliyoahidiwa: {itm['Committed']:,} | Inayopatikana: {itm['Available']:,}\n"
                                else:
                                    text += f"{i}. **{itm['ItemName']}** ({itm['ItemCode']})\n"
                                    text += f"   On Hand: {itm['OnHand']:,} | Committed: {itm['Committed']:,} | Available: {itm['Available']:,}\n"
                        
                        result = {"message": text, "data": [stock_summary]}

        # =========================================================
        # ✅ FIXED: GET_LOW_STOCK_ALERTS with alerts initialization
        # =========================================================
        elif intent == "GET_LOW_STOCK_ALERTS":
            warehouse_name = (entities.get("warehouse") or "").strip()
            alerts = []  # FIX: Initialize alerts to empty list
            title = ""  # Initialize title
            
            if warehouse_name:
                warehouses = self.warehouse.search_warehouses(query=warehouse_name)
                if not warehouses:
                    if language == "sw":
                        result = {"message": f"Ghala '{warehouse_name}' halijapatikana.", "data": []}
                    else:
                        result = {"message": f"Warehouse '{warehouse_name}' not found.", "data": []}
                else:
                    whscode = warehouses[0].get("WhsCode")
                    alerts = self.warehouse.get_low_stock_alerts(whscode=whscode)
                    if language == "sw":
                        title = f"⚠️ Arifa za Hisa Chache: {warehouses[0].get('WhsName')}"
                    else:
                        title = f"⚠️ Low Stock Alerts: {warehouses[0].get('WhsName')}"
            else:
                alerts = self.warehouse.get_low_stock_alerts()
                if language == "sw":
                    title = "⚠️ Arifa za Hisa Chache (Maghala Yote)"
                else:
                    title = "⚠️ Low Stock Alerts (All Warehouses)"
            
            # Now alerts is guaranteed to be defined (empty list if no alerts)
            if not alerts:
                if language == "sw":
                    result = {"message": "Hakuna arifa za hisa chache kwa sasa.", "data": []}
                else:
                    result = {"message": "No low stock alerts at this time.", "data": []}
            else:
                critical = [a for a in alerts if a["Severity"] == "CRITICAL"]
                low = [a for a in alerts if a["Severity"] == "LOW"]
                
                text = f"{title}\n\n"
                
                if critical:
                    if language == "sw":
                        text += f"🔴 **MUHIMU SANA** (bidhaa {len(critical)}):\n"
                    else:
                        text += f"🔴 **CRITICAL** ({len(critical)} items):\n"
                    for a in critical[:10]:
                        if language == "sw":
                            text += f"• {a['ItemName']} ({a['ItemCode']}) @ {a['WhsCode']}\n"
                            text += f"  Inayopatikana: {a['Available']:,} (Kiwango: {a['Threshold']:,})\n"
                        else:
                            text += f"• {a['ItemName']} ({a['ItemCode']}) @ {a['WhsCode']}\n"
                            text += f"  Available: {a['Available']:,} (Threshold: {a['Threshold']:,})\n"
                
                if low:
                    if language == "sw":
                        text += f"\n🟡 **CHACHE** (bidhaa {len(low)}):\n"
                    else:
                        text += f"\n🟡 **LOW** ({len(low)} items):\n"
                    for a in low[:10]:
                        if language == "sw":
                            text += f"• {a['ItemName']} ({a['ItemCode']}) @ {a['WhsCode']}\n"
                            text += f"  Inayopatikana: {a['Available']:,} (Kiwango: {a['Threshold']:,})\n"
                        else:
                            text += f"• {a['ItemName']} ({a['ItemCode']}) @ {a['WhsCode']}\n"
                            text += f"  Available: {a['Available']:,} (Threshold: {a['Threshold']:,})\n"
                
                if len(alerts) > 20:
                    if language == "sw":
                        text += f"\n... na arifa nyingine {len(alerts) - 20}"
                    else:
                        text += f"\n... and {len(alerts) - 20} more alerts"
                
                result = {"message": text, "data": alerts}

        # =========================================================
        # 📋 ORDERS, INVOICES, QUOTATIONS - ENHANCED VERSION
        # =========================================================
        elif intent == "GET_CUSTOMER_ORDERS":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    # Get orders from API using enhanced method
                    orders = self.api.get_customer_orders(
                        customer_name=customer.get("CardName"),
                        limit=quantity if quantity else 10,
                        doc_status="open"
                    )
                    
                    if not orders:
                        if language == "sw":
                            result = {
                                "message": f"📋 **Hakuna oda kwa {customer.get('CardName')}**\n\n"
                                          f"💡 **Unaweza:**\n"
                                          f"• Unda oda mpya: 'unda oda kwa {customer_name} na 5 vegimax'\n"
                                          f"• Angalia nukuu: 'onyesha nukuu za {customer_name}'\n"
                                          f"• Angalia historia ya mauzo: 'historia ya {customer_name}'\n\n"
                                          f"Unahitaji msaada wa kuunda oda? Niulize tu!",
                                "data": []
                            }
                        else:
                            result = {
                                "message": f"📋 **No orders found for {customer.get('CardName')}**\n\n"
                                          f"💡 **You can:**\n"
                                          f"• Create a new order: 'create order for {customer_name} with 5 vegimax'\n"
                                          f"• Check quotations: 'show quotations for {customer_name}'\n"
                                          f"• View sales history: 'history for {customer_name}'\n\n"
                                          f"Need help creating an order? Just ask!",
                                "data": []
                            }
                    else:
                        if language == "sw":
                            text = f"📋 **Oda za {customer.get('CardName')}**\n\n"
                            text += f"Jumla ya oda: {len(orders)}\n\n"
                        else:
                            text = f"📋 **Orders for {customer.get('CardName')}**\n\n"
                            text += f"Total orders: {len(orders)}\n\n"
                        
                        for i, order in enumerate(orders, 1):
                            doc_num = order.get('DocNum') or 'N/A'
                            doc_total = float(order.get('DocTotal') or 0)
                            doc_date = order.get('DocDate') or ''
                            doc_status = order.get('StatusText') or order.get('DocStatus') or ''
                            
                            date_str = f" ({doc_date[:10]})" if doc_date else ""
                            status_icon = "🟢" if "Open" in str(doc_status) else "🔴" if "Closed" in str(doc_status) else ""
                            
                            if language == "sw":
                                text += f"{i}. **Oda {doc_num}**{date_str} {status_icon}\n"
                                text += f"   Kiasi: KES {doc_total:,.2f}\n\n"
                            else:
                                text += f"{i}. **Order {doc_num}**{date_str} {status_icon}\n"
                                text += f"   Amount: KES {doc_total:,.2f}\n\n"
                        
                        # Add helpful tips
                        if language == "sw":
                            text += f"💡 **Kidokezo:** Unaweza pia kuuliza:\n"
                            text += f"• 'Oda zilizofungwa za {customer_name}'\n"
                            text += f"• 'Oda zote za {customer_name}'\n"
                            text += f"• 'Nukuu za {customer_name}'"
                        else:
                            text += f"💡 **Tip:** You can also ask:\n"
                            text += f"• 'Closed orders for {customer_name}'\n"
                            text += f"• 'All orders for {customer_name}'\n"
                            text += f"• 'Quotations for {customer_name}'"
                        
                        result = {"message": text, "data": orders}

        elif intent in ["GET_CUSTOMER_INVOICES", "GET_OUTSTANDING_INVOICES"]:
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    # Use fetch_marketing_docs with doc_type=13 for invoices
                    invoices = self.api.fetch_marketing_docs(
                        card_code=customer.get("CardCode"),
                        doc_type=13  # 13 = Invoices
                    )
                    
                    if not invoices:
                        if language == "sw":
                            result = {"message": f"Hakuna ankra zilizopatikana kwa {customer.get('CardName')}.", "data": []}
                        else:
                            result = {"message": f"No invoices found for {customer.get('CardName')}.", "data": []}
                    else:
                        if language == "sw":
                            text = f"🧾 **Ankra za {customer.get('CardName')}**\n\n"
                            text += f"Jumla ya ankra: {len(invoices)}\n\n"
                        else:
                            text = f"🧾 **Invoices for {customer.get('CardName')}**\n\n"
                            text += f"Total invoices: {len(invoices)}\n\n"
                        
                        for i, inv in enumerate(invoices[:quantity] if quantity else invoices, 1):
                            doc_num = inv.get('DocNum') or inv.get('doc_num', 'N/A')
                            doc_total = float(inv.get('DocTotal') or inv.get('doc_total', 0))
                            doc_date = inv.get('DocDate') or inv.get('doc_date', '')
                            date_str = f" ({doc_date[:10]})" if doc_date else ""
                            
                            if language == "sw":
                                text += f"{i}. **Ankra {doc_num}**{date_str} - KES {doc_total:,.2f}\n"
                            else:
                                text += f"{i}. **Invoice {doc_num}**{date_str} - KES {doc_total:,.2f}\n"
                        
                        result = {"message": text, "data": invoices}

        elif intent == "GET_QUOTATIONS":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    # Get quotations from API using enhanced method
                    quotes = self.api.get_customer_quotations(
                        customer_name=customer.get("CardName"),
                        limit=quantity if quantity else 10
                    )
                    
                    if not quotes:
                        if language == "sw":
                            result = {
                                "message": f"📋 **Hakuna nukuu kwa {customer.get('CardName')}**\n\n"
                                          f"💡 **Unaweza:**\n"
                                          f"• Unda nukuu mpya: 'unda nukuu kwa {customer_name} na 5 vegimax'\n"
                                          f"• Angalia oda za mteja: 'onyesha oda za {customer_name}'\n"
                                          f"• Angalia historia ya mauzo: 'historia ya {customer_name}'\n\n"
                                          f"Unahitaji msaada wa kuunda nukuu? Niulize tu!",
                                "data": []
                            }
                        else:
                            result = {
                                "message": f"📋 **No quotations found for {customer.get('CardName')}**\n\n"
                                          f"💡 **You can:**\n"
                                          f"• Create a new quotation: 'create quotation for {customer_name} with 5 vegimax'\n"
                                          f"• Check customer orders: 'show orders for {customer_name}'\n"
                                          f"• View sales history: 'history for {customer_name}'\n\n"
                                          f"Need help creating a quotation? Just ask!",
                                "data": []
                            }
                    else:
                        if language == "sw":
                            text = f"💼 **Nukuu za {customer.get('CardName')}**\n\n"
                            text += f"Jumla ya nukuu: {len(quotes)}\n\n"
                        else:
                            text = f"💼 **Quotations for {customer.get('CardName')}**\n\n"
                            text += f"Total quotations: {len(quotes)}\n\n"
                        
                        for i, q in enumerate(quotes, 1):
                            doc_num = q.get('DocNum') or 'N/A'
                            doc_total = float(q.get('DocTotal') or 0)
                            doc_date = q.get('DocDate') or ''
                            valid_until = q.get('DocDueDate') or ''
                            
                            date_str = f" ({doc_date[:10]})" if doc_date else ""
                            valid_str = f" (valid until {valid_until[:10]})" if valid_until else ""
                            
                            if language == "sw":
                                text += f"{i}. **Nukuu {doc_num}**{date_str}\n"
                                text += f"   Kiasi: KES {doc_total:,.2f}{valid_str}\n\n"
                            else:
                                text += f"{i}. **Quote {doc_num}**{date_str}\n"
                                text += f"   Amount: KES {doc_total:,.2f}{valid_str}\n\n"
                        
                        # Add helpful tips
                        if language == "sw":
                            text += f"💡 **Kidokezo:** Kutengeneza nukuu mpya, uliza:\n"
                            text += f"• 'Unda nukuu kwa {customer_name} na 5 vegimax'"
                        else:
                            text += f"💡 **Tip:** To create a new quotation, ask:\n"
                            text += f"• 'Create quotation for {customer_name} with 5 vegimax'"
                        
                        result = {"message": text, "data": quotes}

        # =========================================================
        # 📝 CREATE QUOTATION (UPDATED)
        # =========================================================
        elif intent == "CREATE_QUOTATION":
            # Extract customer
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    # Extract items from message (now returns items_to_quote, skipped_items)
                    items_to_quote, skipped_items = self._extract_quotation_items(message, customer)
                    
                    if not items_to_quote:
                        if skipped_items:
                            # Show what was skipped and why
                            if language == "sw":
                                error_text = f"❌ **Haiwezi kuunda nukuu**\n\n"
                                error_text += f"Bidhaa zote {len(skipped_items)} zilizotajwa si halali:\n\n"
                                for idx, item in enumerate(skipped_items[:5], 1):
                                    error_text += f"{idx}. {item.get('name', 'Bidhaa')}: {item.get('reason', 'Sababu haijulikani')}\n"
                                if len(skipped_items) > 5:
                                    error_text += f"\n... na nyingine {len(skipped_items) - 5}\n"
                                error_text += f"\n💡 **Kidokezo:** Hakikisha bidhaa zinauzwa na zina bei."
                                error_text += f"\n\n**Mfano sahihi:** 'Unda nukuu kwa {customer_name} na 3 vegimax-30ml'"
                            else:
                                error_text = f"❌ **Cannot create quotation**\n\n"
                                error_text += f"All {len(skipped_items)} specified items are invalid:\n\n"
                                for idx, item in enumerate(skipped_items[:5], 1):
                                    error_text += f"{idx}. {item.get('name', 'Item')}: {item.get('reason', 'Unknown reason')}\n"
                                if len(skipped_items) > 5:
                                    error_text += f"\n... and {len(skipped_items) - 5} more\n"
                                error_text += f"\n💡 **Tip:** Ensure items are sellable and have prices."
                                error_text += f"\n\n**Correct example:** 'Create quotation for {customer_name} with 3 vegimax-30ml'"
                        else:
                            if language == "sw":
                                error_text = f"❌ Tafadhali taja bidhaa na idadi kwa nukuu.\n\n"
                                error_text += f"**Mfano:** 'Unda nukuu kwa {customer.get('CardName')} na 5 vegimax'"
                            else:
                                error_text = f"❌ Please specify items and quantities for the quotation.\n\n"
                                error_text += f"**Example:** 'Create quotation for {customer.get('CardName')} with 5 vegimax'"
                        
                        result = {"message": error_text, "data": []}
                    else:
                        # Create quotation
                        quotation_result = self.quotation.create_quotation(
                            customer_code=customer.get("CardCode"),
                            items=items_to_quote,
                            comments=f"Quotation requested via AI Assistant"
                        )
                        
                        if quotation_result.get("success"):
                            # Format success message
                            if language == "sw":
                                text = f"✅ **Nukuu Imeundwa Kikamilifu!**\n\n"
                                text += f"**Mteja:** {customer.get('CardName')}\n"
                                text += f"**Namba ya Nukuu #:** {quotation_result.get('DocNum', 'N/A')}\n"
                                text += f"**Inatumika Mpaka:** {quotation_result.get('ValidUntil', 'Siku 30')}\n"
                                text += f"**Bidhaa:** {quotation_result.get('ItemCount', len(items_to_quote))}\n"
                                text += f"**Jumla ya Kiasi:** KES {quotation_result.get('TotalAmount', 0):,.2f}\n\n"
                                text += "**Bidhaa kwenye nukuu:**\n"
                            else:
                                text = f"✅ **Quotation Created Successfully!**\n\n"
                                text += f"**Customer:** {customer.get('CardName')}\n"
                                text += f"**Quotation #:** {quotation_result.get('DocNum', 'N/A')}\n"
                                text += f"**Valid Until:** {quotation_result.get('ValidUntil', '30 days')}\n"
                                text += f"**Items:** {quotation_result.get('ItemCount', len(items_to_quote))}\n"
                                text += f"**Total Amount:** KES {quotation_result.get('TotalAmount', 0):,.2f}\n\n"
                                text += "**Items in quotation:**\n"
                            
                            for idx, item in enumerate(items_to_quote, 1):
                                line_total = item['Quantity'] * item['Price']
                                if language == "sw":
                                    text += f"{idx}. {item['ItemName']} - {item['Quantity']} vitengo @ KES {item['Price']:,.2f} = KES {line_total:,.2f}\n"
                                else:
                                    text += f"{idx}. {item['ItemName']} - {item['Quantity']} units @ KES {item['Price']:,.2f} = KES {line_total:,.2f}\n"
                            
                            # Show skipped items if any
                            if skipped_items:
                                if language == "sw":
                                    text += f"\n⚠️ **Bidhaa zilizorukwa (haziu ziki au bei):**\n"
                                    for item in skipped_items[:3]:
                                        text += f"• {item.get('name', 'Bidhaa')}: {item.get('reason', 'Sababu haijulikani')}\n"
                                    if len(skipped_items) > 3:
                                        text += f"  ... na nyingine {len(skipped_items) - 3}\n"
                                else:
                                    text += f"\n⚠️ **Skipped items (not sellable/no price):**\n"
                                    for item in skipped_items[:3]:
                                        text += f"• {item.get('name', 'Item')}: {item.get('reason', 'Unknown reason')}\n"
                                    if len(skipped_items) > 3:
                                        text += f"  ... and {len(skipped_items) - 3} more\n"
                            
                            result = {"message": text, "data": [quotation_result]}
                        else:
                            # Check if it's an API limitation response
                            if quotation_result.get("api_available") == False and "web_interface_instructions" in quotation_result:
                                # Show web interface instructions
                                instructions = quotation_result["web_interface_instructions"]
                                
                                if language == "sw":
                                    text = f"⚠️ **Kuunda Nukuu Kupitia API Haiwezekani**\n\n"
                                    text += f"{instructions.get('title', 'Tafadhali tumia wavuti kuunda nukuu.')}\n\n"
                                    text += f"**Hatua:**\n"
                                    for step in instructions.get('steps', []):
                                        text += f"{step}\n"
                                    
                                    if quotation_result.get("quotation_summary"):
                                        summary = quotation_result["quotation_summary"]
                                        text += f"\n**Muhtasari wa Nukuu:**\n"
                                        text += f"• Mteja: {summary.get('customer_name')}\n"
                                        text += f"• Bidhaa: {summary.get('items_count')}\n"
                                        text += f"• Jumla: KES {summary.get('total_amount', 0):,.2f}\n"
                                else:
                                    text = f"⚠️ **Quotation Creation via API Not Available**\n\n"
                                    text += f"{instructions.get('title', 'Please use the web interface to create quotations.')}\n\n"
                                    text += f"**Steps:**\n"
                                    for step in instructions.get('steps', []):
                                        text += f"{step}\n"
                                    
                                    if quotation_result.get("quotation_summary"):
                                        summary = quotation_result["quotation_summary"]
                                        text += f"\n**Quotation Summary:**\n"
                                        text += f"• Customer: {summary.get('customer_name')}\n"
                                        text += f"• Items: {summary.get('items_count')}\n"
                                        text += f"• Total: KES {summary.get('total_amount', 0):,.2f}\n"
                            else:
                                # Standard error
                                error_msg = quotation_result.get("error", "Unknown error")
                                if language == "sw":
                                    text = f"❌ **Imeshindwa kuunda nukuu:** {error_msg}\n\n"
                                    text += f"💡 **Kidokezo:** Jaribu muundo huu:\n"
                                    text += f"• 'Unda nukuu kwa {customer_name} na 3 vegimax-30ml'"
                                else:
                                    text = f"❌ **Failed to create quotation:** {error_msg}\n\n"
                                    text += f"💡 **Tip:** Try this format:\n"
                                    text += f"• 'Create quotation for {customer_name} with 3 vegimax-30ml'"
                            
                            result = {"message": text, "data": []}

        elif intent == "GET_OUTSTANDING_DELIVERIES":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    deliveries = self.delivery.get_outstanding_deliveries(
                        customer_code=customer.get("CardCode"),
                        limit=quantity
                    )
                    
                    if not deliveries:
                        if language == "sw":
                            result = {"message": f"Hakuna usafirishaji ambao haujakamilika kwa {customer.get('CardName')}.", "data": []}
                        else:
                            result = {"message": f"No outstanding deliveries for {customer.get('CardName')}.", "data": []}
                    else:
                        if language == "sw":
                            text = f"🚚 **Usafirishaji Ambao Haujakamilika: {customer.get('CardName')}**\n\n"
                        else:
                            text = f"🚚 **Outstanding Deliveries: {customer.get('CardName')}**\n\n"
                        for i, d in enumerate(deliveries, 1):
                            if language == "sw":
                                text += f"{i}. **Usafirishaji #{d.get('DocNum')}**\n"
                                text += f"   Hali: {d.get('Status')} | ETA: {d.get('ETA')}\n"
                                text += f"   Bidhaa: {d.get('ItemCount')} | Thamani: KES {float(d.get('DocTotal', 0)):,.2f}\n"
                            else:
                                text += f"{i}. **Delivery #{d.get('DocNum')}**\n"
                                text += f"   Status: {d.get('Status')} | ETA: {d.get('ETA')}\n"
                                text += f"   Items: {d.get('ItemCount')} | Value: KES {float(d.get('DocTotal', 0)):,.2f}\n"
                            if d.get("Address"):
                                text += f"   Address: {d.get('Address')}\n"
                            text += "\n"
                        
                        result = {"message": text, "data": deliveries}

        elif intent == "TRACK_DELIVERY":
            # Track a specific delivery by number
            if not item_name:  # We'll use item_name to capture the delivery number
                if language == "sw":
                    result = {"message": "Tafadhali toa namba ya usafirishaji kufuatilia.", "data": []}
                else:
                    result = {"message": "Please provide a delivery number to track.", "data": []}
            else:
                tracking = self.delivery.track_delivery(item_name)
                
                if "error" in tracking:
                    result = {"message": tracking["error"], "data": []}
                else:
                    if language == "sw":
                        text = f"📍 **Kufuatilia Usafirishaji #{tracking['DocNum']}**\n\n"
                        text += f"**Hali:** {tracking['Status']}\n"
                        text += f"**ETA:** {tracking['ETA']}\n"
                        text += f"**Mteja:** {tracking['Customer']}\n"
                        text += f"**Anwani:** {tracking['Address']}\n\n"
                        text += "**Ratiba:**\n"
                    else:
                        text = f"📍 **Tracking Delivery #{tracking['DocNum']}**\n\n"
                        text += f"**Status:** {tracking['Status']}\n"
                        text += f"**ETA:** {tracking['ETA']}\n"
                        text += f"**Customer:** {tracking['Customer']}\n"
                        text += f"**Address:** {tracking['Address']}\n\n"
                        text += "**Timeline:**\n"
                    
                    for event in tracking.get('Timeline', []):
                        status_icon = "✅" if event['status'] == 'completed' else "⏳"
                        text += f"{status_icon} {event['event']} - {event['date'][:10]}\n"
                    
                    result = {"message": text, "data": [tracking]}
        
        elif intent == "GET_DELIVERY_HISTORY":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    history = self.delivery.get_delivery_history(
                        customer_code=customer.get("CardCode"),
                        days=30,
                        limit=quantity
                    )
                    
                    if not history:
                        if language == "sw":
                            result = {"message": f"Hakuna historia ya usafirishaji kwa {customer.get('CardName')} katika siku 30 zilizopita.", "data": []}
                        else:
                            result = {"message": f"No delivery history found for {customer.get('CardName')} in the past 30 days.", "data": []}
                    else:
                        if language == "sw":
                            text = f"📜 **Historia ya Usafirishaji: {customer.get('CardName')}** (Siku 30 zilizopita)\n\n"
                        else:
                            text = f"📜 **Delivery History: {customer.get('CardName')}** (Last 30 days)\n\n"
                        for i, d in enumerate(history, 1):
                            if language == "sw":
                                text += f"{i}. **Usafirishaji #{d.get('DocNum')}** - {d.get('DocDate')[:10]}\n"
                                text += f"   Bidhaa: {d.get('ItemCount')} | Thamani: KES {float(d.get('TotalValue', 0)):,.2f}\n"
                            else:
                                text += f"{i}. **Delivery #{d.get('DocNum')}** - {d.get('DocDate')[:10]}\n"
                                text += f"   Items: {d.get('ItemCount')} | Value: KES {float(d.get('TotalValue', 0)):,.2f}\n"
                        
                        result = {"message": text, "data": history}

        # =========================================================
        # 🎯 SMART RECOMMENDATION INTENTS - FIXED
        # =========================================================
        elif intent == "GET_CROSS_SELL":
            if not item_name:
                result = self._missing("an item name", language)
            else:
                suggestions = self.recommender.get_cross_sell_suggestions(item_name, limit=quantity or 5)
                
                # Return structured data ONLY, let the formatter create the message
                result = {
                    "item_name": item_name,
                    "recommendations": suggestions if suggestions else [],
                    "count": len(suggestions) if suggestions else 0
                }

        elif intent == "GET_UPSELL":
            if not item_name:
                result = self._missing("an item name", language)
            else:
                suggestions = self.recommender.get_upsell_suggestions(item_name, limit=quantity or 3)
                
                # Return structured data ONLY, let the formatter create the message
                result = {
                    "item_name": item_name,
                    "recommendations": suggestions if suggestions else [],
                    "count": len(suggestions) if suggestions else 0
                }

        elif intent == "GET_SEASONAL_RECOMMENDATIONS":
            # Try to extract month from message or entities
            month = None
            for m in ["january", "february", "march", "april", "may", "june",
                      "july", "august", "september", "october", "november", "december"]:
                if m in message.lower():
                    month = m
                    break
            
            suggestions = self.recommender.get_seasonal_recommendations(month=month, limit=quantity or 5)
            
            # Return structured data
            result = {
                "month": month or datetime.now().strftime("%B").lower(),
                "recommendations": suggestions if suggestions else [],
                "count": len(suggestions) if suggestions else 0
            }

        elif intent == "GET_TRENDING_PRODUCTS":
            days = 30
            # Try to extract days from query
            if "days" in message.lower():
                match = re.search(r'(\d+)\s+days', message.lower())
                if match:
                    days = int(match.group(1))
            
            suggestions = self.recommender.get_trending_products(days=days, limit=quantity or 5)
            
            # Return structured data
            result = {
                "days": days,
                "recommendations": suggestions if suggestions else [],
                "count": len(suggestions) if suggestions else 0
            }

        # =========================================================
        # 🎯 RECOMMENDATIONS (Original)
        # =========================================================
        elif intent == "RECOMMEND_ITEMS":
            # Use recommendation service for intelligent suggestions
            if item_name:
                # Get items related to searched item
                items = self.api.get_items(search=item_name, limit=1)
                if items:
                    recommended = self.recommender.get_related_items(items[0].get("ItemCode"), limit=quantity)
                else:
                    recommended = self.recommender.get_recommended_items(limit=quantity)
            elif customer_name:
                # Get items recommended for specific customer
                customer, _ = self._resolve_customer(customer_name)
                if customer:
                    recommended = self.recommender.get_items_for_customer(
                        customer_code=customer.get("CardCode"),
                        limit=quantity
                    )
                else:
                    recommended = self.recommender.get_recommended_items(limit=quantity)
            else:
                # Get popular items
                recommended = self.recommender.get_recommended_items(limit=quantity)

            if not recommended:
                if language == "sw":
                    result = {"message": "Hakuna mapendekezo yanayopatikana.", "data": []}
                else:
                    result = {"message": "No recommendations available.", "data": []}
            else:
                if language == "sw":
                    text = f"🎯 **Bidhaa {len(recommended)} Bora Zilizopendekezwa:**\n\n"
                else:
                    text = f"🎯 **Top {len(recommended)} recommended items:**\n\n"
                for i, itm in enumerate(recommended, 1):
                    on_hand = float(itm.get("OnHand", 0))
                    if language == "sw":
                        text += f"{i}. **{itm.get('ItemName')}** ({itm.get('ItemCode')})"
                        if on_hand > 0:
                            text += f" - {on_hand:,.0f} kwenye hisa"
                        text += "\n"
                    else:
                        text += f"{i}. **{itm.get('ItemName')}** ({itm.get('ItemCode')})"
                        if on_hand > 0:
                            text += f" - {on_hand:,.0f} in stock"
                        text += "\n"

                result = {"message": text, "data": recommended}

        elif intent == "RECOMMEND_CUSTOMERS":
            # Use recommendation service for intelligent customer suggestions
            if item_name:
                # Get customers who buy this item
                items = self.api.get_items(search=item_name, limit=1)
                if items:
                    recommended = self.recommender.get_customers_for_item(
                        item_code=items[0].get("ItemCode"),
                        limit=quantity
                    )
                else:
                    recommended = self.recommender.get_recommended_customers(limit=quantity)
            elif customer_name:
                # Get similar customers
                customer, _ = self._resolve_customer(customer_name)
                if customer:
                    recommended = self.recommender.get_similar_customers(
                        customer_code=customer.get("CardCode"),
                        limit=quantity
                    )
                else:
                    recommended = self.recommender.get_recommended_customers(limit=quantity)
            else:
                # Get top customers
                recommended = self.recommender.get_recommended_customers(limit=quantity)

            if not recommended:
                if language == "sw":
                    result = {"message": "Hakuna mapendekezo ya wateja yanayopatikana.", "data": []}
                else:
                    result = {"message": "No customer recommendations available.", "data": []}
            else:
                if language == "sw":
                    text = f"👥 **Wateja {len(recommended)} Bora Waliopendekezwa:**\n\n"
                else:
                    text = f"👥 **Top {len(recommended)} recommended customers:**\n\n"
                for i, cust in enumerate(recommended, 1):
                    territory = (cust.get("territory") or {}).get("descript", "")
                    if language == "sw":
                        text += f"{i}. **{cust.get('CardName')}** (Msimbo: {cust.get('CardCode')})"
                    else:
                        text += f"{i}. **{cust.get('CardName')}** (Code: {cust.get('CardCode')})"
                    if territory:
                        text += f" - {territory}"
                    text += "\n"

                result = {"message": text, "data": recommended}

        # =========================================================
        # 💬 CONVERSATIONAL & KNOWLEDGE
        # =========================================================
        elif intent == "COMPANY_INFO":
            info = kb.get_company_info()
            if language == "sw":
                text = f"🏢 **{info['name']}** - {info['tagline']}\n\n"
                text += info['about'].strip() + "\n\n"
                text += "**Maadili Yetu:**\n"
                for value in info['values']:
                    text += f"• {value}\n"
                text += "\nNikusaidiye vipi leo?"
            else:
                text = f"🏢 **{info['name']}** - {info['tagline']}\n\n"
                text += info['about'].strip() + "\n\n"
                text += "**Our Values:**\n"
                for value in info['values']:
                    text += f"• {value}\n"
                text += "\nHow can I assist you today?"
            result = {"message": text, "data": []}
        
        elif intent == "PRODUCT_INFO":
            brands = kb.get_brand_info()
            if language == "sw":
                text = "🌾 **Chapa za Bidhaa za Leysco 100**\n\n"
            else:
                text = "🌾 **Leysco 100 Product Brands**\n\n"
            
            for brand_key, brand in brands.items():
                text += f"**{brand['name']}** - {brand['category']}\n"
                text += brand['description'].strip()[:200] + "...\n\n"
                text += "Key Products:\n"
                for prod in brand['key_products'][:3]:
                    text += f"  • {prod}\n"
                text += "\n"
            
            if language == "sw":
                text += "💡 Kidokezo: Unataka kuangalia bei au upatikanaji wa hizi? Uliza tu!"
            else:
                text += "💡 Tip: Want to check prices or availability for any of these? Just ask!"
            result = {"message": text, "data": []}
        
        elif intent == "HOW_TO_ORDER":
            ordering = kb.get_ordering_info()
            if language == "sw":
                text = ordering['how_to_order'].strip() + "\n\n"
                text += "**Masharti ya Malipo:**\n"
            else:
                text = ordering['how_to_order'].strip() + "\n\n"
                text += "**Payment Terms:**\n"
            
            for key, value in ordering['payment_terms'].items():
                if isinstance(value, list):
                    if language == "sw":
                        display_key = {
                            'available_methods': 'Njia zinazokubalika',
                            'credit_terms': 'Masharti ya mkopo',
                            'mpesa': 'M-Pesa',
                            'bank_transfer': 'Uhamisho wa benki'
                        }.get(key, key.replace('_', ' ').title())
                    else:
                        display_key = key.replace('_', ' ').title()
                    text += f"• {display_key}: {', '.join(value)}\n"
                else:
                    if language == "sw":
                        display_key = {
                            'available_methods': 'Njia zinazokubalika',
                            'credit_terms': 'Masharti ya mkopo',
                            'mpesa': 'M-Pesa',
                            'bank_transfer': 'Uhamisho wa benki'
                        }.get(key, key.replace('_', ' ').title())
                    else:
                        display_key = key.replace('_', ' ').title()
                    text += f"• {display_key}: {value}\n"
            
            text += "\n" + ordering['delivery'].strip()
            result = {"message": text, "data": []}
        
        elif intent == "PAYMENT_METHODS":
            ordering = kb.get_ordering_info()
            if language == "sw":
                text = "💳 **Njia za Malipo**\n\n"
            else:
                text = "💳 **Payment Methods**\n\n"
            
            for method in ordering['payment_terms'].get('available_methods', []):
                text += f"• {method}\n"
            
            text += "\n" + ordering['payment_terms'].get('credit_terms', '')
            result = {"message": text, "data": []}
        
        elif intent == "CONTACT_INFO":
            contact = kb.get_contact_info()
            if language == "sw":
                text = "📞 **Wasiliana na Leysco 100**\n\n"
                text += "**Msaada kwa Wateja:**\n"
            else:
                text = "📞 **Contact Leysco 100**\n\n"
                text += "**Customer Support:**\n"
            
            for key, value in contact['customer_support'].items():
                if language == "sw":
                    display_key = {
                        'phone': 'Simu',
                        'email': 'Barua pepe',
                        'hours': 'Saa za kazi'
                    }.get(key, key.replace('_', ' ').title())
                else:
                    display_key = key.replace('_', ' ').title()
                text += f"• {display_key}: {value}\n"
            
            if language == "sw":
                text += "\n**Maeneo ya Mauzo:**\n"
            else:
                text += "\n**Sales Regions:**\n"
            for region in contact['sales_regions']:
                text += f"• {region['name']}: {region['contact']}\n"
            
            text += "\n" + contact['technical_support'].strip()
            result = {"message": text, "data": []}
        
        elif intent == "POLICY_QUESTION":
            policies = kb.get_policies()
            if language == "sw":
                text = "📋 **Sera za Leysco 100**\n\n"
            else:
                text = "📋 **Leysco 100 Policies**\n\n"
            text += policies['returns'].strip() + "\n\n"
            text += policies['quality_guarantee'].strip()
            result = {"message": text, "data": []}
        
        elif intent == "FAQ":
            user_msg = entities.get("item_name", "") or message
            faq_answer = kb.get_faq_answer(user_msg)
            if faq_answer:
                if language == "sw":
                    result = {"message": f"❓ **Maswali Yanayoulizwa Mara kwa Mara:** {faq_answer}", "data": []}
                else:
                    result = {"message": f"❓ **FAQ:** {faq_answer}", "data": []}

        # =========================================================
        # ❓ FALLBACK
        # =========================================================
        else:
            logger.warning(f"Intent '{intent}' not recognized")
            if language == "sw":
                result = {"error": f"Kusudi '{intent}' bado halitumiki"}
            else:
                result = {"error": f"Intent '{intent}' not supported yet"}

        # =========================================================
        # ✨ ENHANCE RESPONSE WITH CONVERSATION
        # =========================================================
        if result and "error" not in result:
            enhanced_message = self.conversation.enhance(
                intent=intent,
                original_message=result.get("message", ""),
                data=result.get("data"),
                user_message=message
            )
            result["message"] = enhanced_message
            result["language"] = language

        return result