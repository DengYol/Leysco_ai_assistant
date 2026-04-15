"""
app/ai_engine/response_formatter.py
====================================
Converts raw system responses into natural, conversational text
AND preserves structured list data for the mobile app UI.

Enhanced with:
- Conversational openers and closers
- Natural language responses (non-robotic)
- Emojis for better UX
- Swahili/English bilingual support
- Caching for performance
"""

import logging
import asyncio
import hashlib
import random
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from functools import lru_cache, wraps

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


def cache_formatted(ttl_seconds: int = 300):
    """
    Decorator to cache formatted responses.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            cache = get_cache_service()
            
            # Generate cache key from function name and arguments
            cache_str = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            cache_key = hashlib.md5(cache_str.encode()).hexdigest()
            
            # Check cache
            cached = cache.get_simple(cache_key)
            if cached is not None:
                logger.info(f"⚡ Formatter cache hit: {func.__name__}")
                return cached
            
            # Execute function
            result = func(self, *args, **kwargs)
            
            # Cache result
            if result:
                cache.set_simple(cache_key, result, ttl=ttl_seconds)
            
            return result
        return wrapper
    return decorator


class ResponseFormatter:
    """
    Converts raw system responses into natural, conversational text
    AND preserves structured list data for the mobile app UI.
    """

    MAX_RESULTS = 5
    MAX_CUSTOMERS_DISPLAY = 10
    
    # Conversational openers for different intent types
    OPENERS = {
        "GET_ITEM_PRICE": {
            "en": [
                "Sure! Let me check the price for you... 🔍",
                "Here's what I found:",
                "I've looked up the price:",
                "You're asking about",
                "Let me get that information for you:",
                "One moment while I fetch the price... 💰",
                "Got it! Here's the pricing info:"
            ],
            "sw": [
                "Sawa! Naangalia bei kwa ajili yako... 🔍",
                "Hiki ndio nilichopata:",
                "Nimeangalia bei:",
                "Unauliza kuhusu",
                "Nakupa taarifa hiyo:",
                "Subiri kidogo nitaangalia bei... 💰"
            ]
        },
        "GET_TOP_SELLING_ITEMS": {
            "en": [
                "Here are our hottest selling items right now! 🔥",
                "Customers are loving these products:",
                "Based on recent sales, these are the top performers:",
                "Here's what's flying off the shelves: 📦",
                "The crowd favorites at the moment:",
                "These are the bestsellers this period:"
            ],
            "sw": [
                "Hizi ndizo bidhaa zinazouzwa sana kwa sasa! 🔥",
                "Wateja wanapenda bidhaa hizi:",
                "Kulingana na mauzo ya hivi karibuni, hizi ndizo zinazoongoza:",
                "Hivi ndivyo vinavyouzwa kwa kasi: 📦",
                "Bidhaa zinazopendwa na wengi kwa sasa:"
            ]
        },
        "GET_SLOW_MOVING_ITEMS": {
            "en": [
                "Here are some items that need a bit of attention: 👀",
                "These products could use some marketing love:",
                "Based on turnover rates, consider promoting these:",
                "Here's what's been sitting longer than usual:",
                "These items might benefit from a discount or bundle: 💡"
            ],
            "sw": [
                "Hizi ni bidhaa zinazohitaji uangalizi kidogo: 👀",
                "Bidhaa hizi zinahitaji uuzaji zaidi:",
                "Kulingana na kasi ya mauzo, zingatia kuzitangaza hizi:",
                "Hivi ndivyo vimekaa muda mrefu kuliko kawaida:",
                "Bidhaa hizi zinaweza kufaidika na punguzo au kifurushi: 💡"
            ]
        },
        "GET_CUSTOMER_ORDERS": {
            "en": [
                "Here's what they've been ordering: 📋",
                "Looking at their purchase history:",
                "Here are the orders I found:",
                "Based on their records:",
                "Here's their order summary:"
            ],
            "sw": [
                "Hiki ndicho walichokuwa wakiagiza: 📋",
                "Kuangalia historia yao ya ununuzi:",
                "Hizi ndizo oda nilizopata:",
                "Kulingana na rekodi zao:",
                "Huu ni muhtasari wa oda zao:"
            ]
        },
        "GET_CUSTOMER_DETAILS": {
            "en": [
                "Here's what I know about this customer: 👤",
                "Let me pull up their profile:",
                "Here are the customer details:",
                "Based on our records:",
                "Here's their information:"
            ],
            "sw": [
                "Hiki ndicho ninachojua kuhusu mteja huyu: 👤",
                "Nachukua profile yao:",
                "Hizi ndizo taarifa za mteja:",
                "Kulingana na rekodi zetu:",
                "Hizi ndizo taarifa zao:"
            ]
        },
        "GET_WAREHOUSES": {
            "en": [
                "Here are our warehouse locations: 🏭",
                "These are the active warehouses:",
                "Here's where we store our products:",
                "Check out our warehouse list:"
            ],
            "sw": [
                "Hizi ni maeneo ya maghala yetu: 🏭",
                "Haya ni maghala yanayotumika:",
                "Hapa ndipo tunapohifadhi bidhaa zetu:",
                "Angalia orodha ya ghala zetu:"
            ]
        },
        "GET_LOW_STOCK_ALERTS": {
            "en": [
                "⚠️ Attention! Here are items running low on stock:",
                "Heads up! These products need reordering soon:",
                "🚨 Low stock alert! Check these items:",
                "Better reorder these soon:",
                "📦 Running low! Take a look at these:"
            ],
            "sw": [
                "⚠️ Tahadhari! Hizi ndizo bidhaa zenye hisa chache:",
                "Taarifa! Bidhaa hizi zinahitaji kuagizwa upya hivi karibuni:",
                "🚨 Tahadhari ya hisa chache! Angalia bidhaa hizi:",
                "Ni bora kuagiza hizi tena hivi karibuni:",
                "📦 Hisa inaisha! Angalia hizi:"
            ]
        },
        "CREATE_QUOTATION": {
            "en": [
                "✅ Quotation created successfully! Here's the summary:",
                "Great news! I've prepared the quotation for you:",
                "Your quotation is ready! 📄 Here are the details:",
                "Done! Here's the quotation summary:"
            ],
            "sw": [
                "✅ Nukuu imeundwa kikamilifu! Huu ni muhtasari:",
                "Habari njema! Nimekuandalia nukuu:",
                "Nukuu yako iko tayari! 📄 Haya ni maelezo:",
                "Imekamilika! Huu ni muhtasari wa nukuu:"
            ]
        }
    }
    
    # Friendly closers
    CLOSERS = {
        "en": [
            "\n\n💡 Need anything else? I'm here to help! 😊",
            "\n\n✨ Is there anything else you'd like to know?",
            "\n\n👍 Let me know if you need more information!",
            "\n\n💬 What else can I assist you with today?",
            "\n\n📦 Feel free to ask about prices, stock, or customers!",
            "\n\n🎯 Want me to check something specific? Just ask!",
            "\n\n🤝 Happy to help with anything else!"
        ],
        "sw": [
            "\n\n💡 Unahitaji kitu kingine? Niko hapa kusaidia! 😊",
            "\n\n✨ Kuna chochote kingine ungependa kujua?",
            "\n\n👍 Nijulishe kama unahitaji maelezo zaidi!",
            "\n\n💬 Nini kingine ninachoweza kukusaidia nalo leo?",
            "\n\n📦 Uliza kuhusu bei, hisa, au wateja!",
            "\n\n🎯 Unataka nitaangalie kitu maalum? Uliza tu!",
            "\n\n🤝 Nimefurahi kusaidia na chochote kingine!"
        ]
    }
    
    # No results messages (conversational)
    NO_RESULTS = {
        "GET_ITEM_PRICE": {
            "en": "Hmm, I couldn't find any price information for that item. 🤔\n\n💡 Try:\n• Checking the spelling (e.g., 'vegimax' not 'vegimx')\n• Asking for a different product\n• Saying 'show me items' to browse our catalog",
            "sw": "Hmm, sikuweza kupata taarifa za bei kwa bidhaa hiyo. 🤔\n\n💡 Jaribu:\n• Angalia tahajia (mfano, 'vegimax' si 'vegimx')\n• Uliza kuhusu bidhaa nyingine\n• Sema 'nionyeshe bidhaa' kuona orodha yetu"
        },
        "GET_TOP_SELLING_ITEMS": {
            "en": "I don't have enough sales data yet to show top selling items. 📊\n\n💡 Try:\n• Asking for a different time period\n• Checking back later when there's more data\n• Asking about specific products instead",
            "sw": "Sina data ya kutosha ya mauzo bado kuonyesha bidhaa zinazouzwa sana. 📊\n\n💡 Jaribu:\n• Uliza kwa kipindi kingine\n• Angalia tena baadaye kutakuwa na data zaidi\n• Uliza kuhusu bidhaa maalum badala yake"
        },
        "GET_SLOW_MOVING_ITEMS": {
            "en": "Great news! No slow moving items found - your inventory is moving well! 🎉\n\nEverything seems to be selling at a healthy pace. Keep up the good work! 💪",
            "sw": "Habari njema! Hakuna bidhaa zinazotembea polepole - hisa zako zinasonga vizuri! 🎉\n\nKila kitu kinaonekana kinauzwa kwa kasi nzuri. Endelea na kazi nzuri! 💪"
        },
        "GET_CUSTOMER_ORDERS": {
            "en": "I couldn't find any orders for this customer. 📋\n\n💡 Would you like to:\n• Create a quotation for them?\n• Check customer details instead?\n• Search for a different customer?",
            "sw": "Sikuweza kupata oda zozote kwa mteja huyu. 📋\n\n💡 Je, ungependa:\n• Kuunda nukuu kwa ajili yao?\n• Angalia maelezo ya mteja badala yake?\n• Tafuta mteja mwingine?"
        }
    }
    
    # Helpful tips after responses
    TIPS = {
        "GET_ITEM_PRICE": {
            "en": "\n\n💡 Tip: Ask 'price for [customer name]' to see customer-specific pricing!",
            "sw": "\n\n💡 Kidokezo: Uliza 'bei kwa [jina la mteja]' kuona bei maalum kwa mteja!"
        },
        "GET_TOP_SELLING_ITEMS": {
            "en": "\n\n💡 Tip: Want to check stock? Ask 'check stock for [item name]'",
            "sw": "\n\n💡 Kidokezo: Unataka kuangalia hisa? Uliza 'angalia hisa za [jina la bidhaa]'"
        },
        "GET_SLOW_MOVING_ITEMS": {
            "en": "\n\n💡 Tip: Consider running promotions or bundling slow movers with popular items!",
            "sw": "\n\n💡 Kidokezo: Fikiria kufanya promo au kufungasha bidhaa zinazotembea polepole na zinazouzwa sana!"
        }
    }

    # -------------------------------------------------
    @staticmethod
    def _extract_list(data):
        if isinstance(data, dict):
            if "error" in data:
                return "error", data["error"]

            response = data.get("ResponseData")

            if isinstance(response, list):
                return "list", response

            if isinstance(response, dict) and "data" in response:
                return "list", response["data"]

            return "list", []

        if isinstance(data, list):
            return "list", data

        return "error", "Invalid data format"

    # -------------------------------------------------
    @staticmethod
    def _format_price(value):
        try:
            return f"{float(value):,.2f}"
        except Exception:
            return value or "0.00"

    # -------------------------------------------------
    @staticmethod
    def _format_date(date_str: Optional[str]) -> str:
        """Format date string to readable format."""
        if not date_str:
            return "N/A"
        try:
            if isinstance(date_str, str):
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                return dt.strftime("%b %d, %Y")
            return str(date_str)
        except Exception:
            return str(date_str)[:10]

    # -------------------------------------------------
    @staticmethod
    def _not_available(msg="That information is not available in Leysco right now."):
        return {"message": msg, "data": []}
    
    # -------------------------------------------------
    @staticmethod
    def _get_opener(intent: str, language: str = "en") -> str:
        """Get a random conversational opener for the intent."""
        openers = ResponseFormatter.OPENERS.get(intent, {}).get(language, [])
        if openers:
            return random.choice(openers)
        return "" if language == "en" else "Sawa, nikupe taarifa:"
    
    @staticmethod
    def _get_closer(language: str = "en") -> str:
        """Get a random friendly closer."""
        return random.choice(ResponseFormatter.CLOSERS.get(language, ResponseFormatter.CLOSERS["en"]))
    
    @staticmethod
    def _get_no_results_message(intent: str, language: str = "en") -> str:
        """Get conversational no-results message."""
        return ResponseFormatter.NO_RESULTS.get(intent, {}).get(
            language, 
            "I couldn't find what you're looking for. Try rephrasing your question! 🤔"
        )
    
    @staticmethod
    def _get_tip(intent: str, language: str = "en") -> str:
        """Get a helpful tip for the intent."""
        return ResponseFormatter.TIPS.get(intent, {}).get(language, "")

    # =================================================
    # ENHANCED: CUSTOMER SEGMENTATION FORMATTER
    # =================================================
    @staticmethod
    @cache_formatted(ttl_seconds=300)
    def format_customer_segmentation(data: Dict[str, Any], language: str = "en") -> dict:
        """
        Format customer segmentation results (FIND_CUSTOMERS_BY_ITEM).
        """
        customers = data.get("customers", [])
        item_name = data.get("item_name", "this product")
        summary = data.get("summary", {})
        recommendations = data.get("recommendations", [])
        
        if not customers:
            msg = ResponseFormatter._get_no_results_message("FIND_CUSTOMERS_BY_ITEM", language)
            if "item_name" in msg:
                msg = msg.replace("[item_name]", item_name)
            return {"message": msg, "data": []}
        
        # Get conversational opener
        opener = ResponseFormatter._get_opener("FIND_CUSTOMERS_BY_ITEM", language)
        
        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"🎯 **Wateja Wanaonunua {item_name}**")
            lines.append(f"📊 Nimepata wateja {len(customers)}:")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"🎯 **Customers Who Buy {item_name}**")
            lines.append(f"📊 Found {len(customers)} customers:")
            lines.append("")
        
        # Display top customers with details
        for i, cust in enumerate(customers[:ResponseFormatter.MAX_CUSTOMERS_DISPLAY], 1):
            cust_name = cust.get("CardName", "Unknown")
            cust_code = cust.get("CardCode", "N/A")
            qty = cust.get("PurchaseQuantity", 0)
            last_purchase = cust.get("LastPurchaseDate", "")
            reason = cust.get("RecommendationReason", "")
            
            if language == "sw":
                lines.append(f"{i}. **{cust_name}** (Msimbo: {cust_code})")
                if qty > 0:
                    lines.append(f"   📦 Kiasi: {qty:,.0f} vitengo")
                if last_purchase:
                    lines.append(f"   🕒 Alinunua mwisho: {ResponseFormatter._format_date(last_purchase)}")
                if reason:
                    lines.append(f"   💡 {reason}")
                lines.append("")
            else:
                lines.append(f"{i}. **{cust_name}** (Code: {cust_code})")
                if qty > 0:
                    lines.append(f"   📦 Quantity purchased: {qty:,.0f} units")
                if last_purchase:
                    lines.append(f"   🕒 Last purchased: {ResponseFormatter._format_date(last_purchase)}")
                if reason:
                    lines.append(f"   💡 {reason}")
                lines.append("")
        
        # Add summary if there are more customers
        total_customers = len(customers)
        if total_customers > ResponseFormatter.MAX_CUSTOMERS_DISPLAY:
            if language == "sw":
                lines.append(f"... na {total_customers - ResponseFormatter.MAX_CUSTOMERS_DISPLAY} wateja wengine.")
            else:
                lines.append(f"... and {total_customers - ResponseFormatter.MAX_CUSTOMERS_DISPLAY} more customers.")
            lines.append("")
        
        # Add recommendations
        if recommendations:
            if language == "sw":
                lines.append("💡 **Mapendekezo:**")
            else:
                lines.append("💡 **Recommendations:**")
            for rec in recommendations[:3]:
                lines.append(f"• {rec}")
            lines.append("")
        
        # Add follow-up suggestions
        if language == "sw":
            lines.append("💡 **Vitendo:**")
            lines.append("• Uliza 'nionyeshe maelezo ya mteja' kwa maelezo zaidi")
            lines.append("• Uliza 'unda nukuu kwa wateja hawa' kutengeneza nukuu")
            lines.append("• Uliza 'nionyeshe oda za wateja hawa' kuona historia ya ununuzi")
        else:
            lines.append("💡 **Next Steps:**")
            lines.append("• Ask 'show customer details' for more information")
            lines.append("• Ask 'create quotation for these customers' to generate quotes")
            lines.append("• Ask 'show orders for these customers' to see purchase history")
        
        # Add friendly closer
        lines.append(ResponseFormatter._get_closer(language))
        
        return {
            "message": "\n".join(lines),
            "data": customers
        }

    # =================================================
    # 🔥 FIX FOR SERVER CRASH (alias method added)
    # =================================================
    @staticmethod
    def format_prices(data: dict) -> dict:
        """Alias to prevent crash from old router call"""
        return ResponseFormatter.format_item_price(data)

    # =================================================
    # ENHANCED: ITEM PRICE FORMATTER
    # =================================================
    @staticmethod
    @cache_formatted(ttl_seconds=300)
    def format_item_price(data: dict, language: str = "en") -> dict:
        if not data or "item" not in data:
            return ResponseFormatter._not_available(
                ResponseFormatter._get_no_results_message("GET_ITEM_PRICE", language)
            )

        item = data.get("item", {})
        prices = data.get("prices", [])
        uom = data.get("uom", "Unit")

        item_name = item.get("ItemName") or item.get("full_name") or "Unknown Item"
        item_code = item.get("ItemCode", "")

        if not prices:
            msg = f"Hmm, I found {item_name} ({item_code}) but no price is configured for it yet. 🤔\n\n💡 Try asking for a different product or contact sales for pricing!"
            if language == "sw":
                msg = f"Hmm, nimeipata {item_name} ({item_code}) lakini bei yake haijasanidiwa bado. 🤔\n\n💡 Jaribu kuuliza kuhusu bidhaa nyingine au wasiliana na mauzo kwa bei!"
            return {"message": msg, "data": []}

        # Get conversational opener
        opener = ResponseFormatter._get_opener("GET_ITEM_PRICE", language)
        
        lines = []
        if opener:
            lines.append(opener)
            lines.append("")
        
        if language == "sw":
            lines.append(f"💰 **Bei za {item_name}**")
            lines.append(f"   (Msimbo: {item_code})\n")
        else:
            lines.append(f"💰 **Prices for {item_name}**")
            lines.append(f"   (Code: {item_code})\n")

        structured = []

        for p in prices[:ResponseFormatter.MAX_RESULTS]:
            list_name = p.get("ListName", "Price List")
            price = ResponseFormatter._format_price(p.get("Price"))
            currency = p.get("Currency", "KES")

            if language == "sw":
                lines.append(f"• **{list_name}**: {price} {currency} kwa {uom}")
            else:
                lines.append(f"• **{list_name}**: {price} {currency} per {uom}")

            structured.append({
                "price_list": list_name,
                "price": price,
                "currency": currency,
                "uom": uom
            })
        
        # Add tip
        lines.append(ResponseFormatter._get_tip("GET_ITEM_PRICE", language))
        
        # Add friendly closer
        lines.append(ResponseFormatter._get_closer(language))

        return {
            "message": "\n".join(lines),
            "data": structured
        }
    
    # =================================================
    # ENHANCED: TOP SELLING ITEMS FORMATTER
    # =================================================
    @staticmethod
    def format_top_selling_items(items: list, limit: int = 10, days: int = 30, language: str = "en") -> dict:
        """Format top selling items with conversational flair."""
        if not items:
            return ResponseFormatter._not_available(
                ResponseFormatter._get_no_results_message("GET_TOP_SELLING_ITEMS", language)
            )
        
        opener = ResponseFormatter._get_opener("GET_TOP_SELLING_ITEMS", language)
        
        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📊 **Bidhaa {min(limit, len(items))} Zinazouzwa Sana** (Siku {days} zilizopita)")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📊 **Top {min(limit, len(items))} Selling Items** (Last {days} days)")
            lines.append("")
        
        for i, item in enumerate(items[:limit], 1):
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
            
            lines.append(f"{i}. {emoji} **{name}**")
            if score > 0:
                if language == "sw":
                    lines.append(f"   📊 Alama ya Umaarufu: {score:.1f}/100")
                else:
                    lines.append(f"   📊 Popularity Score: {score:.1f}/100")
            lines.append("")
        
        # Add tip
        lines.append(ResponseFormatter._get_tip("GET_TOP_SELLING_ITEMS", language))
        
        # Add friendly closer
        lines.append(ResponseFormatter._get_closer(language))
        
        return {"message": "\n".join(lines), "data": items}
    
    # =================================================
    # ENHANCED: SLOW MOVING ITEMS FORMATTER
    # =================================================
    @staticmethod
    def format_slow_moving_items(items: list, limit: int = 10, days: int = 90, language: str = "en") -> dict:
        """Format slow moving items with conversational recommendations."""
        if not items:
            return ResponseFormatter._not_available(
                ResponseFormatter._get_no_results_message("GET_SLOW_MOVING_ITEMS", language)
            )
        
        opener = ResponseFormatter._get_opener("GET_SLOW_MOVING_ITEMS", language)
        
        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📊 **Bidhaa {len(items)} Zinazotembea Polepole** (Siku {days} zilizopita)")
            lines.append("")
            lines.append("⚠️ **Bidhaa hizi zinahitaji uangalizi:**")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📊 **Top {len(items)} Slow Moving Items** (Last {days} days)")
            lines.append("")
            lines.append("⚠️ **These items need attention:**")
            lines.append("")
        
        for i, item in enumerate(items[:limit], 1):
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
            
            lines.append(f"{i}. {emoji} **{name}**")
            if language == "sw":
                lines.append(f"   📊 Kiwango cha Mzunguko: {turnover:.2f}")
            else:
                lines.append(f"   📊 Turnover Rate: {turnover:.2f}")
            if recommendation:
                lines.append(f"   💡 {recommendation}")
            lines.append("")
        
        # Add tip
        lines.append(ResponseFormatter._get_tip("GET_SLOW_MOVING_ITEMS", language))
        
        # Add friendly closer
        lines.append(ResponseFormatter._get_closer(language))
        
        return {"message": "\n".join(lines), "data": items}

    # =================================================
    # QUOTATION CREATION SUCCESS FORMATTER (FIXED - USING @classmethod)
    # =================================================
    @classmethod
    @cache_formatted(ttl_seconds=60)
    def format_quotation_creation_success(
        cls,
        customer_name: str,
        items: list,
        total_amount: float,
        valid_until: str,
        doc_num: str = None,
        language: str = "en"
    ) -> dict:
        """
        Format a successful quotation creation response with conversational flair.
        FIXED: Uses @classmethod to support both instance and class calls.
        """
        opener = cls._get_opener("CREATE_QUOTATION", language)
        
        # Format valid_until date if it's a full timestamp
        if valid_until and len(valid_until) > 10:
            try:
                valid_until = valid_until[:10]
            except:
                pass
        
        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            
            lines.append("📄 **Muhtasari wa Nukuu**")
            lines.append("")
            lines.append("**Bidhaa:**")
            
            for item in items:
                item_name = item.get("ItemName", item.get("name", "Unknown"))
                quantity = item.get("Quantity", item.get("quantity", 1))
                price = item.get("Price", item.get("price", 0))
                line_total = quantity * price
                lines.append(f"• {item_name} ({quantity} vitengo) @ KES {price:,.2f} = KES {line_total:,.2f}")
            
            lines.append("")
            lines.append(f"👤 **Mteja:** {customer_name}")
            lines.append(f"💰 **Jumla:** KES {total_amount:,.2f}")
            lines.append(f"📅 **Inaisha:** {valid_until}")
            
            if doc_num:
                lines.append(f"🔢 **Nambari ya Nukuu:** {doc_num}")
            
            lines.append("")
            lines.append("💡 **Kidokezo:** Unaweza kuuliza 'nionyeshe nukuu za mteja huyu' kuona historia.")
            
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            
            lines.append("📄 **Quotation Summary**")
            lines.append("")
            lines.append("**Items:**")
            
            for item in items:
                item_name = item.get("ItemName", item.get("name", "Unknown"))
                quantity = item.get("Quantity", item.get("quantity", 1))
                price = item.get("Price", item.get("price", 0))
                line_total = quantity * price
                lines.append(f"• {item_name} ({quantity} units) @ KES {price:,.2f} = KES {line_total:,.2f}")
            
            lines.append("")
            lines.append(f"👤 **Customer:** {customer_name}")
            lines.append(f"💰 **Total:** KES {total_amount:,.2f}")
            lines.append(f"📅 **Valid until:** {valid_until}")
            
            if doc_num:
                lines.append(f"🔢 **Quotation Number:** {doc_num}")
            
            lines.append("")
            lines.append("💡 **Tip:** Ask 'show quotations for this customer' to see history.")
        
        # Add friendly closer
        lines.append(cls._get_closer(language))
        
        return {
            "message": "\n".join(lines),
            "data": [{
                "customer_name": customer_name,
                "items": items,
                "total_amount": total_amount,
                "valid_until": valid_until,
                "doc_num": doc_num,
                "success": True
            }]
        }

    # =================================================
    # QUOTATION CREATION ERROR FORMATTER
    # =================================================
    @staticmethod
    def format_quotation_creation_error(
        error_message: str,
        invalid_items: list = None,
        language: str = "en"
    ) -> dict:
        """
        Format a quotation creation error response.
        """
        if language == "sw":
            message = f"❌ Samahani, sikuweza kuunda nukuu:\n{error_message}"
            
            if invalid_items:
                message += "\n\n📦 **Bidhaa zilizorukwa:**"
                for item in invalid_items[:5]:
                    item_name = item.get("ItemName", item.get("name", "Unknown"))
                    reason = item.get("reason", "Sababu haijulikani")
                    message += f"\n• {item_name}: {reason}"
                
                if len(invalid_items) > 5:
                    message += f"\n... na {len(invalid_items) - 5} nyingine"
            
            message += "\n\n💡 **Jaribu:**\n• Angalia majina ya bidhaa\n• Hakikisha bidhaa zina bei\n• Uliza 'nionyeshe bidhaa' kuona orodha"
            
        else:
            message = f"❌ Sorry, I couldn't create the quotation:\n{error_message}"
            
            if invalid_items:
                message += "\n\n📦 **Skipped items:**"
                for item in invalid_items[:5]:
                    item_name = item.get("ItemName", item.get("name", "Unknown"))
                    reason = item.get("reason", "Unknown reason")
                    message += f"\n• {item_name}: {reason}"
                
                if len(invalid_items) > 5:
                    message += f"\n... and {len(invalid_items) - 5} more"
            
            message += "\n\n💡 **Try:**\n• Check item names\n• Ensure items have prices\n• Ask 'show me items' to browse"
        
        return {
            "message": message,
            "data": [{
                "error": error_message,
                "invalid_items": invalid_items,
                "success": False
            }]
        }

    # =================================================
    # ENHANCED: CUSTOMER ORDERS FORMATTER
    # =================================================
    @staticmethod
    def format_customer_orders(orders: list, customer_name: str, language: str = "en") -> dict:
        """Format customer orders conversationally."""
        if not orders:
            msg = ResponseFormatter._get_no_results_message("GET_CUSTOMER_ORDERS", language)
            msg = msg.replace("this customer", customer_name)
            return {"message": msg, "data": []}
        
        opener = ResponseFormatter._get_opener("GET_CUSTOMER_ORDERS", language)
        
        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📋 **Oda za {customer_name}**")
            lines.append(f"📊 Nimepata oda {len(orders)}:")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📋 **Orders for {customer_name}**")
            lines.append(f"📊 Found {len(orders)} orders:")
            lines.append("")
        
        total_value = 0
        for i, o in enumerate(orders[:10], 1):
            doc_num = o.get('DocNum', 'N/A')
            doc_date = ResponseFormatter._format_date(o.get('DocDate', ''))
            doc_total = float(o.get('DocTotal', 0))
            status = o.get('StatusText', o.get('DocStatus', 'Unknown'))
            total_value += doc_total
            
            lines.append(f"{i}. **Order #{doc_num}** ({doc_date})")
            lines.append(f"   💰 Amount: KES {doc_total:,.2f}")
            lines.append(f"   📍 Status: {status}")
            lines.append("")
        
        if len(orders) > 10:
            lines.append(f"... and {len(orders) - 10} more orders")
            lines.append("")
        
        lines.append(f"💰 **Total Value:** KES {total_value:,.2f}")
        
        # Add friendly closer
        lines.append(ResponseFormatter._get_closer(language))
        
        return {"message": "\n".join(lines), "data": orders}

    # -------------------------------------------------
    @staticmethod
    def format_customer(data, language: str = "en") -> dict:
        status, payload = ResponseFormatter._extract_list(data)

        if status == "error":
            return ResponseFormatter._not_available(payload)

        if not payload:
            return ResponseFormatter._not_available("I couldn't find that customer.")

        customers = payload[:ResponseFormatter.MAX_RESULTS]
        
        if language == "sw":
            lines = ["👥 **Wateja Wanaolingana:**\n"]
            for c in customers:
                if isinstance(c, dict):
                    lines.append(f"• **{c.get('CardName', 'N/A')}** (Msimbo: {c.get('CardCode', 'N/A')})")
        else:
            lines = ["👥 **Matching Customers:**\n"]
            for c in customers:
                if isinstance(c, dict):
                    lines.append(f"• **{c.get('CardName', 'N/A')}** (Code: {c.get('CardCode', 'N/A')})")
        
        lines.append("\n" + ResponseFormatter._get_closer(language))

        return {
            "message": "\n".join(lines),
            "data": customers
        }

    # -------------------------------------------------
    @staticmethod
    def format_stock(data: dict, language: str = "en") -> dict:
        if "error" in data or data.get("stock") is None:
            return ResponseFormatter._not_available()
        
        stock = data.get('stock')
        item_name = data.get('item_name')
        
        if stock <= 0:
            if language == "sw":
                msg = f"📦 **{item_name}** imeisha kwa sasa. 💡 Tafadhali wasiliana na timu ya mauzo kwa usaidizi."
            else:
                msg = f"📦 **{item_name}** is currently out of stock. 💡 Please contact the sales team for assistance."
        else:
            if language == "sw":
                msg = f"📦 **{item_name}** tuna vitengo **{stock:,.0f}** hisani. 💡 Unahitaji kuangalia bidhaa nyingine?"
            else:
                msg = f"📦 **{item_name}** we have **{stock:,.0f}** units in stock. 💡 Need to check another product?"
        
        msg += "\n" + ResponseFormatter._get_closer(language)
        
        return {
            "message": msg,
            "data": []
        }

    # -------------------------------------------------
    @staticmethod
    def format_list(title: str, data, language: str = "en") -> dict:
        status, payload = ResponseFormatter._extract_list(data)

        if status == "error":
            return ResponseFormatter._not_available(payload)

        if not payload:
            return ResponseFormatter._not_available(f"I couldn't find any {title}.")

        limited = payload[:ResponseFormatter.MAX_RESULTS]

        if title == "items":
            if language == "sw":
                lines = ["📦 **Bidhaa Zinazolingana:**\n"]
                for i in limited:
                    if isinstance(i, dict):
                        stock_info = f" - Hisa: {i.get('OnHand', 'N/A')}" if i.get('OnHand') else ""
                        lines.append(f"• **{i.get('ItemName', 'N/A')}** ({i.get('ItemCode', 'N/A')}){stock_info}")
            else:
                lines = ["📦 **Matching Items:**\n"]
                for i in limited:
                    if isinstance(i, dict):
                        stock_info = f" - Stock: {i.get('OnHand', 'N/A')}" if i.get('OnHand') else ""
                        lines.append(f"• **{i.get('ItemName', 'N/A')}** ({i.get('ItemCode', 'N/A')}){stock_info}")
            
            lines.append("\n" + ResponseFormatter._get_closer(language))
            return {"message": "\n".join(lines), "data": limited}

        if title == "customers":
            return ResponseFormatter.format_customer(data, language)

        return {"message": f"I found some {title}.", "data": limited}

    # -------------------------------------------------
    @staticmethod
    def format_sales_orders(data: list, language: str = "en") -> dict:
        if not data:
            return {"message": "No sales orders found.", "data": []}

        if language == "sw":
            lines = ["📋 **Oda za Mauzo Zilizopatikana:**\n"]
        else:
            lines = ["📋 **Sales Orders Found:**\n"]

        structured = []

        for idx, item in enumerate(data[:ResponseFormatter.MAX_RESULTS], 1):
            if isinstance(item, dict):
                name = item.get("name") or item.get("ItemName") or "N/A"
                warehouse = item.get("warehouse") or item.get("Warehouse") or "N/A"
            else:
                name = str(item)
                warehouse = "N/A"

            lines.append(f"{idx}. **{name}** (Ghala: {warehouse})" if language == "sw" else f"{idx}. **{name}** (Warehouse: {warehouse})")
            structured.append({"name": name, "warehouse": warehouse})

        lines.append("\n" + ResponseFormatter._get_closer(language))
        
        return {
            "message": "\n".join(lines),
            "data": structured
        }
    
    @staticmethod
    def format_customer_activity(summary: dict, engagement: str, language: str = "en") -> dict:
        """
        Formats customer activity when no orders are found.
        Shows engagement level and document counts.
        """
        invoices = summary.get("invoices", [])
        deliveries = summary.get("deliveries", [])
        quotations = summary.get("quotations", [])

        if language == "sw":
            message_lines = [
                "🔍 Hakuna oda za mauzo za hivi karibuni zilizopatikana.",
                "",
                f"📊 **Kiwango cha Ushirikiano:** {engagement}",
                "",
                "📈 **Muhtasari wa Shughuli za Mteja**",
                f"🧾 Ankara: {len(invoices)}",
                f"🚚 Usafirishaji: {len(deliveries)}",
                f"📝 Nukuu: {len(quotations)}",
                "",
                ResponseFormatter._get_closer(language)
            ]
        else:
            message_lines = [
                "🔍 No recent sales orders found.",
                "",
                f"📊 **Engagement Level:** {engagement}",
                "",
                "📈 **Customer Activity Summary**",
                f"🧾 Invoices: {len(invoices)}",
                f"🚚 Deliveries: {len(deliveries)}",
                f"📝 Quotations: {len(quotations)}",
                "",
                ResponseFormatter._get_closer(language)
            ]

        return {
            "message": "\n".join(message_lines),
            "data": summary
        }

    # -------------------------------------------------
    @staticmethod
    def format_recommended_items(data: list, language: str = "en") -> str:
        """Format recommended items for frontend or API response."""
        if not data:
            return "No item recommendations available."

        if language == "sw":
            text = f"🎯 **Bidhaa {min(len(data), ResponseFormatter.MAX_RESULTS)} Zilizopendekezwa:**\n"
        else:
            text = f"🎯 **Top {min(len(data), ResponseFormatter.MAX_RESULTS)} Recommended Items:**\n"
        
        for idx, item in enumerate(data[:ResponseFormatter.MAX_RESULTS], 1):
            if isinstance(item, dict):
                name = item.get("ItemName") or item.get("name") or "N/A"
                code = item.get("ItemCode") or item.get("code") or "N/A"
            else:
                name = str(item)
                code = "N/A"

            text += f"{idx}. **{name}** (Code: {code})\n"

        return text

    # -------------------------------------------------
    @staticmethod
    def format_recommended_customers(data: list, language: str = "en") -> str:
        """Format recommended customers for frontend or API response."""
        if not data:
            return "No customer recommendations available."

        if language == "sw":
            text = f"👥 **Wateja {min(len(data), ResponseFormatter.MAX_RESULTS)} Walio Pendekezwa:**\n"
        else:
            text = f"👥 **Top {min(len(data), ResponseFormatter.MAX_RESULTS)} Recommended Customers:**\n"
        
        for idx, cust in enumerate(data[:ResponseFormatter.MAX_RESULTS], 1):
            if isinstance(cust, dict):
                name = cust.get("CardName") or cust.get("name") or "N/A"
                code = cust.get("CardCode") or cust.get("code") or "N/A"
            else:
                name = str(cust)
                code = "N/A"

            text += f"{idx}. **{name}** (Code: {code})\n"

        return text

    @staticmethod
    def format_quotations(quotations, customer_name: str | None = None, language: str = "en") -> dict:
        """
        Formats quotation data into readable text.
        Optionally filters by customer.
        """
        if not quotations:
            return {"message": "No quotations found.", "data": []}

        if isinstance(quotations, str):
            return {"message": quotations, "data": []}

        if isinstance(quotations, dict):
            quotations = quotations.get("value") or quotations.get("data") or []

        if isinstance(quotations, list) and quotations and isinstance(quotations[0], str):
            return {"message": "\n".join(quotations), "data": quotations}

        if not quotations:
            return {"message": "No quotations found.", "data": []}

        if customer_name:
            quotations = [
                q for q in quotations
                if customer_name.lower() in str(q.get("CardName", "")).lower()
            ]

            if not quotations:
                msg = f"No quotations found for {customer_name}." if language == "en" else f"Hakuna nukuu zilizopatikana kwa {customer_name}."
                return {"message": msg, "data": []}

        if language == "sw":
            text = f"📄 **Nukuu ({len(quotations)} zilizopatikana):**\n\n"
        else:
            text = f"📄 **Quotations ({len(quotations)} found):**\n\n"
        
        grand_total = 0

        for i, q in enumerate(quotations[:ResponseFormatter.MAX_RESULTS], 1):
            total = float(q.get("DocTotal", 0))
            grand_total += total

            if language == "sw":
                text += (
                    f"{i}. **Nukuu #{q.get('DocNum', 'N/A')}**\n"
                    f"   📅 Tarehe: {ResponseFormatter._format_date(q.get('DocDate'))}\n"
                    f"   👤 Mteja: {q.get('CardName', 'N/A')}\n"
                    f"   💰 Jumla: KES {total:,.2f}\n"
                    f"   📍 Hali: {q.get('DocStatus', 'N/A')}\n\n"
                )
            else:
                text += (
                    f"{i}. **Quotation #{q.get('DocNum', 'N/A')}**\n"
                    f"   📅 Date: {ResponseFormatter._format_date(q.get('DocDate'))}\n"
                    f"   👤 Customer: {q.get('CardName', 'N/A')}\n"
                    f"   💰 Total: KES {total:,.2f}\n"
                    f"   📍 Status: {q.get('DocStatus', 'N/A')}\n\n"
                )

        if language == "sw":
            text += f"💰 **Jumla Kuu:** KES {grand_total:,.2f}"
        else:
            text += f"💰 **Grand Total:** KES {grand_total:,.2f}"
        
        text += "\n" + ResponseFormatter._get_closer(language)

        return {
            "message": text,
            "data": quotations
        }

    # =================================================
    # ENHANCED: CROSS-SELL FORMATTER
    # =================================================
    @staticmethod
    @cache_formatted(ttl_seconds=300)
    def format_cross_sell(data: dict, language: str = "en") -> dict:
        """
        Format cross-sell recommendations with conversational flair.
        """
        if not data or not isinstance(data, dict):
            return ResponseFormatter._not_available("I couldn't find any cross-sell recommendations.")
        
        item_name = data.get("item_name", "this item")
        recommendations = data.get("recommendations", [])
        
        if not recommendations:
            if language == "sw":
                msg = f"Hakuna bidhaa nyingine zinazonunuliwa pamoja na {item_name}."
            else:
                msg = f"I couldn't find any items commonly purchased with {item_name}."
            return {"message": msg, "data": []}
        
        if language == "sw":
            lines = [f"🛒 **Wateja walionunua {item_name} pia walinunua:**\n"]
        else:
            lines = [f"🛒 **Customers who bought {item_name} also bought:**\n"]
        
        for idx, item in enumerate(recommendations[:ResponseFormatter.MAX_RESULTS], 1):
            name = (item.get("ItemName") or item.get("name") or "Unknown Item")
            item_code = (item.get("ItemCode") or item.get("item_code") or "")
            price = item.get("Price") or item.get("price")
            reason = item.get("Reason") or item.get("reason") or ""
            stock_status = item.get("StockStatus") or item.get("stock_status") or ""
            stock = item.get("stock", 0)
            
            display_name = name
            if item_code:
                display_name = f"{name} ({item_code})"
            
            lines.append(f"{idx}. **{display_name}**")
            
            if price:
                if isinstance(price, (int, float)) and price > 0:
                    lines.append(f"   💰 Bei: {ResponseFormatter._format_price(price)} KES")
                else:
                    lines.append(f"   ⚠️ Bei: Haijulikani")
            else:
                lines.append(f"   ⚠️ Bei: Haijulikani")
            
            if reason:
                lines.append(f"   💡 Sababu: {reason}")
            
            if stock_status:
                lines.append(f"   {stock_status}")
            elif stock <= 0:
                lines.append(f"   ⚠️ Hali: ⚠️ Imeisha")
            elif stock > 0:
                lines.append(f"   ✅ Hali: Ipo (vitengo {stock})")
            
            lines.append("")
        
        if recommendations:
            if language == "sw":
                lines.append("💡 **Kidokezo:** Fungasha bidhaa hizi pamoja na uokoe 10%! Niambie kama unahitaji msaada!")
            else:
                lines.append("💡 **Tip:** Bundle these items together and save 10%! Let me know if you need help!")
        
        lines.append(ResponseFormatter._get_closer(language))
        
        return {
            "message": "\n".join(lines).strip(),
            "data": recommendations
        }

    # -------------------------------------------------
    @staticmethod
    def format_generic_error(data: dict, language: str = "en") -> dict:
        if language == "sw":
            msg = "Samahani, kuna hitilafu ilitokea. Tafadhali jaribu tena baadaye. 😔"
        else:
            msg = "Sorry, something went wrong. Please try again in a moment. 😔"
        return ResponseFormatter._not_available(msg)


# Singleton instance
response_formatter = ResponseFormatter()