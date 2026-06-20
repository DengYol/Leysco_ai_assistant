"""Main LLMService class - orchestrates providers and formatters"""

import logging
import time
import asyncio
import re
from typing import Any, Optional, List, Dict
from datetime import datetime

from .constants import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    RATE_LIMIT_INTERVAL,
    NO_DATA_FALLBACKS_EN,
    NO_DATA_FALLBACKS_SW
)
from .utils import clean_response, count_items
from .memory import get_conversation_memory
from .prompts import get_prompt_builder
from .providers import GroqProvider, GeminiProvider
from .formatters import (
    StockFormatter,
    PriceFormatter,
    CustomerFormatter,
    WarehouseFormatter,
    AnalyticsFormatter
)

logger = logging.getLogger(__name__)


class LLMService:
    """
    Enhanced LLM service with natural language understanding,
    conversation memory, and flexible response generation.
    """

    def __init__(self, provider: str = "groq"):
        """
        Initialize LLM service.
        
        Args:
            provider: "groq" (default), "gemini", or "auto" 
                     Note: Default is now "groq" to avoid Gemini 404 errors
        """
        # Force to "groq" if set to "auto" to avoid Gemini errors
        if provider == "auto":
            provider = "groq"
            logger.info("Auto provider fallback: forcing Groq to avoid Gemini 404 errors")
        
        self.provider_choice = provider
        
        # Initialize only Groq provider by default
        self.groq_provider = GroqProvider() if provider in ["groq", "auto"] else None
        self.gemini_provider = None  # Completely disable Gemini to avoid 404 errors
        
        # Initialize formatters
        self.stock_formatter = StockFormatter()
        self.price_formatter = PriceFormatter()
        self.customer_formatter = CustomerFormatter()
        self.warehouse_formatter = WarehouseFormatter()
        self.analytics_formatter = AnalyticsFormatter()
        
        # Prompt builder
        self.prompt_builder = get_prompt_builder()
        
        # Rate limiting
        self._last_request_time = 0
        self._min_interval = RATE_LIMIT_INTERVAL
        
        # Metrics
        self._metrics = {
            "requests": 0,
            "errors": 0,
            "total_tokens": 0,
            "avg_response_time": 0
        }
        
        logger.info(f"✅ LLMService initialized with provider: {self._get_active_provider()}")

    def _get_active_provider(self) -> str:
        """Get the provider that will be used."""
        if self.groq_provider and self.groq_provider.is_available():
            return "groq"
        return "none"

    def _rate_limit(self):
        """Implement rate limiting for free tier."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            sleep_time = self._min_interval - elapsed
            logger.info(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _record_metrics(self, duration: float, tokens: int = 0):
        """Record request metrics."""
        self._metrics["requests"] += 1
        self._metrics["total_tokens"] += tokens
        current_avg = self._metrics["avg_response_time"]
        total_requests = self._metrics["requests"]
        self._metrics["avg_response_time"] = ((current_avg * (total_requests - 1)) + duration) / total_requests

    def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics."""
        return self._metrics.copy()

    def _format_db_context(self, db_context: Any, intent: str, language: str = "en") -> str:
        """Format database context for LLM using appropriate formatter."""
        if not db_context:
            return "No data available."
        
        intent_upper = intent.upper() if intent else ""
        
        # Route to appropriate formatter
        if intent_upper == "GET_STOCK_LEVELS":
            return self.stock_formatter.format(db_context, language)
        
        if intent_upper in ["GET_ITEM_PRICE", "GET_CUSTOMER_PRICE"]:
            return self.price_formatter.format(db_context, language)
        
        if intent_upper == "GET_CUSTOMER_DETAILS":
            return self.customer_formatter.format(db_context, language)
        
        if intent_upper == "FIND_CUSTOMERS_BY_ITEM":
            return self.customer_formatter.format_segmentation(db_context, language)
        
        if intent_upper == "GET_TOP_SELLING_ITEMS":
            return self.analytics_formatter.format_top_selling(db_context, language)
        
        if intent_upper == "GET_SLOW_MOVING_ITEMS":
            return self.analytics_formatter.format_slow_moving(db_context, language)
        
        if intent_upper == "GET_WAREHOUSES":
            return self.warehouse_formatter.format(db_context, language)
        
        if intent_upper == "GET_LOW_STOCK_ALERTS":
            return self.warehouse_formatter.format_low_stock(db_context, language)
        
        # Default formatting for other intents
        if isinstance(db_context, list):
            if len(db_context) > 20:
                db_context = db_context[:20]
                return f"Data: {db_context}\n... and {len(db_context)} total items"
            return f"Data: {db_context}"
        elif isinstance(db_context, dict):
            return f"Data: {db_context}"
        
        return str(db_context)

    def _get_no_data_response(self, intent: str, language: str) -> str:
        """Get no-data fallback response."""
        intent_upper = intent.upper() if intent else ""
        
        if language == "sw":
            fallback = NO_DATA_FALLBACKS_SW.get(intent_upper)
        else:
            fallback = NO_DATA_FALLBACKS_EN.get(intent_upper)
        
        if fallback:
            return clean_response(fallback)
        
        # Generic fallback
        if language == "sw":
            return clean_response("Samahani, sikuweza kupata taarifa ulizoomba. Tafadhali jaribu tena.")
        return clean_response("Sorry, I couldn't find the information you're looking for. Please try again.")

    def _clean_llm_response(self, text: str) -> str:
        """Clean LLM response to ensure no markdown or formatting issues."""
        if not text:
            return text
        
        # Remove markdown code blocks
        text = re.sub(r'```\w*\n?(.*?)\n?```', r'\1', text, flags=re.DOTALL)
        
        # Remove markdown bold and italic
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        
        # Remove markdown links
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # Remove any stray JSON-like patterns that might have been returned
        text = re.sub(r'\{"intent":\s*"[^"]+"\}', '', text)
        
        # Clean up extra whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        return text.strip()

    def generate(
        self,
        prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        intent: str | None = None,
        db_context: Any = None,
        language: str | None = None,
        session_id: str | None = None,
        user_message: str = "",
    ) -> str:
        """Generate response with conversation context."""
        # Format data if provided
        formatted_data = None
        if db_context:
            formatted_data = self._format_db_context(db_context, intent or "", language or "en")
        
        # Build system prompt
        system_prompt = self.prompt_builder.build(
            intent=intent,
            db_context=db_context,
            language=language,
            session_id=session_id,
            user_message=user_message,
            formatted_data=formatted_data
        )
        
        # Build user prompt
        if formatted_data:
            item_count = count_items(db_context)
            user_prompt = f"""
The user asked: "{prompt}"

I found {item_count} item(s) in the database. Here's the data:

{formatted_data}

Please answer the user's question in a natural, conversational way. 
Be friendly and helpful. Use the data above - don't make anything up.
Use bullet points or numbered lists for clarity.
IMPORTANT: DO NOT use any markdown formatting. Do not use **bold**, *italic*, or any other markdown. Use plain text only.
End by asking if they need anything else.
"""
        else:
            user_prompt = f'The user asked: "{prompt}"\n\nPlease provide a helpful response. IMPORTANT: DO NOT use any markdown formatting. Use plain text only. Do not use **bold** or *italic*.'

        start_time = time.time()
        self._rate_limit()
        
        response = None
        
        # Use Groq only (Gemini disabled)
        if self.groq_provider and self.groq_provider.is_available():
            try:
                response = self.groq_provider.generate(system_prompt, user_prompt, max_tokens)
                if response:
                    duration = time.time() - start_time
                    self._record_metrics(duration)
                    # Store in conversation memory
                    if session_id:
                        memory = get_conversation_memory()
                        memory.add_exchange(session_id, user_message or prompt[:500], response[:500])
                    # Clean the response
                    cleaned = self._clean_llm_response(response)
                    return cleaned
            except Exception as e:
                logger.error(f"Groq generation failed: {e}")
                return self._handle_error(e, language)
        
        # No provider available
        logger.error("No LLM provider available (Groq unavailable)")
        return self._handle_error(Exception("No LLM provider available"), language)

    async def generate_async(
        self,
        prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
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

    def narrate(
        self,
        question: str,
        db_rows: Any,
        intent: str = "GENERAL",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        language: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Generate natural narrative from question and database rows."""
        lang = (language or "en").lower().strip()
        intent_upper = intent.upper()
        
        # No data - use conversational fallback
        if not db_rows or (isinstance(db_rows, list) and len(db_rows) == 0):
            return self._get_no_data_response(intent, lang)
        
        # Generate narrative
        result = self.generate(
            question,
            max_tokens=max_tokens,
            intent=intent,
            db_context=db_rows,
            language=language,
            session_id=session_id,
            user_message=question
        )
        
        # Add helpful follow-up based on intent
        if self._should_add_followup(intent_upper, db_rows, lang):
            followup = self._get_followup_message(intent_upper, lang)
            result += followup
        
        return self._clean_llm_response(result)

    async def narrate_async(
        self,
        question: str,
        db_rows: Any,
        intent: str = "GENERAL",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        language: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Async version of narrate."""
        return await asyncio.to_thread(
            self.narrate, question, db_rows, intent, max_tokens, language, session_id
        )

    def _should_add_followup(self, intent: str, db_rows: Any, language: str) -> bool:
        """Check if follow-up message should be added."""
        if not db_rows:
            return False
        
        followup_intents = [
            "GET_STOCK_LEVELS", "GET_CUSTOMER_DETAILS", "GET_TOP_SELLING_ITEMS",
            "GET_SLOW_MOVING_ITEMS", "CREATE_QUOTATION", "FIND_CUSTOMERS_BY_ITEM",
            "GET_WAREHOUSES"
        ]
        return intent in followup_intents

    def _get_followup_message(self, intent: str, language: str) -> str:
        """Get follow-up message for intent."""
        followups = {
            "GET_STOCK_LEVELS": {
                "en": "\n\nWant to check another product or create a purchase order?",
                "sw": "\n\nUnataka kuangalia bidhaa nyingine au kuunda agizo la ununuzi?"
            },
            "GET_CUSTOMER_DETAILS": {
                "en": "\n\nWould you like to see their order history or create a quotation?",
                "sw": "\n\nJe, ungependa kuona historia ya oda zao au kuunda nukuu?"
            },
            "GET_TOP_SELLING_ITEMS": {
                "en": "\n\nWant to check stock on any of these?",
                "sw": "\n\nUnataka kuangalia hisa za bidhaa hizi?"
            },
            "GET_SLOW_MOVING_ITEMS": {
                "en": "\n\nWould you like me to suggest promotions for these?",
                "sw": "\n\nJe, ungependa nipendekeze promo kwa bidhaa hizi?"
            },
            "CREATE_QUOTATION": {
                "en": "\n\nNeed me to email this quotation to the customer?",
                "sw": "\n\nUnahitaji nitumie nukuu hii kwa barua pepe?"
            },
            "FIND_CUSTOMERS_BY_ITEM": {
                "en": "\n\nYou can ask 'create quotation for these customers' to generate quotes.",
                "sw": "\n\nUnaweza kuuliza 'unda nukuu kwa wateja hawa' kutengeneza nukuu."
            },
            "GET_WAREHOUSES": {
                "en": "\n\nWant to check stock at a specific warehouse?",
                "sw": "\n\nUnataka kuangalia hisa kwenye ghala fulani?"
            }
        }
        
        followup = followups.get(intent, {})
        return followup.get(language, followup.get("en", ""))

    def _handle_error(self, e: Exception, language: str | None = None) -> str:
        """Handle errors gracefully with natural language."""
        error_msg = str(e)
        lang = (language or "en").lower().strip()

        if lang == "sw":
            if "429" in error_msg or "rate" in error_msg.lower():
                return "Samahani, msaidizi wa AI ana shughuli nyingi kwa sasa. Jaribu tena baada ya dakika chache."
            if "401" in error_msg or "auth" in error_msg.lower():
                return "Nina shida ya kuthibitisha akaunti. Tafadhali wasiliana na msimamizi wa mfumo."
            if "404" in error_msg or "not found" in error_msg.lower():
                return "Samahani, huduma ya AI haipatikani kwa sasa. Jaribu tena baadaye."
            return "Nimekutana na tatizo la kiufundi. Tafadhali jaribu tena baadaye."
        else:
            if "429" in error_msg or "rate" in error_msg.lower():
                return "I'm handling many requests right now. Please try again in a moment."
            if "401" in error_msg or "auth" in error_msg.lower():
                return "I'm having trouble authenticating. Please check your configuration."
            if "404" in error_msg or "not found" in error_msg.lower():
                return "Sorry, the AI service is currently unavailable. Please try again later."
            return "I encountered a temporary issue. Please try again in a moment."

    def test_connection(self) -> bool:
        """Test LLM connection."""
        try:
            response = self.generate("Reply with a friendly 'Ready to help!'", max_tokens=20)
            return response is not None and len(response) > 0
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def get_provider_status(self) -> dict:
        """Get status of all providers."""
        return {
            "groq": self.groq_provider.is_available() if self.groq_provider else False,
            "gemini": False,  # Gemini is disabled
            "active_provider": self._get_active_provider(),
            "metrics": self._metrics
        }

    def clear_history(self, session_id: str):
        """Clear conversation history for a session."""
        memory = get_conversation_memory()
        memory.clear(session_id)


# Singleton instance
_llm_instance: Optional[LLMService] = None


def get_llm_service(provider: str = "groq") -> LLMService:
    """Get or create LLM service instance."""
    global _llm_instance
    if _llm_instance is None:
        # Force to groq to avoid Gemini issues
        if provider == "auto":
            provider = "groq"
        _llm_instance = LLMService(provider=provider)
    return _llm_instance
