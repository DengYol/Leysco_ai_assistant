"""
app/services/llm_service.py
============================
LLM Service using Groq API — Leysco100 Context-Aware Edition

Features:
- Dynamic system prompts based on intent
- DB context injection (pass query results directly)
- Separate generate() and chat() methods
- Graceful fallback messages
- Intent-specific tone and instructions

Performance:
- Groq: 1-3 seconds per request ⚡
- Get free API key: https://console.groq.com/
"""

import json
import logging
from groq import Groq
from app.core.config import settings
from app.ai_engine.leysco_knowledge_base import get_knowledge

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1.  COMPANY PROFILE — edit this to match Leysco
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

Key Departments (Leysco100 client): Sales, Finance, Procurement, HR, Warehouse, IT
"""

# ---------------------------------------------------------------------------
# 2.  INTENT → SYSTEM PROMPT MAPPING
# ---------------------------------------------------------------------------

INTENT_SYSTEM_PROMPTS: dict[str, str] = {
    "COMPANY_INFO": (
        "You answer questions about Leysco company structure, employees, "
        "departments, and roles. Use ONLY the data provided. "
        "If data is missing, say so clearly — never guess."
    ),
    "INVENTORY": (
        "You answer inventory and stock questions for Leysco. "
        "Always mention item codes, quantities, and warehouse locations "
        "when available in the data. Be precise with numbers."
    ),
    "GET_ITEM_PRICE": (
        "You answer item price questions for Leysco sales reps. "
        "Always state: item name, final price, currency (KES), and price source. "
        "If a volume discount or manual discount was applied, mention it clearly. "
        "Format: 'ItemName costs KES X (PriceSource). Reason: ...' "
        "Be concise — one line per item."
    ),
    "GET_CUSTOMER_PRICE": (
        "You answer customer-specific pricing questions for Leysco sales reps. "
        "Always state: item name, customer name, final price, currency (KES), and price source. "
        "Highlight if a special price or discount is active. "
        "Format: 'For [Customer], ItemName costs KES X (PriceSource).' "
        "Be concise — one line per item."
    ),
    "GET_ITEM_BASE_PRICE": (
        "You answer base price questions for Leysco. "
        "State the default list price clearly with currency. "
        "Note if no customer-specific pricing is applied."
    ),
    "PRODUCTS": (
        "You answer product-related questions including pricing, descriptions, "
        "and availability. Use the provided product data only."
    ),
    "POLICIES": (
        "You answer questions about Leysco company policies and procedures. "
        "Be clear and professional. If a policy is not in the data, "
        "direct the user to HR or their department head."
    ),
    "GENERAL": (
        "You are a general-purpose assistant for Leysco staff. "
        "Be helpful, concise, and professional. "
        "For company-specific data questions, let the user know "
        "you may need to look that up in the system."
    ),
    "UNKNOWN": (
        "You are a helpful assistant for Leysco. "
        "The user's request was unclear. Politely ask for clarification "
        "or suggest what kinds of questions you can answer."
    ),
}

DEFAULT_SYSTEM_PROMPT = INTENT_SYSTEM_PROMPTS["GENERAL"]

# ---------------------------------------------------------------------------
# 3.  LLM SERVICE CLASS
# ---------------------------------------------------------------------------

class LLMService:
    """
    LLM service using Groq API.

    Groq provides free access to Llama 3.x models with:
    - 30 requests/minute (free tier)
    - ~200 tokens/second generation speed
    - No GPU required
    """

    def __init__(self, model_override: str | None = None):
        self.api_key = settings.GROQ_API_KEY

        if not self.api_key:
            logger.error("❌ GROQ_API_KEY not found in environment!")
            logger.error("   Add to .env file: GROQ_API_KEY=gsk_your_key_here")
            raise ValueError("GROQ_API_KEY environment variable not set")

        try:
            self.client = Groq(api_key=self.api_key)
        except Exception as e:
            logger.error(f"❌ Failed to initialize Groq client: {e}")
            raise

        # Model: reads from settings.GROQ_MODEL (set in .env)
        self.model = model_override or settings.GROQ_MODEL

        logger.info("✅ Groq LLM initialized")
        logger.info(f"   Model: {self.model}")
        logger.info(f"   API Key: {self.api_key[:10]}********")

    # -----------------------------------------------------------------------
    # CORE: build system prompt dynamically
    # -----------------------------------------------------------------------

    def _build_system_prompt(
        self,
        intent: str | None = None,
        db_context: list | dict | str | None = None,
    ) -> str:
        """
        Compose a system prompt from:
        - Leysco company profile
        - Intent-specific instructions
        - Live DB data (optional)
        """

        # Base identity
        parts = [
            f"You are a helpful AI assistant for Leysco Limited, "
            f"an agricultural company in Kenya.\n",
            f"--- COMPANY PROFILE ---\n{LEYSCO_PROFILE}\n",
        ]

        # Intent-specific instructions
        intent_key = (intent or "GENERAL").upper()
        intent_instruction = INTENT_SYSTEM_PROMPTS.get(
            intent_key, DEFAULT_SYSTEM_PROMPT
        )
        parts.append(f"--- YOUR ROLE FOR THIS QUESTION ---\n{intent_instruction}\n")

        # Inject knowledge base content for knowledge intents
        kb_content = get_knowledge(intent_key)
        if kb_content and intent_key not in ("GENERAL", "UNKNOWN"):
            parts.append(f"--- LEYSCO KNOWLEDGE BASE ---\n{kb_content}\n")

        # Inject DB data if provided
        if db_context:
            if isinstance(db_context, (list, dict)):
                context_str = json.dumps(db_context, indent=2, default=str)
            else:
                context_str = str(db_context)

            parts.append(
                f"--- LEYSCO100 SYSTEM DATA ---\n"
                f"The following data was retrieved from the Leysco100 database:\n"
                f"{context_str}\n"
                f"Base your answer on this data. Do NOT invent values not shown above.\n"
            )
        else:
            parts.append(
                "--- NOTE ---\n"
                "No database records were retrieved for this query.\n"
                "IMPORTANT RULES when no data is found:\n"
                "1. Do NOT suggest contacting info@leysco.com or any external email for pricing/stock queries\n"
                "2. Do NOT suggest contacting procurement or IT for pricing questions\n"
                "3. DO suggest the user try a different search term or item name\n"
                "4. DO suggest checking the system with a broader query\n"
                "5. Keep the response short and actionable — 2-3 sentences max\n"
            )

        parts.append("Always be concise, accurate, and professional.")

        return "\n".join(parts)

    # -----------------------------------------------------------------------
    # generate() — simple single-turn prompt (backward compatible)
    # -----------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        max_tokens: int = 500,
        intent: str | None = None,
        db_context: list | dict | str | None = None,
    ) -> str:
        """
        Generate a response to a single prompt.
        Optionally inject intent + DB context for company-aware answers.

        Args:
            prompt:      The user's question or instruction.
            max_tokens:  Max response length.
            intent:      Detected intent (e.g. 'INVENTORY', 'COMPANY_INFO').
            db_context:  Data from Leysco100 DB relevant to this query.

        Returns:
            LLM response string.
        """
        system_prompt = self._build_system_prompt(intent, db_context)

        try:
            logger.info("📡 Sending request to Groq...")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.4,   # Lower = more factual for business use
                max_tokens=max_tokens,
                top_p=1,
                stream=False,
            )

            result = response.choices[0].message.content
            tokens_used = (
                response.usage.total_tokens if hasattr(response, "usage") else 0
            )

            logger.info("✅ Groq response received")
            logger.info(f"   Length: {len(result)} chars")
            logger.info(f"   Tokens: {tokens_used}")

            return result

        except Exception as e:
            return self._handle_error(e)

    # -----------------------------------------------------------------------
    # chat() — multi-turn conversation support
    # -----------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 500,
        intent: str | None = None,
        db_context: list | dict | str | None = None,
    ) -> str:
        """
        Multi-turn chat with full conversation history.

        Args:
            messages:    List of {"role": "user"|"assistant", "content": "..."}
            max_tokens:  Max response length.
            intent:      Detected intent for this turn.
            db_context:  DB data to inject for this turn.

        Returns:
            LLM response string.

        Example:
            history = [
                {"role": "user",      "content": "How many bags of urea do we have?"},
                {"role": "assistant", "content": "We have 340 bags in Warehouse A."},
                {"role": "user",      "content": "What about warehouse B?"},
            ]
            answer = llm.chat(history, intent="INVENTORY", db_context=db_rows)
        """
        system_prompt = self._build_system_prompt(intent, db_context)

        try:
            logger.info("📡 Sending chat request to Groq...")

            full_messages = [{"role": "system", "content": system_prompt}] + messages

            response = self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                temperature=0.4,
                max_tokens=max_tokens,
                top_p=1,
                stream=False,
            )

            result = response.choices[0].message.content
            tokens_used = (
                response.usage.total_tokens if hasattr(response, "usage") else 0
            )

            logger.info("✅ Groq chat response received")
            logger.info(f"   Intent: {intent or 'GENERAL'}")
            logger.info(f"   DB context rows: {len(db_context) if isinstance(db_context, list) else ('yes' if db_context else 'none')}")
            logger.info(f"   Tokens: {tokens_used}")

            return result

        except Exception as e:
            return self._handle_error(e)

    # -----------------------------------------------------------------------
    # narrate() — convenience: takes raw DB rows + question → answer
    # -----------------------------------------------------------------------

    # Intent-specific fallback messages when DB returns no results
    _NO_DATA_FALLBACKS = {
        "GET_ITEM_PRICE":       "I couldn't find a price for that item in Leysco100. Try searching with the exact item name or code (e.g. 'Price of VegiMax'). You can also ask 'Show me items' to browse the catalogue.",
        "GET_CUSTOMER_PRICE":   "I couldn't find a customer-specific price for that combination. Check the item name and customer name are correct, or ask 'Show me customers' to confirm the customer.",
        "GET_ITEM_BASE_PRICE":  "I couldn't find a base price for that item. Try 'Show me items' to see available products and their codes.",
        "GET_ITEMS":            "No items matched that search in Leysco100. Try a shorter or different product name, or ask 'Show me all items' for the full catalogue.",
        "GET_STOCK_LEVELS":     "I couldn't find stock information for that item. Check the item name or try 'Show me all items' to browse available products.",
        "GET_CUSTOMERS":        "No customers matched that search. Try using a partial name or ask 'Show me all customers' for the full list.",
        "GET_CUSTOMER_DETAILS": "I couldn't find that customer in Leysco100. Check the spelling or try 'Show me customers' to browse the list.",
        "GET_CUSTOMER_ORDERS":  "No orders found for that customer. Confirm the customer name is correct or check with your sales manager.",
        "GET_CUSTOMER_INVOICES":"No invoices found for that customer. Confirm the customer name or contact the Finance department.",
        "GET_QUOTATIONS":       "No quotations found. Try 'Create a quote for [customer] — [qty] [item]' to make a new one.",
        "GET_WAREHOUSES":       "No warehouses found in the system. Contact your IT administrator to check the Leysco100 configuration.",
        "GET_WAREHOUSE_STOCK":  "No stock data found for that warehouse. Check the warehouse name or try 'Show me warehouses' for a list.",
        "GET_LOW_STOCK_ALERTS": "No low stock alerts at the moment. All stock levels appear to be within normal ranges.",
        "GET_OUTSTANDING_DELIVERIES": "No outstanding deliveries found. All deliveries may be up to date.",
        "GET_DELIVERY_HISTORY": "No delivery history found for that query. Try specifying a customer name.",
    }

    def narrate(
        self,
        question: str,
        db_rows: list | dict | None,
        intent: str = "GENERAL",
        max_tokens: int = 400,
    ) -> str:
        """
        Highest-level method: pass a question + raw DB data,
        get a human-friendly answer back.

        Uses intent-specific fallback messages when DB returns no results,
        so the LLM never reaches for unrelated contact info.
        """
        if not db_rows:
            # Use a specific, actionable fallback per intent
            fallback = self._NO_DATA_FALLBACKS.get(intent.upper())
            if fallback:
                logger.info(f"   No DB data — using intent fallback for {intent}")
                return fallback

            # Generic fallback for unmapped intents — tightly scoped,
            # no mention of external contacts
            no_data_prompt = (
                f"The user asked: '{question}'\n\n"
                f"No matching records were found in the Leysco100 system for this query.\n"
                f"Inform the user briefly and suggest they:\n"
                f"1. Check the spelling of the item/customer name\n"
                f"2. Try a broader search term\n"
                f"3. Ask their sales manager if the item exists in the system\n"
                f"Do NOT mention any email addresses or external contacts."
            )
            return self.generate(no_data_prompt, max_tokens=150, intent=intent)

        user_prompt = (
            f"Based on the Leysco100 data provided, please answer this question:\n\n"
            f"Question: {question}\n\n"
            f"Give a clear, concise answer using the data. "
            f"Mention specific names, numbers, or codes where relevant."
        )

        return self.generate(
            user_prompt,
            max_tokens=max_tokens,
            intent=intent,
            db_context=db_rows,
        )

    # -----------------------------------------------------------------------
    # Error handling
    # -----------------------------------------------------------------------

    def _handle_error(self, e: Exception) -> str:
        error_msg = str(e)

        if "401" in error_msg or "unauthorized" in error_msg.lower():
            logger.error("❌ Invalid API key! Check your GROQ_API_KEY")
            return "Authentication error. Please contact your system administrator."

        elif "429" in error_msg or "rate limit" in error_msg.lower():
            logger.error("❌ Rate limit exceeded (30 requests/minute on free tier)")
            return "The AI assistant is busy right now. Please try again in a moment."

        elif "404" in error_msg or "model_not_found" in error_msg.lower():
            logger.error(f"❌ Model not found: {self.model}")
            logger.error("   Valid models: llama-3.1-8b-instant, llama3-8b-8192, mixtral-8x7b-32768")
            return "AI model configuration error. Please contact your system administrator."

        else:
            logger.error(f"❌ Groq API error: {error_msg}")
            return "I encountered an error processing your request. Please try again."

    # -----------------------------------------------------------------------
    # Connection test
    # -----------------------------------------------------------------------

    def test_connection(self) -> bool:
        try:
            logger.info("🔍 Testing Groq connection...")
            response = self.generate("Reply with the single word: ready", max_tokens=10)
            if response and len(response) > 0:
                logger.info(f"✅ Connection test passed: '{response.strip()}'")
                return True
            logger.warning("⚠️ Connection test returned empty response")
            return False
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            return False


# ---------------------------------------------------------------------------
# Backward compatibility alias
# ---------------------------------------------------------------------------

class OllamaService:
    """Deprecated — kept for backward compatibility only."""

    def __init__(self, model_override: str | None = None):
        logger.warning("⚠️ OllamaService is deprecated, using Groq instead")
        self.llm = LLMService(model_override=model_override)

    def generate(self, prompt: str, max_tokens: int = 500) -> str:
        return self.llm.generate(prompt, max_tokens)

    def test_connection(self) -> bool:
        return self.llm.test_connection()