"""
app/ai_engine/action_router.py
===============================
Routes intents to appropriate handlers with caching and optimizations.
"""

from app.services.leysco_api_service import LeyscoAPIService, clean_customer_search_term
from app.services.pricing_service import PricingService
from app.services.warehouse_service import WarehouseService
from app.services.recommendation_service import RecommendationService
from app.services.delivery_tracking_service import DeliveryTrackingService
from app.services.quotation_service import QuotationService
from app.services.customer_orders_service import CustomerOrdersService
from app.ai_engine import leysco_knowledge_base as kb
from app.ai_engine.response_formatter import ResponseFormatter
from app.ai_engine.training_actions import TrainingActions
from app.ai_engine.decision_support import DecisionSupport
from app.ai_engine.conversation_enhancer import ConversationEnhancer
from app.ai_engine.multi_turn_quotation import handle_create_quotation
from app.services.customer_health_service import CustomerHealthService
from app.services.quotation_intelligence import QuotationIntelligence
from app.services.cache_service import get_cache_service
import logging
import random
import difflib
import re
from datetime import datetime
from functools import lru_cache

logger = logging.getLogger(__name__)


class ActionRouter:
    def __init__(self):
        self.api = LeyscoAPIService()
        self.pricing = PricingService()
        self.warehouse = WarehouseService()
        self.recommender = RecommendationService(self.api)
        self.delivery = DeliveryTrackingService(self.api)
        self.quotation = QuotationService(self.api)
        self.customer_orders = CustomerOrdersService(self.api, self.pricing)
        self.training = TrainingActions()
        self.decision_support = DecisionSupport(
            api=self.api,
            pricing=self.pricing,
            warehouse=self.warehouse,
            recommender=self.recommender
        )
        self.conversation = ConversationEnhancer()
        self.formatter = ResponseFormatter()
        self.health = CustomerHealthService()
        self.quotation_intelligence = QuotationIntelligence()
        self.cache = get_cache_service()
        
        # Customer resolution cache (in-memory, short TTL)
        self._customer_resolution_cache = {}
        self._customer_cache_ttl = 300  # 5 minutes

    # =========================================================
    # INTERNAL HELPERS (with caching)
    # =========================================================

    def _resolve_customer(self, customer_name: str, item_name: str = ""):
        """Resolve customer with caching."""
        name = customer_name or item_name
        if not name:
            return None, None
        name = name.strip()
        
        # Check cache
        cache_key = f"customer_resolve:{name.lower()}"
        if cache_key in self._customer_resolution_cache:
            cached_time, cached_customer = self._customer_resolution_cache[cache_key]
            if (datetime.now() - cached_time).seconds < self._customer_cache_ttl:
                logger.info(f"📦 Customer cache hit: {name}")
                return cached_customer, name
        
        customer = self.api.resolve_customer(name)
        if customer:
            self._customer_resolution_cache[cache_key] = (datetime.now(), customer)
            return customer, name
        
        results = self.api.get_customers(search=name)
        if not results:
            return None, name
        
        name_lower = name.lower()
        for c in results:
            if (c.get("CardName") or "").lower() == name_lower:
                self._customer_resolution_cache[cache_key] = (datetime.now(), c)
                return c, name
        
        card_names = [c.get("CardName") for c in results if c.get("CardName")]
        matches = difflib.get_close_matches(name, card_names, n=1, cutoff=0.6)
        if matches:
            customer = next((c for c in results if c.get("CardName") == matches[0]), None)
            if customer:
                logger.info(f"Fuzzy matched customer: '{name}' → '{matches[0]}'")
                self._customer_resolution_cache[cache_key] = (datetime.now(), customer)
                return customer, name
        
        return None, name

    def _missing(self, what: str, language: str = "en"):
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
        """Smart not-found — suggests closest matches for items and customers."""
        if what == "Item":
            return self._smart_not_found_item(value, language)
        if what == "Customer":
            return self._smart_not_found_customer(value, language)
        if language == "sw":
            swahili_what = {"Warehouse": "Ghala", "Order": "Oda", "Quotation": "Nukuu"}.get(what, what)
            return {"message": f"{swahili_what} '{value}' haipatikani.", "data": []}
        return {"message": f"{what} '{value}' not found.", "data": []}

    def _smart_not_found_item(self, item_name: str, language: str = "en") -> dict:
        """Not-found with up to 3 closest item matches — turns dead ends into suggestions."""
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
                lines = [f"❌ Bidhaa '{item_name}' haijapatikana.\n\n💡 **Ulimaanisha mojawapo ya hizi?**"]
                for s in suggestions:
                    lines.append(f"• {s.get('ItemName')} ({s.get('ItemCode')})")
                lines.append("\nJaribu kutumia jina kamili zaidi.")
            else:
                lines = [f"❌ Item '{item_name}' not found.\n\n💡 **Did you mean one of these?**"]
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
                f"❌ Bidhaa '{item_name}' haijapatikana.\n\n💡 **Vidokezo:**\n"
                f"• Angalia tahajia\n• Jaribu jina fupi\n• Uliza 'nionyeshe bidhaa' kuona orodha kamili"
            ), "data": []}
        return {"message": (
            f"❌ Item '{item_name}' not found.\n\n💡 **Tips:**\n"
            f"• Check spelling (e.g. 'vegimax' not 'vegimx')\n"
            f"• Try a shorter name (e.g. 'cabbage' instead of 'cabbage seeds drumhead')\n"
            f"• Ask 'show me items' to browse the full catalogue"
        ), "data": []}

    def _smart_not_found_customer(self, customer_name: str, language: str = "en") -> dict:
        """Not-found with up to 3 closest customer matches."""
        try:
            suggestions = self.api.get_customers(search=customer_name, limit=5)
        except Exception:
            suggestions = []

        if suggestions:
            if language == "sw":
                lines = [f"❌ Mteja '{customer_name}' hajapatikana.\n\n💡 **Ulimaanisha mojawapo ya hawa?**"]
                for c in suggestions[:3]:
                    lines.append(f"• {c.get('CardName')} ({c.get('CardCode')})")
            else:
                lines = [f"❌ Customer '{customer_name}' not found.\n\n💡 **Did you mean one of these?**"]
                for c in suggestions[:3]:
                    lines.append(f"• {c.get('CardName')} ({c.get('CardCode')})")
            return {
                "message": "\n".join(lines),
                "data": [],
                "_suggestions": [c.get("CardName") for c in suggestions[:3]],
            }

        if language == "sw":
            return {"message": f"❌ Mteja '{customer_name}' hajapatikana.\n\n💡 Jaribu jina au msimbo tofauti, au uliza 'nionyeshe wateja'.", "data": []}
        return {"message": f"❌ Customer '{customer_name}' not found.\n\n💡 Try a different name or code, or ask 'show me customers'.", "data": []}

    def _extract_quotation_items(self, message: str, customer: dict) -> tuple:
        """Extract multiple items from a quotation message."""
        items_to_quote = []
        skipped_items = []
        logger.info(f"🔍 Extracting items from: {message}")
        
        items_part = message
        customer_name = customer.get("CardName", "") if customer else ""
        if customer_name:
            items_part = re.sub(re.escape(customer_name), '', message, flags=re.IGNORECASE)
            items_part = re.sub(r'^.*?(?:with|for)\s+', '', items_part, flags=re.IGNORECASE)
        
        prefixes_to_remove = [
            r'^create\s+(?:a\s+)?quotation\s+for\s+',
            r'^make\s+(?:a\s+)?quotation\s+for\s+',
            r'^new\s+quotation\s+for\s+',
            r'^quotation\s+for\s+',
            r'^quote\s+for\s+',
        ]
        for prefix in prefixes_to_remove:
            items_part = re.sub(prefix, '', items_part, flags=re.IGNORECASE)
        
        items_part = items_part.strip()
        logger.info(f"📦 Items part after cleaning: {items_part}")
        
        item_parts = re.split(r'\s+and\s+', items_part)
        all_matches = []
        
        for part in item_parts:
            part = part.strip()
            if not part:
                continue
            
            match = re.search(r'^(\d+)\s+(.+)$', part, re.IGNORECASE)
            if match:
                qty = int(match.group(1))
                item_search = match.group(2).strip()
                all_matches.append((qty, item_search))
                logger.info(f"📦 Extracted: qty={qty}, item='{item_search}'")
                continue
            
            match = re.search(r'^(.+?)\s+(\d+)$', part, re.IGNORECASE)
            if match:
                qty = int(match.group(2))
                item_search = match.group(1).strip()
                all_matches.append((qty, item_search))
                logger.info(f"📦 Extracted: qty={qty}, item='{item_search}'")
                continue
            
            if part:
                all_matches.append((1, part))
                logger.info(f"📦 Extracted (default qty=1): item='{part}'")
        
        if not all_matches:
            patterns = [
                r'(\d+)\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\s+and|\s+na|\s*,\s*|$)',
                r'(\d+)\s+(?:units?|pieces?|vitengo)\s+(?:of|za)?\s+([a-zA-Z0-9\-\(\)\s]+?)(?:\s+and|\s+na|\s*,\s*|$)',
                r'([a-zA-Z0-9\-\(\)\s]+?)\s+(\d+)(?:\s+and|\s+na|\s*,\s*|$)',
            ]
            
            for pattern in patterns:
                found = re.findall(pattern, items_part.lower())
                if found:
                    for match in found:
                        if len(match) == 2:
                            if match[0].isdigit():
                                qty = int(match[0])
                                item_search = match[1].strip()
                            elif match[1].isdigit():
                                qty = int(match[1])
                                item_search = match[0].strip()
                            else:
                                continue
                            all_matches.append((qty, item_search))
                    break
        
        SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL", "PACKAGING"}
        SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK", "PACK", "BAG", "BOX")
        
        for qty, item_search in all_matches:
            try:
                item_search = re.sub(r'\s+(and|na|with|for|units?|pieces?|vitengo)$', '', item_search).strip()
                logger.info(f"🔍 Searching for item: '{item_search}' (qty: {qty})")
                
                items = self.api.get_items(search=item_search, limit=10)
                if items:
                    item = None
                    for candidate in items:
                        candidate_name = candidate.get("ItemName", "").lower()
                        candidate_code = candidate.get("ItemCode", "").lower()
                        search_lower = item_search.lower()
                        
                        if search_lower == candidate_name or search_lower == candidate_code:
                            item = candidate
                            break
                        if search_lower in candidate_name or search_lower in candidate_code:
                            if not item:
                                item = candidate
                            elif len(candidate_name) < len(item.get("ItemName", "").lower()):
                                item = candidate
                    
                    if not item:
                        item = items[0]
                    
                    item_code = item.get("ItemCode")
                    item_name = item.get("ItemName")
                    item_group = (item.get("item_group") or {}).get("ItmsGrpNam", "").upper()
                    is_sellable = item.get("SellItem") == "Y"
                    is_packing = item_group in SKIP_GROUPS or any(item_code.startswith(p) for p in SKIP_PREFIXES)
                    
                    if not is_sellable or is_packing:
                        skipped_items.append({
                            "name": item_name,
                            "code": item_code,
                            "reason": f"Non-sellable item (Group: {item_group})"
                        })
                        continue
                    
                    price_result = self.pricing.get_price_for_customer(item_code=item_code, customer=customer)
                    price = price_result.get("price", 0) if price_result.get("found") else 0
                    
                    if price <= 0:
                        skipped_items.append({
                            "name": item_name,
                            "code": item_code,
                            "reason": "No price set for this customer"
                        })
                        continue
                    
                    items_to_quote.append({
                        "ItemCode": item_code,
                        "ItemName": item_name,
                        "Quantity": qty,
                        "Price": price,
                        "ItemGroup": item_group
                    })
                    logger.info(f"✅ Added item: {item_name} x{qty} @ KES {price}")
                else:
                    skipped_items.append({
                        "name": item_search,
                        "reason": "Item not found in system"
                    })
            except Exception as e:
                logger.error(f"Failed to parse item: {item_search} - {e}")
                continue
        
        logger.info(f"📦 Total items to quote: {len(items_to_quote)}, Skipped: {len(skipped_items)}")
        return items_to_quote, skipped_items

    def _create_quotation_for_customers(self, customers: list, item_name: str, item_code: str = None, language: str = "en") -> dict:
        """Helper to create quotations for a list of customers."""
        if not customers:
            return {"message": "No customers to create quotations for.", "data": []}
        
        if not item_code:
            items = self.api.get_items(search=item_name, limit=1)
            if not items:
                if language == "sw":
                    return {"message": f"Bidhaa '{item_name}' haijapatikana.", "data": []}
                return {"message": f"Item '{item_name}' not found.", "data": []}
            item_code = items[0].get("ItemCode")
            item_name = items[0].get("ItemName")
        
        created = []
        failed = []
        
        for customer in customers[:5]:
            try:
                result = self.api.create_quotation({
                    "customer_code": customer.get("CardCode"),
                    "items": [{"ItemCode": item_code, "Quantity": 1}],
                    "comments": f"AI-generated quotation for {item_name} based on purchase history"
                })
                
                if result.get("success"):
                    created.append({
                        "customer": customer.get("CardName"),
                        "quotation": result.get("DocNum", "N/A")
                    })
                else:
                    failed.append({
                        "customer": customer.get("CardName"),
                        "reason": result.get("error", "API error")
                    })
            except Exception as e:
                failed.append({
                    "customer": customer.get("CardName"),
                    "reason": str(e)
                })
        
        if language == "sw":
            text = f"📝 **Nukuu Zimeundwa**\n\n"
            if created:
                text += "✅ **Imefanikiwa:**\n"
                for c in created:
                    text += f"• {c['customer']} → Nukuu #{c['quotation']}\n"
            if failed:
                text += f"\n❌ **Imeshindwa:**\n"
                for f in failed:
                    text += f"• {f['customer']}: {f['reason']}\n"
        else:
            text = f"📝 **Quotations Created**\n\n"
            if created:
                text += "✅ **Successful:**\n"
                for c in created:
                    text += f"• {c['customer']} → Quote #{c['quotation']}\n"
            if failed:
                text += f"\n❌ **Failed:**\n"
                for f in failed:
                    text += f"• {f['customer']}: {f['reason']}\n"
        
        return {"message": text, "data": {"created": created, "failed": failed}}

    def _optimize_get_items(self, item_name: str, quantity: int = 10, language: str = "en") -> dict:
        """Optimized GET_ITEMS with single API call."""
        try:
            url = f"{self.api.base_url}/item_masterdata"
            params = {"page": 1, "per_page": min(quantity * 2, 200), "search": item_name}
            resp = self.api.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                items = self.api._normalize(resp.json())
            else:
                items = []
        except Exception as e:
            logger.error(f"Error fetching items: {e}")
            items = []
        
        if not items:
            return {"message": "Hakuna bidhaa zilizopatikana. Jaribu kutafuta bidhaa mahususi kama 'kabeji' au 'vegimax'." if language == "sw" else "No items found. Try searching for a specific product like 'cabbage' or 'vegimax'.", "data": []}
        
        SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL", "PACKAGING"}
        SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK", "PACK", "BAG", "BOX")
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
        text = f"Imepatikana bidhaa {len(items_to_show)}:\n\n" if language == "sw" else f"Found {len(items_to_show)} items:\n\n"
        for i, itm in enumerate(items_to_show, 1):
            name = itm.get('ItemName', 'Unknown')
            code = itm.get('ItemCode', 'N/A')
            group = (itm.get("item_group") or {}).get("ItmsGrpNam", "Unknown")
            on_hand = float(itm.get("OnHand", 0))
            stock_info = f" | {'Hisa' if language == 'sw' else 'Stock'}: {on_hand:,.0f}" if on_hand > 0 else ""
            text += f"{i}. {name} ({code}) — {group}{stock_info}\n"
        
        if len(items) > quantity:
            text += f"\n... and {len(items) - quantity} more items."
        
        if packing_count > 0:
            if language == "sw":
                text += f"\n\n📦 Kumbuka: Bidhaa {packing_count} za vifaa vya kufungashia zimefichwa. "
                text += "Uliza 'nionyeshe bidhaa zote pamoja na vifungashio' kuziona."
            else:
                text += f"\n\n📦 Note: {packing_count} packing/raw material items were hidden. "
                text += "Ask for 'show me all items including packing' to see them."
        
        return {"message": text, "data": items_to_show}

    # =========================================================
    # ROUTE METHOD
    # =========================================================

    def route(self, intent: str, entities: dict, message: str = "", language: str = "en"):
        item_name = (entities.get("item_name") or "").strip()
        customer_name = (entities.get("customer_name") or "").strip()
        quantity = entities.get("quantity") or 10
        warehouse_name = (entities.get("warehouse") or "").strip()
        result = None

        # =========================================================
        # CONVERSATIONAL
        # =========================================================
        if intent == "GREETING":
            if language == "sw":
                greetings = [
                    "Habari! Mimi ni msaidizi wako wa Leysco. Nikusaidie vipi leo?",
                    "Mambo! Ninaweza kukusaidia na:\n• Bei za bidhaa na hisa\n• Taarifa za wateja\n• Maelezo ya maghala\n• Mapendekezo\n\nUngependa kujua nini?",
                ]
            else:
                greetings = [
                    "Hello! I'm your Leysco AI assistant. How can I help you today?",
                    "Hi there! I can help you with:\n• Product prices and stock\n• Customer information\n• Warehouse details\n• Recommendations\n\nWhat would you like to know?",
                ]
            result = {"message": random.choice(greetings), "data": []}

        elif intent == "THANKS":
            result = {"message": "Karibu! Najulishe kama unahitaji kitu kingine chochote." if language == "sw" else "You're welcome! Let me know if you need anything else.", "data": []}

        elif intent == "SMALL_TALK":
            responses = {
                "en": [
                    "I'm doing great, thanks for asking! 😊 Ready to help with prices, stock, or customer info!",
                    "All good here! How can I assist you with Leysco products today?",
                    "Doing well! Need help checking prices or inventory?",
                    "I'm here and ready! What would you like to know about Leysco?",
                    "Feeling helpful as always! What can I do for you?"
                ],
                "sw": [
                    "Nimefurahi, asante kwa kuuliza! 😊 Niko tayari kusaidia kwa bei, hisa, au taarifa za wateja!",
                    "Salama! Nawezaje kukusaidia na bidhaa za Leysco leo?",
                    "Nzuri! Unahitaji msaada wa kuangalia bei au hisa?",
                    "Niko hapa na niko tayari! Ungependa kujua nini kuhusu Leysco?",
                    "Nina nia ya kusaidia! Nikusaidie nini?"
                ]
            }
            result = {"message": random.choice(responses.get(language, responses["en"])), "data": []}

        elif intent == "FAQ":
            if language == "sw":
                result = {"message": "Ninaweza kukusaidia na:\n\n📦 **Bidhaa**: Angalia bei, hisa, aina\n👥 **Wateja**: Tazama maelezo, oda, bei\n🏭 **Maghala**: Angalia hisa, maeneo\n🎯 **Mapendekezo**: Pendekeza bidhaa au wateja\nℹ️ **Taarifa za Kampuni**: Kuhusu Leysco, mawasiliano\n\nUliza swali lako kwa urahisi!", "data": None}
            else:
                result = {"message": "I can help you with:\n\n📦 **Products**: Check prices, stock, variants\n👥 **Customers**: View details, orders, pricing\n🏭 **Warehouses**: Check stock levels, locations\n🎯 **Recommendations**: Suggest items or customers\nℹ️ **Company Info**: About Leysco, contact details\n\nJust ask your question naturally!", "data": None}

        # =========================================================
        # TRAINING
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
        # DECISION SUPPORT
        # =========================================================
        elif intent == "ANALYZE_INVENTORY_HEALTH":
            analysis = self.decision_support.analyze_inventory_health(entities.get("warehouse"))
            if "error" in analysis:
                result = {"message": analysis["error"], "data": []}
            else:
                summary = analysis["summary"]
                if language == "sw":
                    text = f"📊 **Ripoti ya Afya ya Hisa**\n\n📍 **Ghala:** {summary['warehouse']}\n📦 **Jumla ya Bidhaa:** {summary['total_items']}\n💰 **Jumla ya Thamani:** KES {summary['total_inventory_value']:,.2f}\n\n"
                else:
                    text = f"📊 **Inventory Health Report**\n\n📍 **Warehouse:** {summary['warehouse']}\n📦 **Total Items:** {summary['total_items']}\n💰 **Total Value:** KES {summary['total_inventory_value']:,.2f}\n\n"
                for section, sw_label, en_label in [
                    ("critical_items", "⚠️ **HISA MUHIMU - AGIZA MARA MOJA**", "⚠️ **CRITICAL STOCK - ORDER IMMEDIATELY**"),
                    ("reorder_recommendations", "🔄 **Mapendekezo ya Kuagiza Tena**", "🔄 **Reorder Recommendations**"),
                    ("overstock_items", "📦 **Bidhaa Zaidi ya Hisa**", "📦 **Overstock Items**"),
                    ("fast_movers", "⚡ **Bidhaa Zinazouza Haraka**", "⚡ **Fast Movers - Keep Stocked**"),
                    ("slow_movers", "🐢 **Bidhaa Zinazokaa**", "🐢 **Slow Movers - Consider Promotion**"),
                ]:
                    items = analysis.get(section, [])
                    if items:
                        label = sw_label if language == "sw" else en_label
                        text += f"{label} ({len(items)}):\n"
                        for item in items[:5]:
                            text += f"• {item.get('name', item.get('name', '?'))}\n"
                        text += "\n"
                result = {"message": text, "data": [analysis]}

        elif intent == "GET_REORDER_DECISIONS":
            decisions = self.decision_support.get_reorder_decisions(entities.get("item_name"))
            if language == "sw":
                text = "🔄 **Maamuzi ya Kuagiza Tena**\n\n"
                if decisions.get("immediate_orders"):
                    text += "**⚠️ Maagizo ya Haraka Yanahitajika:**\n"
                    for order in decisions["immediate_orders"][:5]:
                        text += f"• **{order['name']}**: Agiza {order['recommended_qty']} vitengo (KES {order['estimated_cost']:,.0f})\n\n"
                else:
                    text += "✅ Hakuna maagizo ya haraka yanayohitajika.\n"
            else:
                text = "🔄 **Reorder Decisions**\n\n"
                if decisions.get("immediate_orders"):
                    text += "**⚠️ Immediate Orders Required:**\n"
                    for order in decisions["immediate_orders"][:5]:
                        text += f"• **{order['name']}**: Order {order['recommended_qty']} units (KES {order['estimated_cost']:,.0f})\n\n"
                else:
                    text += "✅ No immediate reorders needed.\n"
            result = {"message": text, "data": [decisions]}

        elif intent == "ANALYZE_PRICING_OPPORTUNITIES":
            opportunities = self.decision_support.analyze_pricing_opportunities(entities.get("customer_name"))
            text = "💰 **Pricing Opportunities & Insights**\n\n" if language != "sw" else "💰 **Fursa za Bei na Uchambuzi**\n\n"
            for key, label_en, label_sw in [
                ("price_drops", "📉 **Price Drops - BUY NOW!**", "📉 **Kushuka kwa Bei - NUNUA SASA!**"),
                ("price_hikes", "📈 **Price Hikes - Consider Alternatives**", "📈 **Kupanda kwa Bei**"),
                ("best_value", "✨ **Best Value Items**", "✨ **Bidhaa za Thamani Bora**"),
            ]:
                items = opportunities.get(key, [])
                if items:
                    text += (label_sw if language == "sw" else label_en) + "\n"
                    for opp in items[:5]:
                        text += f"• {opp['name']}: KES {opp.get('current', opp.get('price', 0)):,.0f}\n"
                    text += "\n"
            result = {"message": text, "data": [opportunities]}

        elif intent == "ANALYZE_CUSTOMER_BEHAVIOR":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                analysis = self.decision_support.analyze_customer_behavior(customer_name)
                if "error" in analysis:
                    result = {"message": analysis["error"], "data": []}
                else:
                    cname = analysis['customer']['name']
                    patterns = analysis.get("purchase_patterns", {})
                    text = f"👥 **{'Uchambuzi wa Mteja' if language == 'sw' else 'Customer Insights'}: {cname}**\n\n"
                    if patterns:
                        text += f"📊 **{'Mifumo ya Ununuzi' if language == 'sw' else 'Purchase Patterns'}**\n"
                        text += f"• {'Jumla ya Oda' if language == 'sw' else 'Total Orders'}: {patterns.get('total_orders', 0)}\n"
                        text += f"• {'Jumla ya Matumizi' if language == 'sw' else 'Total Spent'}: KES {patterns.get('total_spent', 0):,.2f}\n"
                        text += f"• {'Wastani wa Oda' if language == 'sw' else 'Avg Order Value'}: KES {patterns.get('avg_order_value', 0):,.2f}\n\n"
                    for key, label_sw, label_en in [
                        ("recommendations", "💡 **Mapendekezo**", "💡 **Recommendations**"),
                        ("upsell_opportunities", "📈 **Fursa za Kuuza Zaidi**", "📈 **Upsell Opportunities**"),
                        ("risk_factors", "⚠️ **Sababu za Hatari**", "⚠️ **Risk Factors**"),
                    ]:
                        items = analysis.get(key, [])
                        if items:
                            text += (label_sw if language == "sw" else label_en) + "\n"
                            for item in items:
                                text += f"• {item}\n"
                            text += "\n"
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
                        text = f"📈 **Utabiri wa Mahitaji: {forecast['item_name']}**\n\n📍 **Hisa ya Sasa:** {forecast['current_stock']} vitengo\n📊 **Wastani wa Kila Siku:** {forecast['daily_avg']} vitengo\n\n"
                    else:
                        text = f"📈 **Demand Forecast: {forecast['item_name']}**\n\n📍 **Current Stock:** {forecast['current_stock']} units\n📊 **Daily Average:** {forecast['daily_avg']} units\n\n"
                    text += f"💡 **{'Mapendekezo' if language == 'sw' else 'Recommendation'}:** {forecast['recommendation']}"
                    result = {"message": text, "data": [forecast]}

        # =========================================================
        # ITEMS (OPTIMIZED)
        # =========================================================
        elif intent == "GET_ITEMS":
            result = self._optimize_get_items(item_name, quantity, language)

        elif intent in ["GET_SELLABLE_ITEMS", "GET_PURCHASABLE_ITEMS", "GET_INVENTORY_ITEMS"]:
            all_items = []
            # Optimize: single API call with larger per_page
            try:
                url = f"{self.api.base_url}/item_masterdata"
                resp = self.api.session.get(url, params={"page": 1, "per_page": 200, "search": item_name}, timeout=15)
                if resp.status_code == 200:
                    all_items = self.api._normalize(resp.json())
            except Exception as e:
                logger.error(f"Error fetching items: {e}")
            
            if not all_items:
                result = {"message": "Hakuna bidhaa zilizopatikana kwenye mfumo." if language == "sw" else "No items found in the system.", "data": []}
            else:
                flag_map = {"GET_SELLABLE_ITEMS": "SellItem", "GET_PURCHASABLE_ITEMS": "PrchseItem", "GET_INVENTORY_ITEMS": "InvntItem"}
                flag = flag_map[intent]
                filtered = [i for i in all_items if i.get(flag) == "Y"]
                items_to_show = (filtered if filtered else all_items)[:quantity]
                filter_name = {"GET_SELLABLE_ITEMS": "Sellable", "GET_PURCHASABLE_ITEMS": "Purchasable", "GET_INVENTORY_ITEMS": "Inventory"}[intent]
                text = f"📦 **{filter_name} Items** ({len(items_to_show)} of {len(filtered)} found):\n\n"
                for i, itm in enumerate(items_to_show, 1):
                    text += f"{i}. {itm.get('ItemName')} ({itm.get('ItemCode')})\n"
                result = {"message": text, "data": items_to_show}

        elif intent == "GET_ITEMS_ADVANCED":
            inventory = self.api.get_inventory_report(search=item_name, limit=200)
            if not inventory:
                result = {"message": "Hakuna rekodi za hisa zilizopatikana." if language == "sw" else "No inventory records found.", "data": []}
            else:
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
                text = f"📊 {'Bidhaa za Hisa' if language == 'sw' else 'Inventory Items'} ({len(items)} found):\n"
                for i, itm in enumerate(items, 1):
                    text += f"{i}. {itm['ItemName']} — {'Jumla ya Hisa' if language == 'sw' else 'Total Stock'}: {itm['TotalStock']:,.0f}\n"
                result = {"message": text, "data": items}

        elif intent == "GET_ITEM_DETAILS":
            if not item_name:
                result = self._missing("the item you want details for", language)
            else:
                item = self.api.get_item_by_name(item_name)
                if not item:
                    result = self._not_found("Item", item_name, language)
                else:
                    on_hand = float(item.get("OnHand", 0))
                    committed = float(item.get("IsCommited", 0))
                    if language == "sw":
                        text = f"📋 **Maelezo ya Bidhaa**\n\n**Jina:** {item.get('ItemName')}\n**Msimbo:** {item.get('ItemCode')}\n**Kundi:** {item.get('item_group', {}).get('ItmsGrpNam', 'N/A')}\n**Hisa:** {on_hand:,.0f}\n**Iliyoahidiwa:** {committed:,.0f}\n**Inayopatikana:** {on_hand - committed:,.0f}\n"
                    else:
                        text = f"📋 **Item Details**\n\n**Name:** {item.get('ItemName')}\n**Code:** {item.get('ItemCode')}\n**Group:** {item.get('item_group', {}).get('ItmsGrpNam', 'N/A')}\n**On Hand:** {on_hand:,.0f}\n**Committed:** {committed:,.0f}\n**Available:** {on_hand - committed:,.0f}\n"
                    result = {"message": text, "data": [item]}

        # =========================================================
        # PRICING
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
                        text_lines = [f"💰 **{customer.get('CardName')} - {'Bei' if language == 'sw' else 'Pricing'}**\n"]
                        for itm in items:
                            pr = self.pricing.get_price_for_customer(item_code=itm.get("ItemCode"), customer=customer)
                            if pr["found"]:
                                text_lines.append(f"• **{itm.get('ItemName')}**: KES {pr['price']:,.2f}")
                                results.append(pr)
                        if not results:
                            text_lines.append("Hakuna bei zilizopatikana kwa bidhaa hizi." if language == "sw" else "No prices available for these items.")
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

                    SKIP_GROUPS = {"PACKING MATERIAL", "RAW MATERIAL"}
                    SKIP_PREFIXES = ("RMST", "RMOP", "RMFC", "RMPA", "RMPK")
                    
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
                                    f"• **{item_name_full}** ({item_code}){type_str}\n"
                                    f"  KES {price_result['price']:,.2f}{gross_tag}{uom_tag} [{price_result['price_list_name']}]"
                                )
                            else:
                                text_lines.append(
                                    f"• **{item_name_full}** ({item_code}){type_str}\n"
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
                        if not final_message or final_message in [
                            f"💰 **Bei za '{item_name}'**\n",
                            f"💰 **Prices for '{item_name}'**\n"
                        ]:
                            if language == "sw":
                                final_message = f"Imepatikana bidhaa {len(results)} zinazolingana na '{item_name}' zenye bei."
                            else:
                                final_message = f"Found {len(results)} items matching '{item_name}' with pricing information."
                        
                        logger.info(f"📤 GET_ITEM_PRICE returning message length: {len(final_message)} chars, {len(results)} items")
                        result = {"message": final_message, "data": results}
        
        # =========================================================
        # CUSTOMERS (OPTIMIZED)
        # =========================================================
        elif intent == "GET_CUSTOMERS":
            try:
                # Check cache first
                cache_key = f"get_customers:{customer_name}:{quantity}"
                cached = self.cache.get("GET_CUSTOMERS", {"customer_name": customer_name, "quantity": quantity}, "")
                if cached:
                    logger.info(f"📦 Cache hit for GET_CUSTOMERS")
                    return cached
                
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
                    
                    # Cache the result
                    self.cache.set("GET_CUSTOMERS", {"customer_name": customer_name, "quantity": quantity}, "", result)
                    
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
                # Check cache
                cache_key = f"customer_details:{customer_name.lower()}"
                cached = self.cache.get("GET_CUSTOMER_DETAILS", {"customer_name": customer_name}, "")
                if cached:
                    logger.info(f"📦 Cache hit for customer: {customer_name}")
                    return cached
                
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    territory = customer.get("territory") or {}
                    octg = customer.get("octg") or {}
                    territory_desc = territory.get("descript", "N/A") if isinstance(territory, dict) else "N/A"
                    payment_terms = octg.get("PymntGroup", "N/A") if isinstance(octg, dict) else "N/A"
                    credit_limit = float(octg.get("CredLimit", 0)) if isinstance(octg, dict) else 0.0
                    if language == "sw":
                        text = f"👤 **Maelezo ya Mteja**\n\n**Jina:** {customer.get('CardName', 'N/A')}\n**Msimbo:** {customer.get('CardCode', 'N/A')}\n**Eneo:** {territory_desc}\n**Masharti ya Malipo:** {payment_terms}\n**Kikomo cha Mkopo:** KES {credit_limit:,.2f}\n**Simu:** {customer.get('Phone1', 'N/A')}\n**Anwani:** {customer.get('Address', 'N/A')}\n"
                    else:
                        text = f"👤 **Customer Details**\n\n**Name:** {customer.get('CardName', 'N/A')}\n**Code:** {customer.get('CardCode', 'N/A')}\n**Territory:** {territory_desc}\n**Payment Terms:** {payment_terms}\n**Credit Limit:** KES {credit_limit:,.2f}\n**Phone:** {customer.get('Phone1', 'N/A')}\n**Address:** {customer.get('Address', 'N/A')}\n"
                    group_code = customer.get("GroupCode")
                    if group_code:
                        text += f"**Group Code:** {group_code}\n"
                    try:
                        health = self.health.score(customer_code=customer.get("CardCode"), customer_name=customer.get("CardName"))
                        if not health.get("error"):
                            s, grade, emoji = health["score"], health["grade"], health["emoji"]
                            text += f"\n{emoji} **{'Alama ya Afya' if language == 'sw' else 'Health Score'}:** {s:.0f}/100 ({grade})\n"
                            if health["recommendations"]:
                                text += f"💡 {health['recommendations'][0]}\n"
                    except Exception as _he:
                        logger.debug("Health score failed: %s", _he)
                    result = {"message": text, "data": [customer]}
                    
                    # Cache the result
                    self.cache.set("GET_CUSTOMER_DETAILS", {"customer_name": customer_name}, "", result)

        # =========================================================
        # WAREHOUSES
        # =========================================================
        elif intent == "GET_WAREHOUSES":
            wh_name = (entities.get("warehouse") or "").strip()
            if wh_name:
                warehouses = self.warehouse.search_warehouses(query=wh_name, active_only=True)
                if not warehouses:
                    result = {"message": f"Hakuna ghala lililopatikana linalolingana na '{wh_name}'." if language == "sw" else f"No warehouses found matching '{wh_name}'.", "data": []}
                else:
                    wh = warehouses[0]
                    stock_summary = self.warehouse.get_warehouse_stock_summary(wh.get("WhsCode"))
                    text = f"🏭 **{wh.get('WhsName')}** ({wh.get('WhsCode')})\n\n📊 **{'Muhtasari wa Hisa' if language == 'sw' else 'Stock Summary'}:**\n"
                    text += f"   Total Items: {stock_summary.get('total_items', 0):,}\n"
                    text += f"   Available: {stock_summary.get('total_available', 0):,}\n"
                    result = {"message": text, "data": [stock_summary]}
            else:
                summaries = self.warehouse.get_all_warehouses_summary()
                active = [s for s in summaries if s["details"].get("Inactive") != "Y"]
                if not active:
                    result = {"message": "Hakuna maghala yanayotumika yaliyopatikana." if language == "sw" else "No active warehouses found.", "data": []}
                else:
                    text = f"🏭 **Found {len(active)} active warehouses:**\n\n"
                    for s in active[:15]:
                        text += f"**{s['WhsName']}** ({s['WhsCode']}) — Items: {s['total_items']:,} | Available: {s['total_available']:,}\n"
                    result = {"message": text, "data": active}

        elif intent == "GET_WAREHOUSE_STOCK":
            if not warehouse_name:
                result = {"message": "Tafadhali taja jina la ghala au msimbo." if language == "sw" else "Please specify a warehouse name or code.", "data": []}
            else:
                warehouses = self.warehouse.search_warehouses(query=warehouse_name)
                if not warehouses:
                    result = {"message": f"Ghala '{warehouse_name}' halijapatikana." if language == "sw" else f"Warehouse '{warehouse_name}' not found.", "data": []}
                else:
                    wh = warehouses[0]
                    stock_summary = self.warehouse.get_warehouse_stock_summary(wh.get("WhsCode"))
                    if "error" in stock_summary:
                        result = {"message": stock_summary["error"], "data": []}
                    else:
                        text = f"📊 **{'Ripoti ya Hisa' if language == 'sw' else 'Stock Report'}: {wh.get('WhsName')}**\n\n"
                        text += f"Total Items: {stock_summary['total_items']:,} | Available: {stock_summary['total_available']:,}\n\n"
                        for i, itm in enumerate(stock_summary.get("top_items", [])[:10], 1):
                            text += f"{i}. **{itm['ItemName']}** — On Hand: {itm['OnHand']:,}\n"
                        result = {"message": text, "data": [stock_summary]}

        elif intent == "GET_LOW_STOCK_ALERTS":
            wh_name = (entities.get("warehouse") or "").strip()
            if wh_name:
                warehouses = self.warehouse.search_warehouses(query=wh_name)
                if not warehouses:
                    result = {"message": f"Ghala '{wh_name}' halijapatikana." if language == "sw" else f"Warehouse '{wh_name}' not found.", "data": []}
                    alerts = []
                else:
                    alerts = self.warehouse.get_low_stock_alerts(whscode=warehouses[0].get("WhsCode"))
                    title = f"⚠️ Low Stock Alerts: {warehouses[0].get('WhsName')}"
            else:
                alerts = self.warehouse.get_low_stock_alerts()
                title = "⚠️ Low Stock Alerts (All Warehouses)"
            if 'alerts' in dir() and not alerts:
                result = {"message": "Hakuna arifa za hisa chache kwa sasa." if language == "sw" else "No low stock alerts at this time.", "data": []}
            elif 'alerts' in dir():
                critical = [a for a in alerts if a["Severity"] == "CRITICAL"]
                low = [a for a in alerts if a["Severity"] == "LOW"]
                text = f"{title}\n\n"
                if critical:
                    text += f"🔴 **CRITICAL** ({len(critical)} items):\n"
                    for a in critical[:10]:
                        text += f"• {a['ItemName']} @ {a['WhsCode']} — Available: {a['Available']:,}\n"
                if low:
                    text += f"\n🟡 **LOW** ({len(low)} items):\n"
                    for a in low[:10]:
                        text += f"• {a['ItemName']} @ {a['WhsCode']} — Available: {a['Available']:,}\n"
                result = {"message": text, "data": alerts}

        # =========================================================
        # ANALYTICS: TOP SELLING ITEMS (NEW)
        # =========================================================
        elif intent == "GET_TOP_SELLING_ITEMS":
            logger.info(f"📊 Processing GET_TOP_SELLING_ITEMS intent")
            
            # Extract limit from entities or message
            limit = quantity if isinstance(quantity, int) and quantity > 0 else 10
            days = 30
            
            # Check for days in message
            days_match = re.search(r'(\d+)\s+days', message, re.IGNORECASE)
            if days_match:
                days = int(days_match.group(1))
            
            # Also check for limit in message like "top 5"
            limit_match = re.search(r'top\s+(\d+)', message, re.IGNORECASE)
            if limit_match:
                limit = int(limit_match.group(1))
            
            logger.info(f"📊 Getting top {limit} selling items for last {days} days")
            
            try:
                top_items = self.api.get_top_selling_items(limit=limit, days=days)
                
                if not top_items:
                    if language == "sw":
                        result = {"message": "Hakuna bidhaa zilizopatikana kwa kipindi hiki. Jaribu kuuliza kwa siku chache au angalia baadaye.", "data": []}
                    else:
                        result = {"message": "No top selling items found for this period. Try asking for fewer days or check back later.", "data": []}
                else:
                    if language == "sw":
                        text = f"📊 **Bidhaa {min(limit, len(top_items))} Zinazouzwa Sana** (Siku {days} zilizopita)\n\n"
                        for i, item in enumerate(top_items[:limit], 1):
                            name = item.get('ItemName', 'Unknown')
                            score = item.get('PopularityScore', 0)
                            velocity = item.get('Velocity', 'MEDIUM')
                            
                            if velocity == "VERY_HIGH":
                                emoji = "🔥🔥"
                            elif velocity == "HIGH":
                                emoji = "🔥"
                            elif velocity == "MEDIUM":
                                emoji = "📈"
                            elif velocity == "LOW":
                                emoji = "📉"
                            else:
                                emoji = "❄️"
                            
                            text += f"{i}. {emoji} **{name}**\n"
                            if score > 0:
                                text += f"   📊 Alama ya Umaarufu: {score:.1f}/100\n"
                            text += "\n"
                        
                        text += "\n💡 **Vidokezo:**\n"
                        text += "• Uliza 'nionyeshe hisa' kuangalia upatikanaji\n"
                        text += "• Uliza 'bei ya [bidhaa]' kuona bei\n"
                    else:
                        text = f"📊 **Top {min(limit, len(top_items))} Selling Items** (Last {days} days)\n\n"
                        for i, item in enumerate(top_items[:limit], 1):
                            name = item.get('ItemName', 'Unknown')
                            score = item.get('PopularityScore', 0)
                            velocity = item.get('Velocity', 'MEDIUM')
                            
                            if velocity == "VERY_HIGH":
                                emoji = "🔥🔥"
                            elif velocity == "HIGH":
                                emoji = "🔥"
                            elif velocity == "MEDIUM":
                                emoji = "📈"
                            elif velocity == "LOW":
                                emoji = "📉"
                            else:
                                emoji = "❄️"
                            
                            text += f"{i}. {emoji} **{name}**\n"
                            if score > 0:
                                text += f"   📊 Popularity Score: {score:.1f}/100\n"
                            text += "\n"
                        
                        text += "\n💡 **Next Steps:**\n"
                        text += "• Ask 'check stock' to see availability\n"
                        text += "• Ask 'price of [item]' to see pricing\n"
                        text += "• Ask 'create quotation' to generate quotes"
                    
                    result = {"message": text, "data": top_items}
                    
            except Exception as e:
                logger.error(f"Error in GET_TOP_SELLING_ITEMS: {e}")
                if language == "sw":
                    result = {"message": f"Hitilafu wakati wa kupata bidhaa zinazouzwa sana: {str(e)}\n\nJaribu tena baadaye.", "data": []}
                else:
                    result = {"message": f"Error fetching top selling items: {str(e)}\n\nPlease try again later.", "data": []}

        # =========================================================
        # ANALYTICS: SLOW MOVING ITEMS (NEW)
        # =========================================================
        elif intent == "GET_SLOW_MOVING_ITEMS":
            logger.info(f"📊 Processing GET_SLOW_MOVING_ITEMS intent")
            
            # Extract limit from entities or message
            limit = quantity if isinstance(quantity, int) and quantity > 0 else 10
            days = 90  # Default 90 days for slow moving
            threshold = 0.5  # Default turnover threshold
            
            # Check for days in message
            days_match = re.search(r'(\d+)\s+days', message, re.IGNORECASE)
            if days_match:
                days = int(days_match.group(1))
            
            # Check for limit
            limit_match = re.search(r'slow\s+(\d+)', message, re.IGNORECASE)
            if limit_match:
                limit = int(limit_match.group(1))
            
            logger.info(f"📊 Getting {limit} slow moving items over {days} days with threshold {threshold}")
            
            try:
                slow_items = self.api.get_slow_moving_items(limit=limit, days=days, turnover_threshold=threshold)
                
                if not slow_items:
                    if language == "sw":
                        result = {"message": "Hakuna bidhaa zilizopatikana zinazotembea polepole kwa kipindi hiki. Hii ni nzuri - hisa zako zinasonga vizuri!", "data": []}
                    else:
                        result = {"message": "No slow moving items found for this period. This is good - your inventory is moving well!", "data": []}
                else:
                    if language == "sw":
                        text = f"📊 **Bidhaa {len(slow_items)} Zinazotembea Polepole** (Siku {days} zilizopita)\n\n"
                        text += "⚠️ **Bidhaa hizi zinahitaji uangalizi:**\n\n"
                        
                        for i, item in enumerate(slow_items[:limit], 1):
                            name = item.get('ItemName', 'Unknown')
                            turnover = item.get('TurnoverRate', 0)
                            severity = item.get('Severity', 'monitor')
                            recommendation = item.get('Recommendation', '')
                            
                            if severity == "critical":
                                emoji = "🔴"
                            elif severity == "warning":
                                emoji = "🟡"
                            else:
                                emoji = "🟢"
                            
                            text += f"{i}. {emoji} **{name}**\n"
                            text += f"   📊 Kiwango cha Mzunguko: {turnover:.2f}\n"
                            if recommendation:
                                text += f"   💡 {recommendation}\n"
                            text += "\n"
                        
                        text += "\n💡 **Mapendekezo:**\n"
                        text += "• Fanya promo au punguza bei\n"
                        text += "• Fungasha na bidhaa zinazouzwa sana\n"
                        text += "• Wasiliana na wateja wanao nunua bidhaa kama hizi"
                    else:
                        text = f"📊 **Top {len(slow_items)} Slow Moving Items** (Last {days} days)\n\n"
                        text += "⚠️ **These items need attention:**\n\n"
                        
                        for i, item in enumerate(slow_items[:limit], 1):
                            name = item.get('ItemName', 'Unknown')
                            turnover = item.get('TurnoverRate', 0)
                            severity = item.get('Severity', 'monitor')
                            recommendation = item.get('Recommendation', '')
                            
                            if severity == "critical":
                                emoji = "🔴"
                            elif severity == "warning":
                                emoji = "🟡"
                            else:
                                emoji = "🟢"
                            
                            text += f"{i}. {emoji} **{name}**\n"
                            text += f"   📊 Turnover Rate: {turnover:.2f}\n"
                            if recommendation:
                                text += f"   💡 {recommendation}\n"
                            text += "\n"
                        
                        text += "\n💡 **Recommendations:**\n"
                        text += "• Run promotions or markdowns\n"
                        text += "• Bundle with popular items\n"
                        text += "• Reach out to customers who buy similar products"
                    
                    result = {"message": text, "data": slow_items}
                    
            except Exception as e:
                logger.error(f"Error in GET_SLOW_MOVING_ITEMS: {e}")
                if language == "sw":
                    result = {"message": f"Hitilafu wakati wa kupata bidhaa zinazotembea polepole: {str(e)}\n\nJaribu tena baadaye.", "data": []}
                else:
                    result = {"message": f"Error fetching slow moving items: {str(e)}\n\nPlease try again later.", "data": []}

        # =========================================================
        # ORDERS / INVOICES / QUOTATIONS
        # =========================================================
        elif intent == "GET_CUSTOMER_ORDERS":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    try:
                        orders = self.customer_orders.get_customer_orders(
                            customer_name=customer.get("CardName"),
                            limit=quantity or 10,
                            doc_status="all",
                            include_details=False
                        )
                        
                        if not orders:
                            if language == "sw":
                                result = {"message": f"📋 Hakuna oda zilizopatikana kwa {customer.get('CardName')}.\n\n💡 Unda nukuu: 'unda nukuu kwa {customer_name} na 5 vegimax'", "data": []}
                            else:
                                result = {"message": f"📋 No orders found for {customer.get('CardName')}.\n\n💡 Create a quote: 'create quotation for {customer_name} with 5 vegimax'", "data": []}
                        else:
                            summary = self.customer_orders.get_order_summary(customer.get("CardName"))
                            
                            if language == "sw":
                                text = f"📋 **Oda za {customer.get('CardName')}**\n\n"
                                text += f"📊 **Muhtasari:** {summary.get('total_orders', 0)} oda, "
                                text += f"KES {summary.get('total_value', 0):,.2f} thamani\n"
                                text += f"   • Wazi: {summary.get('open_orders', 0)} | Imefungwa: {summary.get('closed_orders', 0)}\n\n"
                                
                                for i, o in enumerate(orders[:10], 1):
                                    text += f"{i}. **Oda {o.get('DocNum')}** ({str(o.get('DocDate', ''))[:10]}) — "
                                    text += f"KES {float(o.get('DocTotal', 0)):,.2f} ({o.get('StatusText', 'Unknown')})\n"
                            else:
                                text = f"📋 **Orders for {customer.get('CardName')}**\n\n"
                                text += f"📊 **Summary:** {summary.get('total_orders', 0)} orders, "
                                text += f"KES {summary.get('total_value', 0):,.2f} total\n"
                                text += f"   • Open: {summary.get('open_orders', 0)} | Closed: {summary.get('closed_orders', 0)}\n\n"
                                
                                for i, o in enumerate(orders[:10], 1):
                                    text += f"{i}. **Order {o.get('DocNum')}** ({str(o.get('DocDate', ''))[:10]}) — "
                                    text += f"KES {float(o.get('DocTotal', 0)):,.2f} ({o.get('StatusText', 'Unknown')})\n"
                            
                            if len(orders) > 10:
                                text += f"\n... na {len(orders) - 10} oda zaidi"
                            
                            result = {"message": text, "data": orders}
                            
                    except Exception as e:
                        logger.error(f"Error fetching orders: {e}")
                        if language == "sw":
                            result = {"message": f"Hitilafu wakati wa kupata oda: {str(e)}\n\nJaribu tena baadaye.", "data": []}
                        else:
                            result = {"message": f"Error fetching orders: {str(e)}\n\nPlease try again.", "data": []}

        elif intent in ["GET_CUSTOMER_INVOICES", "GET_OUTSTANDING_INVOICES"]:
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    invoices = self.api.fetch_marketing_docs(card_code=customer.get("CardCode"), doc_type=13)
                    if not invoices:
                        result = {"message": f"No invoices found for {customer.get('CardName')}.", "data": []}
                    else:
                        text = f"🧾 **Invoices for {customer.get('CardName')}** ({len(invoices)} total)\n\n"
                        for i, inv in enumerate(invoices[:quantity], 1):
                            text += f"{i}. **Invoice {inv.get('DocNum')}** — KES {float(inv.get('DocTotal', 0)):,.2f}\n"
                        result = {"message": text, "data": invoices}

        elif intent == "GET_QUOTATIONS":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    quotes = self.api.get_customer_quotations(customer_name=customer.get("CardName"), limit=quantity or 10)
                    if not quotes:
                        result = {"message": f"📋 **No quotations found for {customer.get('CardName')}**\n\n💡 Create one: 'create quotation for {customer_name} with 5 vegimax'", "data": []}
                    else:
                        text = f"💼 **Quotations for {customer.get('CardName')}** ({len(quotes)} total)\n\n"
                        for i, q in enumerate(quotes, 1):
                            valid = (q.get('DocDueDate') or '')[:10]
                            text += f"{i}. **Quote {q.get('DocNum')}** — KES {float(q.get('DocTotal', 0)):,.2f}{f' (valid until {valid})' if valid else ''}\n"
                        result = {"message": text, "data": quotes}

        # =========================================================
        # CREATE QUOTATION (MULTI-TURN)
        # =========================================================
        elif intent == "CREATE_QUOTATION":
            sid = entities.get("_session_id", "")
            result = handle_create_quotation(
                message=message,
                entities=entities,
                session_id=sid,
                action_router_self=self,
                language=language,
            )

        # =========================================================
        # DELIVERIES
        # =========================================================
        elif intent == "GET_OUTSTANDING_DELIVERIES":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    deliveries = self.delivery.get_outstanding_deliveries(customer_code=customer.get("CardCode"), limit=quantity)
                    if not deliveries:
                        result = {"message": f"No outstanding deliveries for {customer.get('CardName')}.", "data": []}
                    else:
                        text = f"🚚 **Outstanding Deliveries: {customer.get('CardName')}**\n\n"
                        for i, d in enumerate(deliveries, 1):
                            text += f"{i}. **Delivery #{d.get('DocNum')}** — Status: {d.get('Status')} | ETA: {d.get('ETA')}\n"
                        result = {"message": text, "data": deliveries}

        elif intent == "TRACK_DELIVERY":
            if not item_name:
                result = {"message": "Please provide a delivery number to track.", "data": []}
            else:
                tracking = self.delivery.track_delivery(item_name)
                if "error" in tracking:
                    result = {"message": tracking["error"], "data": []}
                else:
                    text = f"📍 **Tracking Delivery #{tracking['DocNum']}**\n\n**Status:** {tracking['Status']}\n**ETA:** {tracking['ETA']}\n**Customer:** {tracking['Customer']}\n\n**Timeline:**\n"
                    for event in tracking.get('Timeline', []):
                        text += f"{'✅' if event['status'] == 'completed' else '⏳'} {event['event']} - {event['date'][:10]}\n"
                    result = {"message": text, "data": [tracking]}

        elif intent == "GET_DELIVERY_HISTORY":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                customer, search_name = self._resolve_customer(customer_name)
                if not customer:
                    result = self._not_found("Customer", search_name, language)
                else:
                    history = self.delivery.get_delivery_history(customer_code=customer.get("CardCode"), days=30, limit=quantity)
                    if not history:
                        result = {"message": f"No delivery history for {customer.get('CardName')} in the past 30 days.", "data": []}
                    else:
                        text = f"📜 **Delivery History: {customer.get('CardName')}** (Last 30 days)\n\n"
                        for i, d in enumerate(history, 1):
                            text += f"{i}. **Delivery #{d.get('DocNum')}** - {(d.get('DocDate') or '')[:10]} — KES {float(d.get('TotalValue', 0)):,.2f}\n"
                        result = {"message": text, "data": history}

        # =========================================================
        # RECOMMENDATIONS - ENHANCED WITH CUSTOMER SEGMENTATION
        # =========================================================
        
        # FIND_CUSTOMERS_BY_ITEM - "sell out vegimax", "which customer would buy X"
        elif intent == "FIND_CUSTOMERS_BY_ITEM":
            if not item_name:
                result = self._missing("an item name", language)
            else:
                logger.info(f"🎯 Finding customers for item: {item_name}")
                
                # Check cache first
                cache_key = f"customers_for_item:{item_name.lower()}:{quantity}"
                cached_result = self.cache.get("FIND_CUSTOMERS_BY_ITEM", {"item_name": item_name, "quantity": quantity}, "")
                if cached_result:
                    logger.info(f"📦 Cache hit for FIND_CUSTOMERS_BY_ITEM: {item_name}")
                    return cached_result
                
                items = self.api.get_items(search=item_name, limit=5)
                if not items:
                    result = self._smart_not_found_item(item_name, language)
                else:
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
                    
                    logger.info(f"🎯 Matched item: {item_full_name} ({item_code})")
                    
                    customers = self.recommender.get_customers_for_item(
                        item_code=item_code, 
                        limit=quantity or 10
                    )
                    
                    if not customers:
                        if language == "sw":
                            text = f"🔍 **Hakuna wateja waliojitokeza kwa '{item_full_name}'**\n\n"
                            text += "💡 **Mapendekezo:**\n"
                            text += "• Angalia bidhaa kama 'vegimax', 'easeed', au 'maize'\n"
                            text += "• Jaribu neno tofauti la bidhaa\n"
                            text += "• Uliza 'nionyeshe wateja wanaonunua bidhaa kama hizi'"
                        else:
                            text = f"🔍 **No customers found for '{item_full_name}'**\n\n"
                            text += "💡 **Suggestions:**\n"
                            text += "• Check similar products like 'vegimax', 'easeed', or 'maize'\n"
                            text += "• Try a different product name\n"
                            text += "• Ask 'show me customers who buy similar products'"
                        
                        result = {"message": text, "data": []}
                    else:
                        if language == "sw":
                            text = f"🎯 **Wateja Wanaonunua {item_full_name}**\n\n"
                            text += f"📊 **Wateja {len(customers)} waliojitokeza:**\n\n"
                        else:
                            text = f"🎯 **Customers Who Buy {item_full_name}**\n\n"
                            text += f"📊 **Found {len(customers)} customers:**\n\n"
                        
                        for i, cust in enumerate(customers[:quantity], 1):
                            cust_name = cust.get("CardName", "Unknown")
                            cust_code = cust.get("CardCode", "N/A")
                            qty = cust.get("PurchaseQuantity", 0)
                            last_purchase = cust.get("LastPurchaseDate", "")
                            reason = cust.get("RecommendationReason", "")
                            
                            if language == "sw":
                                text += f"{i}. **{cust_name}** (Msimbo: {cust_code})\n"
                                if qty > 0:
                                    text += f"   📦 Kiasi: {qty:,.0f} vitengo\n"
                                if last_purchase:
                                    text += f"   🕒 Kununuliwa mwisho: {last_purchase[:10]}\n"
                                if reason:
                                    text += f"   💡 {reason}\n"
                                text += "\n"
                            else:
                                text += f"{i}. **{cust_name}** (Code: {cust_code})\n"
                                if qty > 0:
                                    text += f"   📦 Quantity purchased: {qty:,.0f} units\n"
                                if last_purchase:
                                    text += f"   🕒 Last purchase: {last_purchase[:10]}\n"
                                if reason:
                                    text += f"   💡 {reason}\n"
                                text += "\n"
                        
                        if language == "sw":
                            text += "\n💡 **Vitendo:**\n"
                            text += "• Uliza 'nionyeshe maelezo ya mteja' kwa maelezo zaidi\n"
                            text += "• Uliza 'unda nukuu kwa wateja hawa' kutengeneza nukuu\n"
                            text += "• Uliza 'nionyeshe oda za wateja hawa' kuona historia ya ununuzi"
                        else:
                            text += "\n💡 **Next Steps:**\n"
                            text += "• Ask 'show customer details' for more information\n"
                            text += "• Ask 'create quotation for these customers' to generate quotes\n"
                            text += "• Ask 'show orders for these customers' to see purchase history"
                        
                        result = {"message": text, "data": customers}
                        
                        # Cache the result
                        self.cache.set("FIND_CUSTOMERS_BY_ITEM", {"item_name": item_name, "quantity": quantity}, "", result)
        
        # Existing RECOMMEND_CUSTOMERS intent
        elif intent == "RECOMMEND_CUSTOMERS":
            if item_name:
                items = self.api.get_items(search=item_name, limit=1)
                recommended = self.recommender.get_customers_for_item(item_code=items[0].get("ItemCode"), limit=quantity) if items else self.recommender.get_recommended_customers(limit=quantity)
            elif customer_name:
                customer, _ = self._resolve_customer(customer_name)
                recommended = self.recommender.get_similar_customers(customer_code=customer.get("CardCode"), limit=quantity) if customer else self.recommender.get_recommended_customers(limit=quantity)
            else:
                recommended = self.recommender.get_recommended_customers(limit=quantity)
            if not recommended:
                result = {"message": "No customer recommendations available.", "data": []}
            else:
                if language == "sw":
                    text = f"👥 **Wateja {len(recommended)} walio pendekezwa:**\n\n"
                else:
                    text = f"👥 **Top {len(recommended)} recommended customers:**\n\n"
                for i, cust in enumerate(recommended, 1):
                    text += f"{i}. **{cust.get('CardName')}** (Code: {cust.get('CardCode')})\n"
                result = {"message": text, "data": recommended}

        elif intent == "GET_CROSS_SELL":
            if not item_name:
                result = self._missing("an item name", language)
            else:
                suggestions = self.recommender.get_cross_sell_suggestions(item_name, limit=quantity or 5)
                result = {"item_name": item_name, "recommendations": suggestions or [], "count": len(suggestions or [])}

        elif intent == "GET_UPSELL":
            if not item_name:
                result = self._missing("an item name", language)
            else:
                suggestions = self.recommender.get_upsell_suggestions(item_name, limit=quantity or 3)
                result = {"item_name": item_name, "recommendations": suggestions or [], "count": len(suggestions or [])}

        elif intent == "GET_SEASONAL_RECOMMENDATIONS":
            month = next((m for m in ["january","february","march","april","may","june","july","august","september","october","november","december"] if m in message.lower()), None)
            suggestions = self.recommender.get_seasonal_recommendations(month=month, limit=quantity or 5)
            result = {"month": month or datetime.now().strftime("%B").lower(), "recommendations": suggestions or [], "count": len(suggestions or [])}

        elif intent == "GET_TRENDING_PRODUCTS":
            days = 30
            m = re.search(r'(\d+)\s+days', message.lower())
            if m:
                days = int(m.group(1))
            suggestions = self.recommender.get_trending_products(days=days, limit=quantity or 5)
            result = {"days": days, "recommendations": suggestions or [], "count": len(suggestions or [])}

        elif intent == "RECOMMEND_ITEMS":
            if item_name:
                items = self.api.get_items(search=item_name, limit=1)
                recommended = self.recommender.get_related_items(items[0].get("ItemCode"), limit=quantity) if items else self.recommender.get_recommended_items(limit=quantity)
            elif customer_name:
                customer, _ = self._resolve_customer(customer_name)
                recommended = self.recommender.get_items_for_customer(customer_code=customer.get("CardCode"), limit=quantity) if customer else self.recommender.get_recommended_items(limit=quantity)
            else:
                recommended = self.recommender.get_recommended_items(limit=quantity)
            if not recommended:
                result = {"message": "No recommendations available.", "data": []}
            else:
                text = f"🎯 **Top {len(recommended)} recommended items:**\n\n"
                for i, itm in enumerate(recommended, 1):
                    text += f"{i}. **{itm.get('ItemName')}** ({itm.get('ItemCode')})\n"
                result = {"message": text, "data": recommended}

        # =========================================================
        # KNOWLEDGE BASE
        # =========================================================
        elif intent == "COMPANY_INFO":
            info = kb.get_company_info()
            text = f"🏢 **{info['name']}** - {info['tagline']}\n\n{info['about'].strip()}\n\n**Our Values:**\n"
            for value in info['values']:
                text += f"• {value}\n"
            result = {"message": text, "data": []}

        elif intent == "PRODUCT_INFO":
            brands = kb.get_brand_info()
            text = "🌾 **Leysco 100 Product Brands**\n\n"
            for brand_key, brand in brands.items():
                text += f"**{brand['name']}** - {brand['category']}\n{brand['description'].strip()[:200]}...\n\n"
            result = {"message": text, "data": []}

        elif intent == "HOW_TO_ORDER":
            ordering = kb.get_ordering_info()
            text = ordering['how_to_order'].strip() + "\n\n**Payment Terms:**\n"
            for key, value in ordering['payment_terms'].items():
                text += f"• {key.replace('_', ' ').title()}: {', '.join(value) if isinstance(value, list) else value}\n"
            text += "\n" + ordering['delivery'].strip()
            result = {"message": text, "data": []}

        elif intent == "PAYMENT_METHODS":
            ordering = kb.get_ordering_info()
            text = "💳 **Payment Methods**\n\n"
            for method in ordering['payment_terms'].get('available_methods', []):
                text += f"• {method}\n"
            result = {"message": text, "data": []}

        elif intent == "CONTACT_INFO":
            contact = kb.get_contact_info()
            text = "📞 **Contact Leysco 100**\n\n**Customer Support:**\n"
            for key, value in contact['customer_support'].items():
                text += f"• {key.replace('_', ' ').title()}: {value}\n"
            text += "\n**Sales Regions:**\n"
            for region in contact['sales_regions']:
                text += f"• {region['name']}: {region['contact']}\n"
            result = {"message": text, "data": []}

        elif intent == "POLICY_QUESTION":
            policies = kb.get_policies()
            text = "📋 **Leysco 100 Policies**\n\n" + policies['returns'].strip() + "\n\n" + policies['quality_guarantee'].strip()
            result = {"message": text, "data": []}

        elif intent == "FAQ":
            user_msg = entities.get("item_name", "") or message
            faq_answer = kb.get_faq_answer(user_msg)
            if faq_answer:
                result = {"message": f"❓ **FAQ:** {faq_answer}", "data": []}

        # =========================================================
        # CUSTOMER HEALTH
        # =========================================================
        elif intent == "GET_CUSTOMER_HEALTH":
            if not customer_name:
                result = self._missing("a customer name", language)
            else:
                health = self.health.score(customer_name=customer_name)
                if health.get("error"):
                    result = {"message": health["error"], "data": []}
                else:
                    s, grade, emoji = health["score"], health["grade"], health["emoji"]
                    sig = health["signals"]
                    recs = health["recommendations"]
                    if language == "sw":
                        text = f"💚 **Afya ya Mteja: {health['customer_name']}**\n\n"
                        text += f"{emoji} **Alama: {s:.0f}/100** — {grade}\n\n📊 **Maelezo ya Ishara:**\n"
                        text += f"• Hivi karibuni: {sig['recency']['label']}\n• Mara kwa mara: {sig['frequency']['label']}\n"
                        text += f"• Ubadilishaji: {sig['conversion']['label']}\n• Fedha: {sig['financials']['label']}\n"
                    else:
                        text = f"💚 **Customer Health: {health['customer_name']}**\n\n"
                        text += f"{emoji} **Score: {s:.0f}/100** — {grade}\n\n📊 **Signal Breakdown:**\n"
                        text += f"• Recency:    {sig['recency']['label']}\n• Frequency:  {sig['frequency']['label']}\n"
                        text += f"• Conversion: {sig['conversion']['label']}\n• Financials: {sig['financials']['label']}\n"
                    if recs:
                        text += f"\n💡 **{'Mapendekezo' if language == 'sw' else 'Recommendations'}:**\n"
                        for r in recs:
                            text += f"• {r}\n"
                    result = {"message": text, "data": [health]}

        # =========================================================
        # QUOTATION FOLLOW-UP
        # =========================================================
        elif intent == "FOLLOW_UP_QUOTATIONS":
            summary = self.quotation_intelligence.get_follow_up_summary()
            stale = summary["stale_quotations"]
            unconv = summary["unconverted_customers"]
            rate = summary["conversion_rate"]
            stats = summary["summary"]

            if language == "sw":
                text = "📋 **Uchambuzi wa Kufuatilia Nukuu**\n\n"
                if stale:
                    text += f"⏰ **Nukuu za Zamani** ({stats['stale_count']} nukuu):\n"
                    for q in stale[:5]:
                        icon = "🔴" if q["urgency"] == "HIGH" else "🟡" if q["urgency"] == "MEDIUM" else "🟢"
                        text += f"{icon} {q['label']}\n"
                    text += "\n"
                if unconv:
                    text += f"👥 **Wateja Wasiojibu** ({stats['unconverted_count']} wateja):\n"
                    for c in unconv[:5]:
                        text += f"• {c['label']}\n"
                    text += "\n"
                text += f"📊 **Kiwango cha Ubadilishaji:** {rate['conversion_rate']}% ({rate['converted']}/{rate['total_quotes']} kwa siku {rate['period_days']} zilizopita)\n"
                if stats["total_value_at_risk"] > 0:
                    text += f"⚠️ **Thamani Inayoweza Kupotea:** KES {stats['total_value_at_risk']:,.0f}\n"
            else:
                text = "📋 **Quotation Follow-Up Intelligence**\n\n"
                if stale:
                    text += f"⏰ **Stale Quotations** ({stats['stale_count']} quotes):\n"
                    for q in stale[:5]:
                        icon = "🔴" if q["urgency"] == "HIGH" else "🟡" if q["urgency"] == "MEDIUM" else "🟢"
                        text += f"{icon} {q['label']}\n"
                    text += "\n"
                if unconv:
                    text += f"👥 **Unconverted Customers** ({stats['unconverted_count']} customers):\n"
                    for c in unconv[:5]:
                        text += f"• {c['label']}\n"
                    text += "\n"
                text += f"📊 **Conversion Rate:** {rate['conversion_rate']}% ({rate['converted']}/{rate['total_quotes']} over last {rate['period_days']} days)\n"
                if stats["total_value_at_risk"] > 0:
                    text += f"⚠️ **Value at Risk:** KES {stats['total_value_at_risk']:,.0f}\n"
                if not stale and not unconv:
                    text += "✅ All quotations are active. No immediate follow-up needed.\n"

            result = {"message": text, "data": [summary]}

        # =========================================================
        # CLARIFY (when intent not recognized)
        # =========================================================
        elif intent == "CLARIFY":
            if language == "sw":
                alternatives = [
                    "Bei ya bidhaa gani?",
                    "Angalia hisa ya bidhaa gani?",
                    "Unda nukuu kwa mteja gani?",
                    "Onyesha oda za mteja gani?",
                    "Bidhaa zinazouzwa sana?",
                    "Bidhaa zinazotembea polepole?"
                ]
                text = "Samahani, sikuelewa vizuri. Je, ulimaanisha:\n\n"
                for i, alt in enumerate(alternatives[:5], 1):
                    text += f"{i}. {alt}\n"
                text += "\nAu unaweza kuuliza kwa njia tofauti."
            else:
                alternatives = [
                    "Price of which item?",
                    "Check stock for which item?",
                    "Create quotation for which customer?",
                    "Show orders for which customer?",
                    "Top selling items?",
                    "Slow moving items?"
                ]
                text = "Sorry, I didn't quite understand. Did you mean:\n\n"
                for i, alt in enumerate(alternatives[:5], 1):
                    text += f"{i}. {alt}\n"
                text += "\nOr you can rephrase your question."
            
            result = {"message": text, "data": []}

        # =========================================================
        # FALLBACK
        # =========================================================
        else:
            logger.warning(f"Intent '{intent}' not recognized")
            result = {"error": f"Kusudi '{intent}' bado halitumiki" if language == "sw" else f"Intent '{intent}' not supported yet"}

        # =========================================================
        # CONVERSATION ENHANCER
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

    # =========================================================
    # CACHE MANAGEMENT
    # =========================================================
    
    def clear_cache(self):
        """Clear all caches in the action router."""
        self._customer_resolution_cache.clear()
        logger.info("ActionRouter cache cleared")