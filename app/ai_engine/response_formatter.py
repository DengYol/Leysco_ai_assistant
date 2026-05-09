"""
app/ai_engine/response_formatter.py
====================================
Converts raw system responses into natural, conversational text
AND preserves structured list data for the mobile app UI.

UPDATED: Clean, professional formatting for all response types
FIXED: Quotation creation response with proper layout
FIXED: Top selling items - supports both 'ItemName' and 'name' fields
FIXED: Slow moving items - supports both naming conventions
ADDED: Sales analytics formatter
"""

import logging
import asyncio
import hashlib
import random
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
from functools import lru_cache, wraps

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


def cache_formatted(ttl_seconds: int = 300):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            cache = get_cache_service()
            cache_str = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            cache_key = hashlib.md5(cache_str.encode()).hexdigest()
            cached = cache.get_simple(cache_key)
            if cached is not None:
                logger.info(f"⚡ Formatter cache hit: {func.__name__}")
                return cached
            result = func(self, *args, **kwargs)
            if result:
                cache.set_simple(cache_key, result, ttl=ttl_seconds)
            return result
        return wrapper
    return decorator


class ResponseFormatter:
    MAX_RESULTS = 5
    MAX_CUSTOMERS_DISPLAY = 10

    OPENERS = {
        "GET_ITEM_PRICE": {
            "en": [
                "Sure! Let me check the price for you... 🔍",
                "Here's what I found:",
                "I've looked up the price:",
                "Let me get that information for you:",
                "Got it! Here's the pricing info:"
            ],
            "sw": [
                "Sawa! Naangalia bei kwa ajili yako... 🔍",
                "Hiki ndio nilichopata:",
                "Nimeangalia bei:",
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
                "These are the bestsellers this period:"
            ],
            "sw": [
                "Hizi ndizo bidhaa zinazouzwa sana kwa sasa! 🔥",
                "Wateja wanapenda bidhaa hizi:",
                "Kulingana na mauzo ya hivi karibuni, hizi ndizo zinazoongoza:",
                "Hivi ndivyo vinavyouzwa kwa kasi: 📦"
            ]
        },
        "GET_SLOW_MOVING_ITEMS": {
            "en": [
                "Here are some items that need a bit of attention: 👀",
                "These products could use some marketing love:",
                "Based on turnover rates, consider promoting these:",
                "These items might benefit from a discount or bundle: 💡"
            ],
            "sw": [
                "Hizi ni bidhaa zinazohitaji uangalizi kidogo: 👀",
                "Bidhaa hizi zinahitaji uuzaji zaidi:",
                "Bidhaa hizi zinaweza kufaidika na punguzo au kifurushi: 💡"
            ]
        },
        "GET_CUSTOMER_ORDERS": {
            "en": [
                "Here's what they've been ordering: 📋",
                "Looking at their purchase history:",
                "Here are the orders I found:",
                "Here's their order summary:"
            ],
            "sw": [
                "Hiki ndicho walichokuwa wakiagiza: 📋",
                "Huu ni muhtasari wa oda zao:"
            ]
        },
        "GET_OUTSTANDING_DELIVERIES": {
            "en": [
                "Let me check the delivery status for you... 🚚",
                "Here's what's pending delivery:",
                "I've found these outstanding deliveries:",
                "Checking your delivery pipeline... 📦"
            ],
            "sw": [
                "Ngoja niangalie hali ya usafirishaji kwa ajili yako... 🚚",
                "Hiki ndicho kinasubiri usafirishaji:",
                "Naangalia usafirishaji wako... 📦"
            ]
        },
        "CREATE_QUOTATION": {
            "en": [
                "Great news! I've prepared the quotation for you:",
                "Your quotation is ready! 📄 Here are the details:",
                "Done! Here's the quotation summary:",
                "Quotation created successfully! Here's the summary:"
            ],
            "sw": [
                "Habari njema! Nimekuandalia nukuu:",
                "Nukuu yako iko tayari! 📄 Haya ni maelezo:",
                "Nukuu imeundwa kikamilifu! Huu ni muhtasari:"
            ]
        },
    }

    CLOSERS = {
        "en": [
            "\n\n💡 Need anything else? I'm here to help! 😊",
            "\n\nIs there anything else you'd like to know?",
            "\n\nLet me know if you need more information!",
            "\n\nWhat else can I assist you with today?",
            "\n\nFeel free to ask about prices, stock, or customers!",
            "\n\nHappy to help with anything else!"
        ],
        "sw": [
            "\n\n💡 Unahitaji kitu kingine? Niko hapa kusaidia! 😊",
            "\n\nKuna chochote kingine ungependa kujua?",
            "\n\nNijulishe kama unahitaji maelezo zaidi!",
            "\n\nNini kingine ninachoweza kukusaidia nalo leo?"
        ]
    }

    NO_RESULTS = {
        "GET_ITEM_PRICE": {
            "en": "Hmm, I couldn't find any price information for that item. 🤔\n\n💡 Try:\n• Checking the spelling\n• Asking for a different product\n• Saying 'show me items' to browse our catalog",
            "sw": "Hmm, sikuweza kupata taarifa za bei kwa bidhaa hiyo. 🤔\n\n💡 Jaribu:\n• Angalia tahajia\n• Uliza kuhusu bidhaa nyingine"
        },
        "GET_TOP_SELLING_ITEMS": {
            "en": "I don't have enough sales data yet to show top selling items. 📊",
            "sw": "Sina data ya kutosha ya mauzo bado. 📊"
        },
        "GET_SLOW_MOVING_ITEMS": {
            "en": "Great news! No slow moving items found - your inventory is moving well! 🎉",
            "sw": "Habari njema! Hakuna bidhaa zinazotembea polepole - hisa zako zinasonga vizuri! 🎉"
        },
        "GET_CUSTOMER_ORDERS": {
            "en": "I couldn't find any orders for this customer. 📋",
            "sw": "Sikuweza kupata oda zozote kwa mteja huyu. 📋"
        },
        "GET_OUTSTANDING_DELIVERIES": {
            "en": "✅ No outstanding deliveries found! All deliveries are complete. 🎉",
            "sw": "✅ Hakuna usafirishaji uliobaki! Usafirishaji wote umekamilika. 🎉"
        }
    }

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
            "sw": "\n\n💡 Kidokezo: Fikiria kufanya promo au kufungasha bidhaa zinazotembea polepole!"
        },
        "GET_OUTSTANDING_DELIVERIES": {
            "en": "\n\n💡 Tip: Say 'create delivery note' to process these deliveries!",
            "sw": "\n\n💡 Kidokezo: Sema 'tengeneza hati ya usafirishaji' kusafirisha bidhaa hizi!"
        }
    }

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

    @staticmethod
    def _format_price(value):
        try:
            return f"{float(value):,.2f}"
        except Exception:
            return value or "0.00"

    @staticmethod
    def _format_date(date_str: Optional[str]) -> str:
        if not date_str:
            return "N/A"
        try:
            if isinstance(date_str, str):
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                return dt.strftime("%b %d, %Y")
            return str(date_str)
        except Exception:
            return str(date_str)[:10]

    @staticmethod
    def _not_available(msg="That information is not available in Leysco right now."):
        return {"message": msg, "data": []}

    @staticmethod
    def _get_opener(intent: str, language: str = "en") -> str:
        openers = ResponseFormatter.OPENERS.get(intent, {}).get(language, [])
        if openers:
            return random.choice(openers)
        return ""

    @staticmethod
    def _get_closer(language: str = "en") -> str:
        return random.choice(ResponseFormatter.CLOSERS.get(language, ResponseFormatter.CLOSERS["en"]))

    @staticmethod
    def _get_no_results_message(intent: str, language: str = "en") -> str:
        return ResponseFormatter.NO_RESULTS.get(intent, {}).get(
            language,
            "I couldn't find what you're looking for. Try rephrasing your question! 🤔"
        )

    @staticmethod
    def _get_tip(intent: str, language: str = "en") -> str:
        return ResponseFormatter.TIPS.get(intent, {}).get(language, "")

    @classmethod
    def format_quotation_creation_success(
        cls,
        customer_name: str,
        items: list,
        total_amount: float,
        valid_until: str,
        doc_num: str = None,
        language: str = "en"
    ) -> dict:
        """Format quotation creation response with clean, professional layout."""
        opener = cls._get_opener("CREATE_QUOTATION", language)

        # Format the date properly
        try:
            if valid_until and len(valid_until) > 10:
                valid_date = datetime.strptime(valid_until[:10], "%Y-%m-%d")
                valid_until_fmt = valid_date.strftime("%b %d, %Y")
            else:
                valid_until_fmt = valid_until
        except:
            valid_until_fmt = valid_until

        # Build structured items list
        structured_items = []
        for item in items:
            item_name = item.get("ItemName") or item.get("item_name") or item.get("name", "Unknown")
            quantity = item.get("Quantity") or item.get("quantity", 1)
            price = item.get("Price") or item.get("price", 0)
            line_total = float(quantity) * float(price) if quantity and price else 0
            structured_items.append({
                "name": item_name,
                "quantity": quantity,
                "price": float(price),
                "subtotal": line_total
            })

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            
            # Show quotation number if available
            if doc_num:
                lines.append(f"✅ **Nukuu #{doc_num} Imeundwa Kikamilifu**")
            else:
                lines.append("✅ **Nukuu Imeundwa Kikamilifu**")
            lines.append("")
            lines.append(f"**Mteja:** {customer_name}")
            lines.append(f"**Jumla:** KES {total_amount:,.2f}")
            lines.append(f"**Inaisha:** {valid_until_fmt}")
            lines.append("")
            lines.append("**Bidhaa:**")
            for item in structured_items:
                lines.append(f"• {item['quantity']} x **{item['name']}** @ KES {item['price']:,.2f} = KES {item['subtotal']:,.2f}")
            lines.append("")
            if doc_num:
                lines.append(f"📋 **Nukuu #{doc_num} imehifadhiwa kwenye mfumo.**")
            else:
                lines.append("📋 **Nukuu imehifadhiwa kwenye mfumo.**")
            lines.append("Unaweza kuituma kwa mteja au kuichapisha.")
            lines.append("")
            lines.append("**Vitendo:**")
            lines.append("• Tazama nukuu - Fungua maelezo kamili")
            lines.append("• Chapisha - Toa nakala ya nukuu")
            lines.append("• Tuma - Shiriki kwa barua pepe au ujumbe")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            
            # Show quotation number if available
            if doc_num:
                lines.append(f"✅ **Quotation #{doc_num} Created Successfully**")
            else:
                lines.append("✅ **Quotation Created Successfully**")
            lines.append("")
            lines.append(f"**Customer:** {customer_name}")
            lines.append(f"**Total:** KES {total_amount:,.2f}")
            lines.append(f"**Valid Until:** {valid_until_fmt}")
            lines.append("")
            lines.append("**Items:**")
            for item in structured_items:
                lines.append(f"• {item['quantity']} x **{item['name']}** @ KES {item['price']:,.2f} = KES {item['subtotal']:,.2f}")
            lines.append("")
            if doc_num:
                lines.append(f"📋 **Quotation #{doc_num} has been saved to the system.**")
            else:
                lines.append("📋 **Quotation has been saved to the system.**")
            lines.append("You can send it to the customer or print a copy.")
            lines.append("")
            lines.append("**Actions:**")
            lines.append("• View Quotation - See full details")
            lines.append("• Print - Get a printable copy")
            lines.append("• Send - Share via email or message")
            lines.append("")

        lines.append(cls._get_closer(language))

        return {
            "message": "\n".join(lines),
            "data": [{
                "customer_name": customer_name,
                "items": structured_items,
                "total_amount": total_amount,
                "valid_until": valid_until_fmt,
                "doc_num": doc_num,
                "success": True
            }],
            "quotation_id": doc_num
        }

    @classmethod
    def format_quotation_creation_error(
        cls,
        error_message: str,
        invalid_items: list = None,
        language: str = "en"
    ) -> dict:
        """Format quotation creation error response."""
        if language == "sw":
            lines = [
                "❌ **Hitilafu Wakati wa Kuunda Nukuu**",
                "",
                f"**Sababu:** {error_message}"
            ]
            if invalid_items:
                lines.append("")
                lines.append("**Bidhaa Zilizorukwa:**")
                for item in invalid_items[:5]:
                    item_name = item.get("ItemName") or item.get("name", "Unknown")
                    reason = item.get("reason", "Sababu haijulikani")
                    lines.append(f"• {item_name}: {reason}")
                if len(invalid_items) > 5:
                    lines.append(f"... na {len(invalid_items) - 5} nyingine")
            lines.append("")
            lines.append("**💡 Mapendekezo:**")
            lines.append("• Angalia majina ya bidhaa")
            lines.append("• Hakikisha bidhaa zina bei")
            lines.append("• Uliza 'nionyeshe bidhaa' kuona orodha")
        else:
            lines = [
                "❌ **Error Creating Quotation**",
                "",
                f"**Reason:** {error_message}"
            ]
            if invalid_items:
                lines.append("")
                lines.append("**Skipped Items:**")
                for item in invalid_items[:5]:
                    item_name = item.get("ItemName") or item.get("name", "Unknown")
                    reason = item.get("reason", "Unknown reason")
                    lines.append(f"• {item_name}: {reason}")
                if len(invalid_items) > 5:
                    lines.append(f"... and {len(invalid_items) - 5} more")
            lines.append("")
            lines.append("**💡 Suggestions:**")
            lines.append("• Check item names")
            lines.append("• Ensure items have prices")
            lines.append("• Ask 'show me items' to browse")

        lines.append("")
        lines.append(cls._get_closer(language))

        return {
            "message": "\n".join(lines),
            "data": [{"error": error_message, "invalid_items": invalid_items, "success": False}]
        }

    @staticmethod
    def format_customer_segmentation(data: Dict[str, Any], language: str = "en") -> dict:
        customers = data.get("customers", [])
        item_name = data.get("item_name", "this product")
        recommendations = data.get("recommendations", [])

        if not customers:
            msg = ResponseFormatter._get_no_results_message("FIND_CUSTOMERS_BY_ITEM", language)
            return {"message": msg, "data": []}

        opener = ResponseFormatter._get_opener("FIND_CUSTOMERS_BY_ITEM", language)

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"🎯 Wateja Wanaonunua {item_name}")
            lines.append(f"📊 Nimepata wateja {len(customers)}:")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"🎯 Customers Who Buy {item_name}")
            lines.append(f"📊 Found {len(customers)} customers:")
            lines.append("")

        for i, cust in enumerate(customers[:ResponseFormatter.MAX_CUSTOMERS_DISPLAY], 1):
            cust_name = cust.get("CardName", "Unknown")
            cust_code = cust.get("CardCode", "N/A")
            qty = cust.get("PurchaseQuantity", 0)
            last_purchase = cust.get("LastPurchaseDate", "")
            reason = cust.get("RecommendationReason", "")

            if language == "sw":
                lines.append(f"{i}. {cust_name} (Msimbo: {cust_code})")
                if qty > 0:
                    lines.append(f"   📦 Kiasi: {qty:,.0f} vitengo")
                if last_purchase:
                    lines.append(f"   🕒 Alinunua mwisho: {ResponseFormatter._format_date(last_purchase)}")
                if reason:
                    lines.append(f"   💡 {reason}")
                lines.append("")
            else:
                lines.append(f"{i}. {cust_name} (Code: {cust_code})")
                if qty > 0:
                    lines.append(f"   📦 Quantity purchased: {qty:,.0f} units")
                if last_purchase:
                    lines.append(f"   🕒 Last purchased: {ResponseFormatter._format_date(last_purchase)}")
                if reason:
                    lines.append(f"   💡 {reason}")
                lines.append("")

        total_customers = len(customers)
        if total_customers > ResponseFormatter.MAX_CUSTOMERS_DISPLAY:
            if language == "sw":
                lines.append(f"... na {total_customers - ResponseFormatter.MAX_CUSTOMERS_DISPLAY} wateja wengine.")
            else:
                lines.append(f"... and {total_customers - ResponseFormatter.MAX_CUSTOMERS_DISPLAY} more customers.")
            lines.append("")

        if recommendations:
            if language == "sw":
                lines.append("💡 Mapendekezo:")
            else:
                lines.append("💡 Recommendations:")
            for rec in recommendations[:3]:
                lines.append(f"• {rec}")
            lines.append("")

        if language == "sw":
            lines.append("💡 Vitendo:")
            lines.append("• Uliza 'nionyeshe maelezo ya mteja' kwa maelezo zaidi")
            lines.append("• Uliza 'unda nukuu kwa wateja hawa' kutengeneza nukuu")
        else:
            lines.append("💡 Next Steps:")
            lines.append("• Ask 'show customer details' for more information")
            lines.append("• Ask 'create quotation for these customers' to generate quotes")

        lines.append(ResponseFormatter._get_closer(language))

        return {"message": "\n".join(lines), "data": customers}

    @staticmethod
    def format_prices(data: dict) -> dict:
        return ResponseFormatter.format_item_price(data)

    @staticmethod
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
            if language == "sw":
                msg = f"Hmm, nimeipata {item_name} ({item_code}) lakini bei yake haijasanidiwa bado. 🤔\n\n💡 Jaribu kuuliza kuhusu bidhaa nyingine au wasiliana na mauzo kwa usaidizi!"
            else:
                msg = f"Hmm, I found {item_name} ({item_code}) but no price is configured for it yet. 🤔\n\n💡 Try asking for a different product or contact sales for assistance!"
            return {"message": msg, "data": []}

        opener = ResponseFormatter._get_opener("GET_ITEM_PRICE", language)

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"💰 **Bei za {item_name}**")
            if item_code:
                lines.append(f"   (Msimbo: {item_code})")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"💰 **Prices for {item_name}**")
            if item_code:
                lines.append(f"   (Code: {item_code})")
            lines.append("")

        structured = []
        for p in prices[:ResponseFormatter.MAX_RESULTS]:
            list_name = p.get("ListName", "Price List")
            price = ResponseFormatter._format_price(p.get("Price"))
            currency = p.get("Currency", "KES")

            if language == "sw":
                lines.append(f"• **{list_name}:** {price} {currency} kwa {uom}")
            else:
                lines.append(f"• **{list_name}:** {price} {currency} per {uom}")

            structured.append({
                "price_list": list_name,
                "price": price,
                "currency": currency,
                "uom": uom
            })

        lines.append(ResponseFormatter._get_tip("GET_ITEM_PRICE", language))
        lines.append(ResponseFormatter._get_closer(language))

        return {"message": "\n".join(lines), "data": structured}

    @staticmethod
    def format_top_selling_items(items: list, limit: int = 10, days: int = 30, language: str = "en") -> dict:
        """Format top selling items - supports both 'ItemName' and 'name' fields."""
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
            # Support both field naming conventions
            name = item.get('name') or item.get('ItemName', 'Unknown')
            score = item.get('PopularityScore', item.get('popularity_score', 0))
            velocity = item.get('Velocity', item.get('velocity', 'MEDIUM'))
            quantity = item.get('quantity') or item.get('Quantity', item.get('total_quantity', 0))

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

            if language == "sw":
                lines.append(f"{i}. {emoji} **{name}**")
                if quantity and quantity > 0:
                    lines.append(f"   📦 Imewauza: {quantity:,.0f}")
                if score and score > 0:
                    lines.append(f"   📊 Alama ya Umaarufu: {score:.1f}/100")
                lines.append("")
            else:
                lines.append(f"{i}. {emoji} **{name}**")
                if quantity and quantity > 0:
                    lines.append(f"   📦 Sold: {quantity:,.0f} units")
                if score and score > 0:
                    lines.append(f"   📊 Popularity Score: {score:.1f}/100")
                lines.append("")

        lines.append(ResponseFormatter._get_tip("GET_TOP_SELLING_ITEMS", language))
        lines.append(ResponseFormatter._get_closer(language))

        return {"message": "\n".join(lines), "data": items}

    @staticmethod
    def format_slow_moving_items(items: list, limit: int = 10, days: int = 90, language: str = "en") -> dict:
        """Format slow moving items - supports both naming conventions."""
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
            lines.append(f"⚠️ **Bidhaa {len(items)} Zinazotembea Polepole** (Siku {days} zilizopita)")
            lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"⚠️ **Top {len(items)} Slow Moving Items** (Last {days} days)")
            lines.append("")

        for i, item in enumerate(items[:limit], 1):
            # Support both field naming conventions
            name = item.get('name') or item.get('ItemName', 'Unknown')
            turnover = item.get('TurnoverRate', item.get('turnover_rate', 0))
            severity = item.get('Severity', item.get('severity', 'monitor'))
            recommendation = item.get('Recommendation', item.get('recommendation', ''))
            days_in_stock = item.get('DaysOfStock', item.get('days_in_stock', 0))
            quantity = item.get('quantity') or item.get('Quantity', item.get('total_quantity', 0))

            if severity == "critical":
                emoji = "🔴"
            elif severity == "warning":
                emoji = "🟡"
            else:
                emoji = "🟢"

            if language == "sw":
                lines.append(f"{i}. {emoji} **{name}**")
                if quantity and quantity > 0:
                    lines.append(f"   📦 Imewauza: {quantity:,.0f}")
                if days_in_stock and days_in_stock > 0:
                    lines.append(f"   📅 Siku hisani: {days_in_stock}")
                lines.append(f"   📊 Kiwango cha Mzunguko: {turnover:.2f}")
                if recommendation:
                    lines.append(f"   💡 {recommendation}")
                lines.append("")
            else:
                lines.append(f"{i}. {emoji} **{name}**")
                if quantity and quantity > 0:
                    lines.append(f"   📦 Sold: {quantity:,.0f} units")
                if days_in_stock and days_in_stock > 0:
                    lines.append(f"   📅 Days in stock: {days_in_stock}")
                lines.append(f"   📊 Turnover Rate: {turnover:.2f}")
                if recommendation:
                    lines.append(f"   💡 {recommendation}")
                lines.append("")

        lines.append(ResponseFormatter._get_tip("GET_SLOW_MOVING_ITEMS", language))
        lines.append(ResponseFormatter._get_closer(language))

        return {"message": "\n".join(lines), "data": items}

    @staticmethod
    def format_sales_analytics(data: dict, language: str = "en") -> dict:
        """Format sales analytics data - handles decision support response format."""
        if not data or data.get("error"):
            return ResponseFormatter._not_available(
                ResponseFormatter._get_no_results_message("GET_SALES_ANALYTICS", language) if "GET_SALES_ANALYTICS" in ResponseFormatter.NO_RESULTS else "No sales data available."
            )

        opener = ResponseFormatter._get_opener("GET_SALES_ANALYTICS", language)
        
        # Handle both direct data and decision support wrapper
        if "summary" in data:
            # Data from decision support (wrapped)
            summary = data.get("summary", {})
            top_products = data.get("top_products", [])
            date_range = data.get("date_range", {})
        else:
            # Direct data
            summary = data
            top_products = data.get("top_products", [])
            date_range = data.get("date_range", {})

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append("📊 **Uchambuzi wa Mauzo**\n")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append("📊 **Sales Analytics**\n")

        if date_range:
            if language == "sw":
                lines.append(f"📅 Kipindi: {date_range.get('from', 'N/A')} hadi {date_range.get('to', 'N/A')}")
            else:
                lines.append(f"📅 Period: {date_range.get('from', 'N/A')} to {date_range.get('to', 'N/A')}")
            lines.append("")

        total_revenue = summary.get('total_revenue', 0)
        total_orders = summary.get('total_transactions', 0)
        unique_customers = summary.get('unique_customers', 0)
        avg_order = summary.get('average_order_value', 0)
        total_items = summary.get('total_items_sold', 0)

        if language == "sw":
            lines.append(f"💰 **Mapato Jumla:** KES {total_revenue:,.2f}")
            lines.append(f"📦 **Oda Jumla:** {total_orders:,}")
            lines.append(f"👥 **Wateja Waliokuwa:** {unique_customers:,}")
            lines.append(f"📊 **Wastani wa Oda:** KES {avg_order:,.2f}")
            lines.append(f"📦 **Bidhaa Zilizouzwa:** {total_items:,}")
            lines.append("")
        else:
            lines.append(f"💰 **Total Revenue:** KES {total_revenue:,.2f}")
            lines.append(f"📦 **Total Orders:** {total_orders:,}")
            lines.append(f"👥 **Unique Customers:** {unique_customers:,}")
            lines.append(f"📊 **Average Order Value:** KES {avg_order:,.2f}")
            lines.append(f"📦 **Total Items Sold:** {total_items:,}")
            lines.append("")

        if top_products:
            if language == "sw":
                lines.append("🏆 **Bidhaa 5 Zinazouzwa Sana**")
            else:
                lines.append("🏆 **Top 5 Selling Products**")
            for i, prod in enumerate(top_products[:5], 1):
                prod_name = prod.get('name', prod.get('ItemName', 'Unknown'))
                prod_revenue = prod.get('revenue', prod.get('total_revenue', 0))
                prod_quantity = prod.get('quantity', prod.get('Quantity', 0))
                lines.append(f"{i}. **{prod_name}** - KES {prod_revenue:,.2f} ({prod_quantity:,.0f} units)")
            lines.append("")

        lines.append(ResponseFormatter._get_closer(language))

        return {"message": "\n".join(lines), "data": data}

    @staticmethod
    def format_customer_orders(orders: list, customer_name: str, language: str = "en") -> dict:
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

            if language == "sw":
                lines.append(f"{i}. **Oda #{doc_num}** ({doc_date})")
                lines.append(f"   💰 Kiasi: KES {doc_total:,.2f}")
                lines.append(f"   📍 Hali: {status}")
                lines.append("")
            else:
                lines.append(f"{i}. **Order #{doc_num}** ({doc_date})")
                lines.append(f"   💰 Amount: KES {doc_total:,.2f}")
                lines.append(f"   📍 Status: {status}")
                lines.append("")

        if len(orders) > 10:
            if language == "sw":
                lines.append(f"... na {len(orders) - 10} oda nyingine")
            else:
                lines.append(f"... and {len(orders) - 10} more orders")
            lines.append("")

        if language == "sw":
            lines.append(f"💰 **Jumla Kuu:** KES {total_value:,.2f}")
        else:
            lines.append(f"💰 **Grand Total:** KES {total_value:,.2f}")

        lines.append(ResponseFormatter._get_closer(language))

        return {"message": "\n".join(lines), "data": orders}

    @staticmethod
    def format_outstanding_deliveries(data: Union[dict, list], language: str = "en") -> dict:
        if isinstance(data, dict):
            deliveries = data.get('deliveries') or data.get('data') or data.get('items') or []
        elif isinstance(data, list):
            deliveries = data
        else:
            deliveries = []

        if not deliveries:
            msg = ResponseFormatter._get_no_results_message("GET_OUTSTANDING_DELIVERIES", language)
            return {"message": msg, "data": []}

        sample = deliveries[0] if deliveries else {}

        doc_id_fields = ['doc_num', 'document_number', 'doc_id', 'id', 'DocNum']
        customer_fields = ['customer_name', 'customer', 'CardName', 'customer_name_display', 'CustomerName']
        item_fields = ['item_code', 'ItemCode', 'product_code', 'item_name', 'ItemName']
        quantity_fields = ['pending_quantity', 'quantity', 'open_quantity', 'qty', 'PendingQuantity']
        value_fields = ['total_value', 'value', 'amount', 'DocTotal', 'TotalValue']

        doc_field = next((f for f in doc_id_fields if f in sample), 'doc_num')
        cust_field = next((f for f in customer_fields if f in sample), 'customer_name')
        item_field = next((f for f in item_fields if f in sample), 'item_code')
        qty_field = next((f for f in quantity_fields if f in sample), 'pending_quantity')
        val_field = next((f for f in value_fields if f in sample), 'total_value')

        by_document = {}
        by_customer = {}

        for item in deliveries:
            doc_id = str(item.get(doc_field, 'Unknown'))
            customer = item.get(cust_field, 'Unknown')

            if doc_id not in by_document:
                by_document[doc_id] = {
                    'customer': customer,
                    'items': [],
                    'total_value': 0,
                    'doc_date': item.get('doc_date', item.get('DocDate', '')),
                    'status': item.get('status', 'Outstanding')
                }
            by_document[doc_id]['items'].append(item)
            by_document[doc_id]['total_value'] += float(item.get(val_field, 0))

            if customer not in by_customer:
                by_customer[customer] = {
                    'documents': set(),
                    'items': [],
                    'total_value': 0
                }
            by_customer[customer]['documents'].add(doc_id)
            by_customer[customer]['items'].append(item)
            by_customer[customer]['total_value'] += float(item.get(val_field, 0))

        for customer in by_customer:
            by_customer[customer]['document_count'] = len(by_customer[customer]['documents'])
            del by_customer[customer]['documents']

        total_docs = len(by_document)
        total_items = len(deliveries)
        total_value = sum(float(d.get(val_field, 0)) for d in deliveries)
        overdue_count = sum(1 for d in deliveries if d.get('is_overdue', False))

        opener = ResponseFormatter._get_opener("GET_OUTSTANDING_DELIVERIES", language)

        if language == "sw":
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            lines.append(f"📦 **Muhtasari wa Usafirishaji Uliobaki: Hati {total_docs}**")
            lines.append(f"• Bidhaa {total_items} kwa jumla")
            lines.append(f"• Thamani jumla: KES {total_value:,.2f}")
            lines.append("")
            if overdue_count > 0:
                lines.append(f"⚠️ Tahadhari: {overdue_count} ya bidhaa zimechelewa kusafirishwa!")
                lines.append("")
            lines.append("**Maelezo kwa Wateja:**")
            lines.append("")
            for idx, (customer, cust_data) in enumerate(list(by_customer.items())[:5], 1):
                lines.append(f"{idx}. **{customer}**")
                doc_word = "hati" if cust_data['document_count'] == 1 else "hati"
                lines.append(f"   📄 {cust_data['document_count']} {doc_word}")
                lines.append(f"   💰 KES {cust_data['total_value']:,.2f}")
                for item in cust_data['items'][:3]:
                    item_code = item.get(item_field, 'N/A')
                    qty = item.get(qty_field, 0)
                    lines.append(f"   • {item_code}: {qty:,.0f} vitengo")
                if len(cust_data['items']) > 3:
                    lines.append(f"   • ... na {len(cust_data['items']) - 3} bidhaa nyingine")
                lines.append("")
            if len(by_customer) > 5:
                remaining = len(by_customer) - 5
                lines.append(f"📋 Na wateja wengine {remaining} wenye usafirishaji uliobaki.")
                lines.append("")
        else:
            lines = []
            if opener:
                lines.append(opener)
                lines.append("")
            doc_word = "document" if total_docs == 1 else "documents"
            lines.append(f"📦 **Outstanding Deliveries Summary: {total_docs} {doc_word}**")
            lines.append(f"• {total_items} line items total")
            lines.append(f"• Total value: KES {total_value:,.2f}")
            lines.append("")
            if overdue_count > 0:
                lines.append(f"⚠️ Alert: {overdue_count} item(s) are overdue for delivery!")
                lines.append("")
            lines.append("**Details by Customer:**")
            lines.append("")
            for idx, (customer, cust_data) in enumerate(list(by_customer.items())[:5], 1):
                lines.append(f"{idx}. **{customer}**")
                doc_word = "document" if cust_data['document_count'] == 1 else "documents"
                lines.append(f"   📄 {cust_data['document_count']} {doc_word}")
                lines.append(f"   💰 KES {cust_data['total_value']:,.2f}")
                for item in cust_data['items'][:3]:
                    item_code = item.get(item_field, 'N/A')
                    qty = item.get(qty_field, 0)
                    lines.append(f"   • {item_code}: {qty:,.0f} units")
                if len(cust_data['items']) > 3:
                    lines.append(f"   • ... and {len(cust_data['items']) - 3} more items")
                lines.append("")
            if len(by_customer) > 5:
                remaining = len(by_customer) - 5
                lines.append(f"📋 Plus {remaining} more customer(s) with outstanding deliveries.")
                lines.append("")

        lines.append(ResponseFormatter._get_tip("GET_OUTSTANDING_DELIVERIES", language))
        lines.append(ResponseFormatter._get_closer(language))

        return {
            "message": "\n".join(lines),
            "data": deliveries,
            "summary": {
                "total_documents": total_docs,
                "total_items": total_items,
                "total_value": total_value,
                "customers_affected": len(by_customer),
                "overdue_count": overdue_count
            }
        }

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
                    if c.get('PhoneNumber'):
                        lines.append(f"  📞 {c.get('PhoneNumber')}")
                    if c.get('EmailAddress'):
                        lines.append(f"  ✉️ {c.get('EmailAddress')}")
                    lines.append("")
        else:
            lines = ["👥 **Matching Customers:**\n"]
            for c in customers:
                if isinstance(c, dict):
                    lines.append(f"• **{c.get('CardName', 'N/A')}** (Code: {c.get('CardCode', 'N/A')})")
                    if c.get('PhoneNumber'):
                        lines.append(f"  📞 {c.get('PhoneNumber')}")
                    if c.get('EmailAddress'):
                        lines.append(f"  ✉️ {c.get('EmailAddress')}")
                    lines.append("")
        lines.append(ResponseFormatter._get_closer(language))
        return {"message": "\n".join(lines), "data": customers}

    @staticmethod
    def format_stock(data: dict, language: str = "en") -> dict:
        if "error" in data or data.get("stock") is None:
            return ResponseFormatter._not_available()
        stock = data.get('stock')
        item_name = data.get('item_name')
        warehouse = data.get('warehouse', '')
        
        if stock <= 0:
            if language == "sw":
                msg = f"📦 **{item_name}** imeisha kwa sasa."
                if warehouse:
                    msg += f" (Ghala: {warehouse})"
                msg += "\n\n💡 Tafadhali wasiliana na timu ya mauzo kwa usaidizi."
            else:
                msg = f"📦 **{item_name}** is currently out of stock."
                if warehouse:
                    msg += f" (Warehouse: {warehouse})"
                msg += "\n\n💡 Please contact the sales team for assistance."
        else:
            if language == "sw":
                msg = f"📦 **{item_name}** tuna vitengo **{stock:,.0f}** hisani."
                if warehouse:
                    msg += f" (Ghala: {warehouse})"
                msg += "\n\n💡 Unahitaji kuangalia bidhaa nyingine?"
            else:
                msg = f"📦 **{item_name}** we have **{stock:,.0f}** units in stock."
                if warehouse:
                    msg += f" (Warehouse: {warehouse})"
                msg += "\n\n💡 Need to check another product?"
        
        msg += "\n" + ResponseFormatter._get_closer(language)
        return {"message": msg, "data": [{"item": item_name, "stock": stock, "warehouse": warehouse}]}

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
                        item_name = i.get('ItemName', 'N/A')
                        item_code = i.get('ItemCode', 'N/A')
                        stock = i.get('OnHand')
                        lines.append(f"• **{item_name}** ({item_code})")
                        if stock is not None:
                            lines.append(f"  📦 Hisa: {stock:,.0f}")
                        lines.append("")
            else:
                lines = ["📦 **Matching Items:**\n"]
                for i in limited:
                    if isinstance(i, dict):
                        item_name = i.get('ItemName', 'N/A')
                        item_code = i.get('ItemCode', 'N/A')
                        stock = i.get('OnHand')
                        lines.append(f"• **{item_name}** ({item_code})")
                        if stock is not None:
                            lines.append(f"  📦 Stock: {stock:,.0f}")
                        lines.append("")
            lines.append(ResponseFormatter._get_closer(language))
            return {"message": "\n".join(lines), "data": limited}
        
        if title == "customers":
            return ResponseFormatter.format_customer(data, language)
        
        return {"message": f"I found some {title}.", "data": limited}

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
                quantity = item.get("quantity") or item.get("Quantity") or "N/A"
            else:
                name = str(item)
                warehouse = "N/A"
                quantity = "N/A"
            if language == "sw":
                lines.append(f"{idx}. **{name}**")
                lines.append(f"   🏭 Ghala: {warehouse}")
                if quantity != "N/A":
                    lines.append(f"   📦 Kiasi: {quantity}")
            else:
                lines.append(f"{idx}. **{name}**")
                lines.append(f"   🏭 Warehouse: {warehouse}")
                if quantity != "N/A":
                    lines.append(f"   📦 Quantity: {quantity}")
            lines.append("")
            structured.append({"name": name, "warehouse": warehouse, "quantity": quantity})
        lines.append(ResponseFormatter._get_closer(language))
        return {"message": "\n".join(lines), "data": structured}

    @staticmethod
    def format_customer_activity(summary: dict, engagement: str, language: str = "en") -> dict:
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
            ]
        
        message_lines.append("")
        message_lines.append(ResponseFormatter._get_closer(language))
        return {"message": "\n".join(message_lines), "data": summary}

    @staticmethod
    def format_recommended_items(data: list, language: str = "en") -> str:
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

    @staticmethod
    def format_recommended_customers(data: list, language: str = "en") -> str:
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
                if language == "sw":
                    msg = f"No quotations found for {customer_name}."
                else:
                    msg = f"Hakuna nukuu zilizopatikana kwa {customer_name}."
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
        return {"message": text, "data": quotations}

    @staticmethod
    def format_cross_sell(data: dict, language: str = "en") -> dict:
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
            
            display_name = f"{name} ({item_code})" if item_code else name
            lines.append(f"{idx}. **{display_name}**")
            
            if price and isinstance(price, (int, float)) and price > 0:
                lines.append(f"   💰 Bei: {ResponseFormatter._format_price(price)} KES")
            else:
                lines.append(f"   ⚠️ Bei: Haijulikani")
            
            if reason:
                lines.append(f"   💡 Sababu: {reason}")
            
            if stock_status:
                lines.append(f"   {stock_status}")
            elif stock <= 0:
                lines.append(f"   ⚠️ Hali: Imeisha")
            elif stock > 0:
                lines.append(f"   ✅ Hali: Ipo (vitengo {stock})")
            lines.append("")
        
        if recommendations:
            if language == "sw":
                lines.append("💡 **Kidokezo:** Fungasha bidhaa hizi pamoja na uokoe 10%!")
            else:
                lines.append("💡 **Tip:** Bundle these items together and save 10%!")
        
        lines.append(ResponseFormatter._get_closer(language))
        return {"message": "\n".join(lines).strip(), "data": recommendations}

    @staticmethod
    def format_generic_error(data: dict, language: str = "en") -> dict:
        if language == "sw":
            msg = "❌ Samahani, kuna hitilafu ilitokea. Tafadhali jaribu tena baadaye. 😔"
        else:
            msg = "❌ Sorry, something went wrong. Please try again in a moment. 😔"
        return ResponseFormatter._not_available(msg)


response_formatter = ResponseFormatter()