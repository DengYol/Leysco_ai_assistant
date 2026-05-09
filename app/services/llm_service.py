"""
app/services/llm_service.py
============================
LLM Service with multiple provider support (Groq + Gemini)
Enhanced with natural language understanding, conversation memory, and flexible responses.
"""

import json
import logging
import asyncio
import random
import re
from typing import Optional, List, Dict, Any, Union, Tuple
from functools import wraps
from datetime import datetime
import time

from app.core.config import settings
from app.ai_engine.leysco_knowledge_base import get_knowledge

logger = logging.getLogger(__name__)

# Try to import Groq
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logger.warning("Groq library not installed. Install with: pip install groq")

# Try to import new Gemini SDK (google-genai)
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("Google GenAI library not installed. Install with: pip install google-genai")


# ---------------------------------------------------------------------------
# 1. COMPANY PROFILE
# ---------------------------------------------------------------------------

LEYSCO_PROFILE = """
Company: Leysco Limited
Tagline: Simply Reliable
Industry: Software Development & IT Consultancy
Location: APA Arcade, Hurlingham, Nairobi, Kenya
Phone: +254(0) 780 457 591
Email: info@leysco.com
Website: https://leysco.com

Who They Are:
Leysco is a software development and consultancy company specialising in
enterprise Resource Planning and Management Systems for businesses in Kenya.

Core Services: SAP ERP Implementation, Systems Consulting, Web & Mobile App
Development, Web Hosting, EDMS (Electronic Document Management)

About Leysco100:
Leysco100 is Leysco's SAP Business One implementation for an agricultural
inputs client. It manages inventory, customers, pricing, sales orders, and
warehouse operations for seeds, fertilizers, and agro-chemicals in Kenya.
"""

# ---------------------------------------------------------------------------
# 2. ENHANCED LANGUAGE INSTRUCTIONS
# ---------------------------------------------------------------------------

LANGUAGE_INSTRUCTIONS: dict[str, str] = {
    "sw": (
        "MUHIMU: Mtumiaji anaandika kwa Kiswahili.\n"
        "Jibu kwa Kiswahili cha kawaida, kama unavyozungumza na mtu.\n"
        "Tumia maneno rahisi na ya kirafiki.\n"
        "Nambari na kanuni za bidhaa ziweze kubaki kwa Kiingereza (mfano: KES 500, ItemCode WH01).\n"
        "Epuka maneno hasi. Tumia: 'Nimepata', 'Hiki ndio', 'Hongera!', 'Niko hapa kukusaidia'.\n"
        "Mwishoni, uliza kama wana swali lingine."
    ),
    "mixed": (
        "NOTE: The user is writing in a mix of Swahili and English.\n"
        "Mirror their style — respond in the same Swahili-English mix.\n"
        "Be friendly and natural, like a helpful colleague.\n"
        "Keep business terms, numbers, item codes, and currency (KES) in English.\n"
        "Use positive language. End by asking if they need anything else."
    ),
    "en": (
        "IMPORTANT: Be a FRIENDLY, NATURAL assistant - NOT a robot.\n\n"
        "CONVERSATIONAL RULES:\n"
        "• Use natural language like a helpful colleague\n"
        "• Vary your responses (don't repeat the same phrases)\n"
        "• Use occasional emojis for friendliness (😊, 👍, 📦, 💰, 🔥)\n"
        "• Acknowledge the user's request before answering\n"
        "• Ask follow-up questions when appropriate\n"
        "• End with an offer to help further\n\n"
        "NEVER use robotic phrases like:\n"
        "❌ 'Based on the data provided'\n"
        "❌ 'According to the system'\n"
        "❌ 'I have retrieved the following information'\n\n"
        "INSTEAD use natural phrases like:\n"
        "✅ 'Here's what I found...'\n"
        "✅ 'I checked and here's the info...'\n"
        "✅ 'Great news! Here are the details...'\n"
        "✅ 'Sure thing! Here you go...'\n\n"
        "Be warm, professional, and encouraging.\n"
        "Use bullet points or numbered lists for multiple items."
    ),
}

# ---------------------------------------------------------------------------
# 3. ENHANCED INTENT SYSTEM PROMPTS (More Natural)
# ---------------------------------------------------------------------------

INTENT_SYSTEM_PROMPTS: dict[str, str] = {
    "GET_ITEM_PRICE": (
        "You're helping a sales rep check product prices.\n\n"
        "STYLE: Be quick and helpful. Start with a natural opener.\n\n"
        "OPENERS (choose one naturally):\n"
        "• 'Sure! Here's the price for [item]'\n"
        "• 'I looked up [item] for you'\n"
        "• 'Here you go - the pricing info'\n"
        "• 'Got it! Here's what I found'\n\n"
        "FORMAT: Use bullet points for multiple variants.\n"
        "Include: item name, size, code, price, and price list.\n"
        "Use **bold** for prices and important numbers.\n"
        "End with a helpful question like 'Need any other prices?'"
    ),
    "GET_STOCK_LEVELS": (
        "You're checking inventory stock levels for products.\n\n"
        "STYLE: Be clear and specific with numbers. Use emojis for visual cues.\n\n"
        "OPENERS (choose one naturally):\n"
        "• 'Here's the stock level for [item] 📦'\n"
        "• 'I checked the inventory for you:'\n"
        "• 'Here's what we have in stock:'\n\n"
        "FORMAT: For each warehouse, show:\n"
        "• Warehouse name/code\n"
        "• On hand quantity\n"
        "• Committed quantity (if available)\n"
        "• Available quantity (on hand - committed)\n"
        "• Use **bold** for the available quantity\n"
        "• Add a note if stock is low or negative\n\n"
        "If negative available (backorders), explain clearly.\n"
        "End with: 'Need to check another product?'"
    ),
    "GET_CUSTOMER_PRICE": (
        "You're checking customer-specific pricing.\n\n"
        "STYLE: Be personal and helpful.\n\n"
        "FORMAT: State customer name, item, price, and any notes.\n"
        "If multiple items, list them clearly.\n"
        "Use **bold** for prices.\n"
        "End with: 'Would you like to create a quotation for them?'"
    ),
    "GET_CUSTOMER_DETAILS": (
        "You're sharing customer information with a sales rep.\n\n"
        "STYLE: Present info in a clean, scannable format.\n"
        "Use emojis for visual cues: 👤 for customer, 📞 for phone, 📧 for email.\n"
        "Use **bold** for customer name and code.\n\n"
        "End with: 'Would you like to see their order history or create a quote?'"
    ),
    "GET_TOP_SELLING_ITEMS": (
        "You're showing top selling products.\n\n"
        "STYLE: Be excited and encouraging! Use fire emojis 🔥\n\n"
        "OPENERS:\n"
        "• 'Here are our hottest sellers right now! 🔥'\n"
        "• 'Customers are loving these products:'\n"
        "• 'Based on recent sales, these are the top performers:'\n\n"
        "For each item, include popularity score if available.\n"
        "Use **bold** for item names.\n"
        "End with: 'Want to check stock on any of these?'"
    ),
    "GET_SLOW_MOVING_ITEMS": (
        "You're identifying slow-moving inventory.\n\n"
        "STYLE: Be constructive and helpful, not negative.\n\n"
        "OPENERS:\n"
        "• 'Here are some items that could use a little attention:'\n"
        "• 'These products might benefit from a promotion:'\n"
        "• 'Let me share what's moving a bit slower:'\n\n"
        "Include turnover rate, severity level (Critical/Warning/Monitor), and specific recommendations.\n"
        "Use **bold** for severity levels and recommendations.\n"
        "For CRITICAL items: Urge immediate action like markdowns or bundling.\n"
        "For WARNING items: Suggest reviewing pricing or considering discontinuation.\n"
        "For MONITOR items: Recommend keeping an eye on sales velocity.\n"
        "End with: 'Would you like me to suggest promotions for these?'"
    ),
    "GET_CUSTOMER_ORDERS": (
        "You're showing customer order history.\n\n"
        "STYLE: Be helpful and informative.\n\n"
        "OPENERS:\n"
        "• 'Here's what [customer] has been ordering:'\n"
        "• 'Let me pull up their purchase history:'\n"
        "• 'Here are their recent orders:'\n\n"
        "Include order numbers, dates, totals, and status.\n"
        "Use **bold** for totals.\n"
        "End with: 'Need to create a new order or quotation for them?'"
    ),
    "FIND_CUSTOMERS_BY_ITEM": (
        "You're helping find customers for a specific product.\n\n"
        "STYLE: Be strategic and helpful.\n\n"
        "OPENERS:\n"
        "• 'Great! Here are customers who buy [product]:'\n"
        "• 'I found these potential customers for [product]:'\n"
        "• 'Based on purchase history, these customers might be interested:'\n\n"
        "Include customer names, purchase quantities, and reasons.\n"
        "Use **bold** for customer names.\n"
        "End with: 'Want me to create quotations for any of these customers?'"
    ),
    "GET_WAREHOUSES": (
        "You're showing warehouse locations.\n\n"
        "STYLE: Be clear and organized.\n\n"
        "OPENERS:\n"
        "• 'Here are our warehouse locations:'\n"
        "• 'We have stock at these locations:'\n\n"
        "Include warehouse names, codes, and stock counts when available.\n"
        "Use **bold** for warehouse names."
    ),
    "GET_LOW_STOCK_ALERTS": (
        "You're alerting about low stock levels.\n\n"
        "STYLE: Be urgent but helpful.\n\n"
        "OPENERS:\n"
        "• '⚠️ Here's what's running low:'\n"
        "• 'Heads up! These items need reordering soon:'\n"
        "• 'Let me share what's getting low:'\n\n"
        "Include item names, current stock, and recommended actions.\n"
        "Use **bold** for stock quantities.\n"
        "End with: 'Should I help you create reorder requests?'"
    ),
    "CREATE_QUOTATION": (
        "You're helping create a quotation.\n\n"
        "STYLE: Be celebratory and helpful!\n\n"
        "OPENERS:\n"
        "• 'Great! I've prepared the quotation for you:'\n"
        "• '✅ Quotation created successfully! Here's the summary:'\n"
        "• 'All set! Here's the quotation details:'\n\n"
        "Include customer name, items, quantities, prices, and total.\n"
        "Use **bold** for customer name, total amount, and quotation number.\n"
        "End with: 'Need to email this to the customer?'"
    ),
    "GENERAL": (
        "You are a friendly, helpful assistant for Leysco staff.\n\n"
        "PERSONALITY: Warm, knowledgeable, and efficient.\n"
        "Be conversational - respond like a helpful colleague.\n"
        "Use occasional emojis for friendliness.\n"
        "Vary your responses - don't repeat the same phrases.\n"
        "Use **bold** for important information.\n"
        "Always end by asking if you can help with anything else."
    ),
    "UNKNOWN": (
        "You are a helpful assistant for Leysco.\n\n"
        "The user's request was unclear. Be friendly and guide them.\n\n"
        "RESPONSE STYLE:\n"
        "• 'I'd be happy to help! Could you tell me more about what you're looking for?'\n"
        "• 'Sure thing! To help you better, could you clarify...'\n\n"
        "SUGGEST what you CAN help with:\n"
        "• Check prices ('price of vegimax')\n"
        "• Check stock ('stock level of cabbage')\n"
        "• View customers ('show customers')\n"
        "• Top selling items ('top selling items')\n"
        "• Create quotations ('create quotation for Magomano with 5 vegimax')"
    ),
}

DEFAULT_SYSTEM_PROMPT = INTENT_SYSTEM_PROMPTS["GENERAL"]

# ---------------------------------------------------------------------------
# 4. CONVERSATIONAL FALLBACK MESSAGES
# --------------------------------------------------------------------------

_NO_DATA_FALLBACKS_EN: dict[str, str] = {
    "GET_ITEM_PRICE": (
        "Hmm, I couldn't find a price for that item in our system. 🤔\n\n"
        "💡 **A few things to try:**\n"
        "• Double-check the spelling (e.g., 'vegimax' not 'vegimx')\n"
        "• Use the exact product name\n"
        "• Ask for 'show me items' to browse our catalog\n\n"
        "Want me to help you search for something else?"
    ),
    "GET_STOCK_LEVELS": (
        "I checked the inventory but couldn't find stock levels for that item. 📦\n\n"
        "💡 **Try:**\n"
        "• Use the exact product name (e.g., 'vegimax 30ml')\n"
        "• Check the item code\n"
        "• Ask 'show items' to see what's in the system\n\n"
        "Want me to help you find something else?"
    ),
    "GET_TOP_SELLING_ITEMS": (
        "I don't have enough sales data yet to show top sellers. 📊\n\n"
        "💡 **Try:**\n"
        "• Asking for a different time period\n"
        "• Checking back when there's more data\n"
        "• Asking about specific products instead\n\n"
        "Is there anything else I can help with?"
    ),
    "GET_SLOW_MOVING_ITEMS": (
        "Great news! No slow-moving items found - your inventory is moving well! 🎉\n\n"
        "Everything seems to be selling at a healthy pace. Keep up the good work! 💪\n\n"
        "Need me to check anything else?"
    ),
    "GET_CUSTOMER_ORDERS": (
        "I couldn't find any orders for this customer. 📋\n\n"
        "💡 **Would you like to:**\n"
        "• Create a quotation for them?\n"
        "• Check their customer details?\n"
        "• Search for a different customer?\n\n"
        "Let me know how I can help!"
    ),
    "GET_WAREHOUSES": (
        "I couldn't find any warehouse information. 🏭\n\n"
        "This might be a temporary issue. Want me to try again or check something else?"
    ),
    "GET_LOW_STOCK_ALERTS": (
        "Good news! No low stock alerts at the moment. 📦\n\n"
        "All inventory levels look healthy. Need me to check anything specific?"
    ),
    "CREATE_QUOTATION": (
        "I had trouble creating that quotation. 🤔\n\n"
        "💡 **Common issues:**\n"
        "• Make sure the customer name is correct\n"
        "• Check that items have prices configured\n"
        "• Verify the quantities are valid\n\n"
        "Want to try again with different information?"
    ),
}

_NO_DATA_FALLBACKS_SW: dict[str, str] = {
    "GET_ITEM_PRICE": (
        "Hmm, sikuweza kupata bei ya bidhaa hiyo katika mfumo wetu. 🤔\n\n"
        "💡 **Jaribu:**\n"
        "• Angalia tahajia (mfano, 'vegimax' si 'vegimx')\n"
        "• Tumia jina kamili la bidhaa\n"
        "• Uliza 'nionyeshe bidhaa' kuona orodha yetu\n\n"
        "Unataka nikusaidie kutafuta kitu kingine?"
    ),
    "GET_STOCK_LEVELS": (
        "Niliangalia hisa lakini sikuweza kupata bidhaa hiyo. 📦\n\n"
        "💡 **Jaribu:**\n"
        "• Tumia jina kamili la bidhaa (mfano, 'vegimax 30ml')\n"
        "• Angalia msimbo wa bidhaa\n"
        "• Uliza 'nionyeshe bidhaa' kuona orodha\n\n"
        "Unataka nikusaidie kutafuta kitu kingine?"
    ),
    "GET_TOP_SELLING_ITEMS": (
        "Bado sina data ya kutosha ya mauzo kuonyesha bidhaa zinazouzwa sana. 📊\n\n"
        "💡 **Jaribu:**\n"
        "• Uliza kwa kipindi tofauti\n"
        "• Angalia tena baadaye kutakuwa na data zaidi\n"
        "• Uliza kuhusu bidhaa maalum badala yake\n\n"
        "Kuna kitu kingine ninachoweza kukusaidia?"
    ),
    "GET_SLOW_MOVING_ITEMS": (
        "Habari njema! Hakuna bidhaa zinazotembea polepole - hisa zako zinasonga vizuri! 🎉\n\n"
        "Kila kitu kinaonekana kinauzwa kwa kasi nzuri. Endelea na kazi nzuri! 💪\n\n"
        "Nahitaji kuangalia kitu kingine?"
    ),
    "GET_CUSTOMER_ORDERS": (
        "Sikuweza kupata oda zozote kwa mteja huyu. 📋\n\n"
        "💡 **Je, ungependa:**\n"
        "• Kuunda nukuu kwa ajili yao?\n"
        "• Angalia maelezo ya mteja?\n"
        "• Tafuta mteja mwingine?\n\n"
        "Nijulishe nikusaidie vipi!"
    ),
}


# ---------------------------------------------------------------------------
# 5. ENHANCED LLM SERVICE
# ---------------------------------------------------------------------------

class LLMService:
    """
    Enhanced LLM service with natural language understanding,
    conversation memory, and flexible response generation.
    """

    def __init__(self, provider: str = "auto"):
        """
        Initialize LLM service.
        
        Args:
            provider: "groq", "gemini", or "auto" (tries Gemini first, then Groq)
        """
        self.provider = provider
        self._groq_client = None
        self._gemini_client = None
        self._gemini_available = False
        
        # Conversation memory (simple in-memory)
        self._conversation_history: Dict[str, List[Dict]] = {}
        self._max_history = 10  # Keep last 10 exchanges per session
        
        # Rate limiting for free tier
        self._last_request_time = 0
        self._min_interval = 4  # seconds (for 15 RPM)
        
        # Response variation tracking
        self._last_response_style = {}  # Track last style used per intent
        
        # Initialize based on provider
        if provider in ["groq", "auto"]:
            self._init_groq()
        if provider in ["gemini", "auto"]:
            self._init_gemini()
        
        logger.info(f"✅ LLMService initialized with provider: {self._get_active_provider()}")

    def _get_active_provider(self) -> str:
        """Get the provider that will be used first."""
        if self.provider == "groq" and self._groq_client:
            return "groq"
        if self.provider == "gemini" and self._gemini_available:
            return "gemini"
        if self.provider == "auto":
            if self._gemini_available:
                return "gemini (free tier)"
            if self._groq_client:
                return "groq (fallback)"
        return "none"

    def _init_groq(self):
        """Initialize Groq client."""
        if not GROQ_AVAILABLE:
            logger.warning("Groq not available - library not installed")
            return
        
        api_key = settings.GROQ_API_KEY
        if not api_key:
            logger.warning("GROQ_API_KEY not set in environment")
            return
        
        try:
            self._groq_client = Groq(api_key=api_key)
            logger.info("✅ Groq client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Groq: {e}")
            self._groq_client = None

    def _init_gemini(self):
        """Initialize Gemini client with new google-genai SDK."""
        if not GEMINI_AVAILABLE:
            logger.warning("Gemini not available - google-genai library not installed")
            return
        
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            logger.warning("GEMINI_API_KEY not set in environment - get free key from https://aistudio.google.com/")
            return
        
        try:
            # Initialize the new Gemini client
            self._gemini_client = genai.Client(api_key=api_key)
            
            # Store the default model name
            self._gemini_model = "gemini-1.5-flash"  # or "gemini-2.0-flash-exp" for latest
            
            self._gemini_available = True
            logger.info("✅ Gemini client initialized with google-genai SDK (free tier)")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self._gemini_available = False

    def _rate_limit(self):
        """Implement rate limiting for free tier."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            sleep_time = self._min_interval - elapsed
            logger.info(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    # -----------------------------------------------------------------------
    # FIXED: Clean response method that preserves formatting for chat UI
    # -----------------------------------------------------------------------
    
    def clean_response(self, text: str) -> str:
        """
        Clean response for display while preserving readable formatting.
        Keeps **bold** text, bullet points, and emojis for beautiful chat output.
        """
        if not text:
            return text
        
        # Remove code blocks but keep their content
        text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
        
        # Convert markdown links [text](url) -> text (keep the text)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # Clean up excessive whitespace (but keep line breaks for readability)
        text = re.sub(r' +', ' ', text)  # Multiple spaces to single
        text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 line breaks
        
        # Fix spacing after periods
        text = re.sub(r'\.([A-Z])', r'. \1', text)
        
        # Ensure bullet points have proper spacing
        text = re.sub(r'\n•', '\n•', text)
        text = re.sub(r'^•', '•', text, flags=re.MULTILINE)
        
        # Preserve emojis and special characters
        # Don't strip them out - they make the UI friendly
        
        return text.strip()

    # -----------------------------------------------------------------------
    # Conversation Memory
    # -----------------------------------------------------------------------
    
    def get_conversation_history(self, session_id: str) -> List[Dict]:
        """Get conversation history for a session."""
        return self._conversation_history.get(session_id, [])
    
    def add_to_history(self, session_id: str, user_message: str, assistant_response: str):
        """Add exchange to conversation history."""
        if session_id not in self._conversation_history:
            self._conversation_history[session_id] = []
        
        self._conversation_history[session_id].append({
            "user": user_message,
            "assistant": assistant_response,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last N exchanges
        if len(self._conversation_history[session_id]) > self._max_history:
            self._conversation_history[session_id] = self._conversation_history[session_id][-self._max_history:]
    
    def clear_history(self, session_id: str):
        """Clear conversation history for a session."""
        if session_id in self._conversation_history:
            del self._conversation_history[session_id]

    # -----------------------------------------------------------------------
    # Enhanced Response Generation
    # -----------------------------------------------------------------------

    def _get_response_style(self, intent: str) -> str:
        """Get a varied response style for the intent."""
        styles = {
            "GET_ITEM_PRICE": ["direct", "friendly", "enthusiastic"],
            "GET_STOCK_LEVELS": ["detailed", "clear", "informative"],
            "GET_TOP_SELLING_ITEMS": ["excited", "informative", "encouraging"],
            "GET_SLOW_MOVING_ITEMS": ["helpful", "constructive", "strategic"],
            "GET_CUSTOMER_ORDERS": ["detailed", "summary", "insightful"],
            "CREATE_QUOTATION": ["celebratory", "professional", "helpful"],
        }
        
        intent_styles = styles.get(intent, ["friendly", "helpful", "professional"])
        
        # Get last used style for this intent
        last_style = self._last_response_style.get(intent)
        
        # Pick a different style if possible
        available_styles = [s for s in intent_styles if s != last_style]
        if not available_styles:
            available_styles = intent_styles
        
        chosen = random.choice(available_styles)
        self._last_response_style[intent] = chosen
        return chosen

    def _build_system_prompt(
        self,
        intent: str | None = None,
        db_context: Any = None,
        language: str | None = None,
        session_id: str | None = None,
        user_message: str = "",
    ) -> str:
        """Build enhanced system prompt with conversation context."""
        parts = []
        
        # Language instruction
        lang_key = (language or "en").lower().strip()
        lang_instruction = LANGUAGE_INSTRUCTIONS.get(lang_key, "")
        if lang_instruction:
            parts.append(f"=== LANGUAGE INSTRUCTION ===\n{lang_instruction}\n")
        
        # Response style for this intent
        intent_key = (intent or "GENERAL").upper()
        style = self._get_response_style(intent_key)
        parts.append(f"=== RESPONSE STYLE ===\nUse a {style} and conversational tone.\n")
        
        # Base identity
        parts.append(
            "You are a friendly, helpful AI assistant for Leysco Limited.\n"
            "You speak like a knowledgeable colleague, not a robot.\n"
        )
        parts.append(f"--- COMPANY PROFILE ---\n{LEYSCO_PROFILE}\n")
        
        # Intent-specific instructions
        intent_instruction = INTENT_SYSTEM_PROMPTS.get(intent_key, DEFAULT_SYSTEM_PROMPT)
        parts.append(f"--- YOUR ROLE ---\n{intent_instruction}\n")
        
        # Knowledge base
        kb_content = get_knowledge(intent_key)
        if kb_content and intent_key not in ("GENERAL", "UNKNOWN"):
            parts.append(f"--- LEYSCO KNOWLEDGE BASE ---\n{kb_content}\n")
        
        # Conversation history (if available)
        if session_id:
            history = self.get_conversation_history(session_id)
            if history:
                parts.append("--- RECENT CONVERSATION ---")
                for exchange in history[-3:]:  # Last 3 exchanges
                    parts.append(f"User: {exchange['user'][:200]}")
                    parts.append(f"Assistant: {exchange['assistant'][:200]}")
                parts.append("")
        
        # Database context
        if db_context:
            formatted_context = self._format_context(db_context, intent_key, language)
            parts.append(
                f"--- LEYSCO100 SYSTEM DATA ---\n"
                f"The following data was retrieved from the database:\n"
                f"{formatted_context}\n"
                f"Base your answer on this data. Do NOT invent values not shown.\n"
            )
        
        # Final instruction
        parts.append(
            "Remember: Be conversational, friendly, and helpful. "
            "Use natural language like you're talking to a colleague. "
            "Avoid robotic phrases like 'based on the data provided'. "
            "Use **bold** for important numbers and names. "
            "End by asking if they need anything else."
        )
        
        return "\n".join(parts)

    def _format_context(self, db_context: Any, intent: str, language: str = "en") -> str:
        """Format database context for LLM in a natural way."""
        if not db_context:
            return "No data available."
        
        # Handle stock/price data specially
        if intent in ["GET_ITEM_PRICE", "GET_CUSTOMER_PRICE"]:
            return self._format_price_data_natural(db_context, language)
        
        # Handle stock levels
        if intent == "GET_STOCK_LEVELS":
            return self._format_stock_data_natural(db_context, language)
        
        # Handle customer data
        if intent == "GET_CUSTOMER_DETAILS":
            return self._format_customer_data_natural(db_context, language)
        
        # Handle customer segmentation
        if intent == "FIND_CUSTOMERS_BY_ITEM":
            return self._format_customer_segmentation_natural(db_context, language)
        
        # Handle top selling items
        if intent == "GET_TOP_SELLING_ITEMS":
            return self._format_top_selling_natural(db_context, language)
        
        # Handle slow moving items
        if intent == "GET_SLOW_MOVING_ITEMS":
            return self._format_slow_moving_natural(db_context, language)
        
        # Handle warehouses
        if intent == "GET_WAREHOUSES":
            return self._format_warehouse_data_natural(db_context, language)
        
        # Handle low stock alerts
        if intent == "GET_LOW_STOCK_ALERTS":
            return self._format_low_stock_natural(db_context, language)
        
        # Default formatting
        if isinstance(db_context, list):
            if len(db_context) > 20:
                db_context = db_context[:20]
                return json.dumps(db_context, indent=2, default=str) + f"\n... and {len(db_context)} total items"
            return json.dumps(db_context, indent=2, default=str)
        elif isinstance(db_context, dict):
            return json.dumps(db_context, indent=2, default=str)
        return str(db_context)
    
    def _format_stock_data_natural(self, data: Any, language: str = "en") -> str:
        """Format stock level data naturally for LLM consumption."""
        items = data if isinstance(data, list) else [data]
        if not items:
            return "No stock data available."
        
        lines = ["STOCK LEVEL INFORMATION:"]
        
        # Group by item name/code
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
            on_hand = item.get("stock", item.get("on_hand", item.get("CurrentOnHand", 0)))
            committed = item.get("committed", item.get("CurrentIsCommited", 0))
            available = item.get("available", on_hand - committed if committed else on_hand)
            
            by_item[key]["warehouses"].append({
                "warehouse": warehouse,
                "on_hand": round(float(on_hand), 1),
                "committed": round(float(committed), 1),
                "available": round(float(available), 1)
            })
        
        for item_data in by_item.values():
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
    
    def _format_price_data_natural(self, data: Any, language: str = "en") -> str:
        """Format price data naturally."""
        items = data if isinstance(data, list) else [data]
        if not items:
            return "No price data available."
        
        lines = ["PRICE INFORMATION:"]
        for i, item in enumerate(items[:20], 1):
            name = item.get("ItemName", "Unknown")
            code = item.get("ItemCode", "")
            price = item.get("Price")
            currency = item.get("Currency", "KES")
            price_list = item.get("PriceListName", "Standard")
            
            if price and price > 0:
                lines.append(f"{i}. {name} (Code: {code}) - {currency} {price:,.2f} [{price_list}]")
            else:
                lines.append(f"{i}. {name} (Code: {code}) - No price configured")
        
        return "\n".join(lines)
    
    def _format_customer_data_natural(self, data: Any, language: str = "en") -> str:
        """Format customer data naturally."""
        customers = data if isinstance(data, list) else [data]
        if not customers:
            return "No customer data available."
        
        lines = ["CUSTOMER INFORMATION:"]
        for customer in customers[:10]:
            name = customer.get('CardName', 'Unknown')
            code = customer.get('CardCode', 'N/A')
            phone = customer.get('Phone1', '')
            city = customer.get('City', '')
            credit_limit = customer.get('CreditLimit', 0)
            
            lines.append(f"• {name} (Code: {code})")
            if phone:
                lines.append(f"  Phone: {phone}")
            if city:
                lines.append(f"  Location: {city}")
            if credit_limit:
                lines.append(f"  Credit Limit: KES {credit_limit:,.2f}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_customer_segmentation_natural(self, data: Any, language: str = "en") -> str:
        """Format customer segmentation data naturally."""
        customers = data if isinstance(data, list) else [data]
        if not customers:
            return "No customer data available."
        
        lines = ["CUSTOMERS WHO BUY THIS PRODUCT:"]
        for i, cust in enumerate(customers[:15], 1):
            name = cust.get("CardName", "Unknown")
            code = cust.get("CardCode", "N/A")
            qty = cust.get("PurchaseQuantity", 0)
            last_purchase = cust.get("LastPurchaseDate", "")
            reason = cust.get("RecommendationReason", "")
            
            lines.append(f"{i}. {name} (Code: {code})")
            if qty > 0:
                lines.append(f"   Purchased: {qty:,.0f} units")
            if last_purchase:
                lines.append(f"   Last purchase: {last_purchase[:10]}")
            if reason:
                lines.append(f"   Why: {reason}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_top_selling_natural(self, data: Any, language: str = "en") -> str:
        """Format top selling items naturally."""
        items = data if isinstance(data, list) else [data]
        if not items:
            return "No top selling data available."
        
        lines = ["TOP SELLING ITEMS (ranked by popularity):"]
        for i, item in enumerate(items[:15], 1):
            name = item.get("ItemName", "Unknown")
            score = item.get("PopularityScore", 0)
            velocity = item.get("Velocity", "MEDIUM")
            
            velocity_icon = {"VERY_HIGH": "🔥🔥", "HIGH": "🔥", "MEDIUM": "📈", "LOW": "📉"}.get(velocity, "⭐")
            lines.append(f"{i}. {velocity_icon} {name} - Score: {score:.0f}/100")
        
        return "\n".join(lines)
    
    def _format_slow_moving_natural(self, data: Any, language: str = "en") -> str:
        """
        Format slow moving items naturally with severity, urgency, and recommendations.
        """
        items = data if isinstance(data, list) else [data]
        if not items:
            return "No slow moving data available."
        
        lines = ["SLOW MOVING ITEMS (need attention):"]
        lines.append("These items have low sales velocity and may require action:\n")
        
        for i, item in enumerate(items[:15], 1):
            # Get all fields
            item_name = item.get("ItemName", item.get("name", "Unknown"))
            item_code = item.get("ItemCode", item.get("code", ""))
            turnover = item.get("TurnoverRate", item.get("turnover", 0))
            on_hand = item.get("CurrentOnHand", item.get("on_hand", 0))
            committed = item.get("CurrentIsCommited", item.get("committed", 0))
            severity = item.get("Severity", item.get("severity", "monitor"))
            urgency = item.get("Urgency", item.get("urgency", ""))
            recommendation = item.get("Recommendation", item.get("recommendation", "Monitor sales"))
            days_since = item.get("DaysSinceLastTransaction", item.get("days_since", "N/A"))
            
            # Icon based on severity
            if severity == "critical":
                icon = "🔴 CRITICAL"
            elif severity == "warning":
                icon = "🟡 WARNING"
            else:
                icon = "🟢 MONITOR"
            
            lines.append(f"{i}. {icon} - {item_name}")
            if item_code:
                lines.append(f"   Code: {item_code}")
            lines.append(f"   Turnover rate: {turnover:.2f}x/year")
            if on_hand > 0:
                lines.append(f"   Current stock: {on_hand:,.0f} units")
            if committed > 0:
                lines.append(f"   Committed orders: {committed:,.0f} units")
            if days_since != "N/A" and days_since:
                lines.append(f"   Days since last transaction: {days_since}")
            if urgency:
                lines.append(f"   Urgency: {urgency}")
            lines.append(f"   Recommendation: {recommendation}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_warehouse_data_natural(self, data: Any, language: str = "en") -> str:
        """Format warehouse data naturally."""
        warehouses = data if isinstance(data, list) else [data]
        if not warehouses:
            return "No warehouse data available."
        
        lines = ["WAREHOUSE LOCATIONS:"]
        for wh in warehouses[:15]:
            code = wh.get("code", wh.get("WhsCode", "Unknown"))
            name = wh.get("name", wh.get("WhsName", "Unknown"))
            location = wh.get("location", "")
            total_items = wh.get("total_items", 0)
            total_units = wh.get("total_units", 0)
            
            lines.append(f"🏭 {name} (Code: {code})")
            if location:
                lines.append(f"   📍 Location: {location}")
            if total_items > 0:
                lines.append(f"   📊 Items: {total_items} | Total Units: {total_units:,.0f}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_low_stock_natural(self, data: Any, language: str = "en") -> str:
        """Format low stock alerts naturally."""
        items = data if isinstance(data, list) else [data]
        if not items:
            return "No low stock alerts at this time."
        
        lines = ["⚠️ LOW STOCK ALERTS:"]
        for item in items[:20]:
            name = item.get("name", item.get("ItemName", "Unknown"))
            code = item.get("code", item.get("ItemCode", ""))
            available = item.get("available", item.get("Available", 0))
            warehouse = item.get("warehouse", item.get("WhsCode", "Unknown"))
            alert_level = item.get("alert_level", "LOW")
            
            icon = {"CRITICAL": "🔴", "LOW": "🟡", "MEDIUM": "🟠"}.get(alert_level, "⚠️")
            lines.append(f"{icon} {name} (Code: {code})")
            lines.append(f"   🏭 Warehouse: {warehouse}")
            lines.append(f"   📦 Available: {available:,.0f} units")
            lines.append("")
        
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # Core Generation Methods
    # -----------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        max_tokens: int = 800,
        intent: str | None = None,
        db_context: Any = None,
        language: str | None = None,
        session_id: str | None = None,
        user_message: str = "",
    ) -> str:
        """Generate response with conversation context."""
        system_prompt = self._build_system_prompt(intent, db_context, language, session_id, user_message)

        # Try Gemini first if available and appropriate
        if self._gemini_available and self.provider in ["gemini", "auto"]:
            try:
                self._rate_limit()
                response = self._generate_gemini(system_prompt, prompt, max_tokens)
                if response:
                    # Clean response before returning
                    return self.clean_response(response)
            except Exception as e:
                logger.warning(f"Gemini generation failed: {e}")
                if self.provider == "gemini":
                    return self._handle_error(e, language)

        # Fallback to Groq
        if self._groq_client:
            try:
                response = self._generate_groq(system_prompt, prompt, max_tokens)
                # Clean response before returning
                return self.clean_response(response)
            except Exception as e:
                logger.error(f"Groq generation failed: {e}")
                return self._handle_error(e, language)

        # No provider available
        return self._handle_error(Exception("No LLM provider available"), language)

    def _generate_gemini(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        """
        Generate with new Gemini SDK (google-genai).
        
        Uses the updated API format with types.Content for messages.
        """
        try:
            # Combine system and user prompts for Gemini (which doesn't have native system prompt)
            combined_prompt = f"{system_prompt}\n\nUser: {user_prompt}"
            
            # Use the new API format
            response = self._gemini_client.models.generate_content(
                model=self._gemini_model,
                contents=combined_prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.7,
                    top_p=0.95,
                )
            )
            
            # Check for blocking
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logger.warning(f"Gemini blocked: {response.prompt_feedback.block_reason}")
                return "I'm unable to respond to that request."
            
            # Extract text from response
            if response.text:
                result = response.text.strip()
                logger.info(f"✅ Gemini response: {len(result)} chars")
                return result
            else:
                logger.warning("Gemini returned empty response")
                return None
                
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            raise

    def _generate_groq(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        """Generate with Groq."""
        logger.info(f"📡 Sending request to Groq...")

        response = self._groq_client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,  # Higher for more natural responses
            max_tokens=max_tokens,
        )

        result = response.choices[0].message.content
        tokens_used = response.usage.total_tokens if hasattr(response, "usage") else 0
        logger.info(f"✅ Groq response: {len(result)} chars, {tokens_used} tokens")
        return result

    # -----------------------------------------------------------------------
    # Async Methods
    # -----------------------------------------------------------------------

    async def generate_async(
        self,
        prompt: str,
        max_tokens: int = 800,
        intent: str | None = None,
        db_context: Any = None,
        language: str | None = None,
        session_id: str | None = None,
        user_message: str = "",
    ) -> str:
        """Generate response (async)."""
        return await asyncio.to_thread(
            self.generate, prompt, max_tokens, intent, db_context, language, session_id, user_message
        )

    async def narrate_async(
        self,
        question: str,
        db_rows: Any,
        intent: str = "GENERAL",
        max_tokens: int = 800,
        language: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Async version of narrate."""
        return await asyncio.to_thread(
            self.narrate, question, db_rows, intent, max_tokens, language, session_id
        )

    # -----------------------------------------------------------------------
    # Narrate Method (FIXED: preserves formatting)
    # -----------------------------------------------------------------------

    def narrate(
        self,
        question: str,
        db_rows: Any,
        intent: str = "GENERAL",
        max_tokens: int = 800,
        language: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Generate natural narrative from question and database rows."""
        lang = (language or "en").lower().strip()
        intent_upper = intent.upper()

        # No data - use conversational fallback
        if not db_rows or (isinstance(db_rows, list) and len(db_rows) == 0):
            if lang == "sw":
                fallback = _NO_DATA_FALLBACKS_SW.get(intent_upper)
            else:
                fallback = _NO_DATA_FALLBACKS_EN.get(intent_upper)

            if fallback:
                # Clean fallback response (preserves formatting)
                return self.clean_response(fallback)

            # Generic fallback
            return self._generate_no_data_response(question, intent, lang)

        # Build natural prompt
        item_count = self._count_items(db_rows)
        
        # Special handling for stock levels to ensure proper formatting
        if intent_upper == "GET_STOCK_LEVELS":
            formatted_data = self._format_stock_data_natural(db_rows, lang)
        else:
            formatted_data = self._format_context(db_rows, intent_upper, lang)
        
        user_prompt = f"""
The user asked: "{question}"

I found {item_count} item(s) in the database. Here's the data:

{formatted_data}

Please answer the user's question in a natural, conversational way. 
Be friendly and helpful. Use the data above - don't make anything up.
If there are multiple warehouses, show each warehouse separately.
If stock is negative (backorder), explain clearly.
Use bullet points or numbered lists for clarity.
Use **bold** for important numbers (prices, quantities, totals).
End by asking if they need anything else.
"""
        
        result = self.generate(
            user_prompt,
            max_tokens=max_tokens,
            intent=intent,
            db_context=db_rows,
            language=language,
            session_id=session_id,
            user_message=question,
        )
        
        # DON'T clean here - preserve formatting for the follow-up additions
        
        # Add helpful follow-up for certain intents
        if intent_upper == "GET_STOCK_LEVELS" and db_rows:
            if lang == "sw":
                result += "\n\n💡 Unataka kuangalia bidhaa nyingine au kuunda agizo la ununuzi?"
            else:
                result += "\n\n💡 Want to check another product or create a purchase order?"
        
        elif intent_upper == "GET_CUSTOMER_DETAILS" and db_rows:
            if lang == "sw":
                result += "\n\n💡 Je, ungependa kuona historia ya oda zao au kuunda nukuu?"
            else:
                result += "\n\n💡 Would you like to see their order history or create a quotation?"
        
        elif intent_upper == "GET_TOP_SELLING_ITEMS" and db_rows:
            if lang == "sw":
                result += "\n\n💡 Unataka kuangalia hisa za bidhaa hizi?"
            else:
                result += "\n\n💡 Want to check stock on any of these?"
        
        elif intent_upper == "GET_SLOW_MOVING_ITEMS" and db_rows:
            if lang == "sw":
                result += "\n\n💡 Je, ungependa nipendekeze promo kwa bidhaa hizi?"
            else:
                result += "\n\n💡 Would you like me to suggest promotions for these?"
        
        elif intent_upper == "CREATE_QUOTATION" and db_rows:
            if lang == "sw":
                result += "\n\n💡 Unahitaji nitumie nukuu hii kwa barua pepe?"
            else:
                result += "\n\n💡 Need me to email this quotation to the customer?"
        
        elif intent_upper == "FIND_CUSTOMERS_BY_ITEM" and db_rows:
            if lang == "sw":
                result += "\n\n💡 Unaweza kuuliza 'unda nukuu kwa wateja hawa' kutengeneza nukuu."
            else:
                result += "\n\n💡 You can ask 'create quotation for these customers' to generate quotes."
        
        elif intent_upper == "GET_WAREHOUSES" and db_rows:
            if lang == "sw":
                result += "\n\n💡 Unataka kuangalia hisa kwenye ghala fulani?"
            else:
                result += "\n\n💡 Want to check stock at a specific warehouse?"
        
        # Clean the final result once (preserves **bold** formatting)
        return self.clean_response(result)

    def _generate_no_data_response(self, question: str, intent: str, language: str) -> str:
        """Generate natural response when no data is found."""
        prompt = f"""
The user asked: "{question}"

No matching records were found in the Leysco100 system.

Provide a HELPFUL, POSITIVE response that:
1. Acknowledges their question
2. Explains no results were found (without being negative)
3. Offers practical suggestions
4. Ends by asking if they need help with something else

Use natural, conversational language. Be friendly and encouraging.
NEVER use words like 'unfortunately', 'sorry', 'alas', 'regrettably'.
Use **bold** for emphasis where appropriate.

Write in {'Swahili' if language == 'sw' else 'English'}.
"""
        result = self.generate(prompt, max_tokens=200, intent=intent, language=language)
        return self.clean_response(result)

    def _count_items(self, data: Any) -> int:
        """Count items in data."""
        if not data:
            return 0
        if isinstance(data, list):
            return len(data)
        return 1

    def _handle_error(self, e: Exception, language: str | None = None) -> str:
        """Handle errors gracefully with natural language."""
        error_msg = str(e)
        lang = (language or "en").lower().strip()

        if lang == "sw":
            if "429" in error_msg or "rate" in error_msg.lower():
                return "Samahani, msaidizi wa AI ana shughuli nyingi kwa sasa. Jaribu tena baada ya dakika chache. 😊"
            if "401" in error_msg or "auth" in error_msg.lower():
                return "Nina shida ya kuthibitisha akaunti. Tafadhali wasiliana na msimamizi wa mfumo."
            return "Nimekutana na tatizo la kiufundi. Tafadhali jaribu tena baadaye. 😊"
        else:
            if "429" in error_msg or "rate" in error_msg.lower():
                return "I'm handling many requests right now. Please try again in a moment. 😊"
            if "401" in error_msg or "auth" in error_msg.lower():
                return "I'm having trouble authenticating. Please check your configuration."
            return "I encountered a temporary issue. Please try again in a moment. 😊"

    # -----------------------------------------------------------------------
    # Utility Methods
    # -----------------------------------------------------------------------

    def test_connection(self) -> bool:
        """Test LLM connection."""
        try:
            response = self.generate("Reply with a friendly 'Ready to help!'", max_tokens=20)
            return response and len(response) > 0
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def get_provider_status(self) -> dict:
        """Get status of all providers."""
        return {
            "groq": self._groq_client is not None,
            "gemini": self._gemini_available,
            "active_provider": self._get_active_provider(),
            "rate_limit_remaining": "N/A"
        }


# ---------------------------------------------------------------------------
# Singleton Instance
# ---------------------------------------------------------------------------

_llm_instance: Optional[LLMService] = None


def get_llm_service(provider: str = "auto") -> LLMService:
    """Get or create LLM service instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMService(provider=provider)
    return _llm_instance


# Backward compatibility
class OllamaService:
    """Deprecated — kept for backward compatibility only."""
    def __init__(self, model_override: str | None = None):
        logger.warning("⚠️ OllamaService is deprecated, using LLMService instead")
        self.llm = get_llm_service()

    def generate(self, prompt: str, max_tokens: int = 500) -> str:
        return self.llm.generate(prompt, max_tokens)

    def test_connection(self) -> bool:
        return self.llm.test_connection()


# Global instance
llm_service = get_llm_service()