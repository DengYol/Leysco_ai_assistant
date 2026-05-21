"""Main EntityExtractor class - orchestrates all extraction rules"""

import re
import logging
import json
import asyncio
from typing import Optional, Dict, List, Any
from functools import lru_cache

from .constants import SIZE_PATTERNS, COMMON_SIZES
from .swahili import is_swahili_query, normalize_swahili_text, translate_date
from .fuzzy import FuzzyMatcher
from .context import ContextEnhancer
from .rules import (
    CustomerRules,
    ItemRules,
    WarehouseRules,
    QuantityRules,
    DateRules,
    IntentRules,
    clean_customer_name,
    clean_customer_search_term
)
from app.services.llm_service import LLMService
from app.ai_engine.prompt_manager import PromptManager
from app.services.cache_service import cache_service
from app.services.leysco_api.client import LeyscoAPIService, create_api_service

logger = logging.getLogger(__name__)


def normalize_size(size_str: str) -> str:
    """Normalize size string to a standard format for comparison."""
    if not size_str:
        return ""
    normalized = re.sub(r'\s+', '', size_str.lower())
    normalized = re.sub(r'ml$', 'ml', normalized)
    normalized = re.sub(r'kg$', 'kg', normalized)
    normalized = re.sub(r'g$', 'g', normalized)
    normalized = re.sub(r'l$', 'l', normalized)
    return normalized


class EntityExtractor:
    """
    Smart Hybrid Entity Extraction Engine.
    Rule-first for speed, AI fallback for intelligence.
    Enhanced with context awareness and Swahili support.
    """

    def __init__(self, user_token: str = None):
        """
        Initialize EntityExtractor with optional user token.
        
        Args:
            user_token: Optional user token for API access
        """
        self.user_token = user_token
        self.llm = LLMService()
        self.prompt_manager = PromptManager()
        self.fuzzy_matcher = None  # Lazy initialized with API service
        self.context_enhancer = ContextEnhancer()
        self._api_service = None
        self._extract_cache = {}
        self._extract_cache_ttl = 300
        self._customers_fetched = False

    def set_user_token(self, token: str):
        """Update user token for API access."""
        self.user_token = token
        if self._api_service:
            self._api_service.set_user_token(token)

    @property
    def api_service(self):
        """Lazy load API service to avoid circular imports."""
        if self._api_service is None:
            # Use LeyscoAPIService from client
            self._api_service = create_api_service(user_token=self.user_token)
            # Initialize fuzzy matcher with API service
            self.fuzzy_matcher = FuzzyMatcher(self._api_service)
        return self._api_service

    async def _ensure_customer_cache(self):
        """Ensure customer cache is populated for fuzzy matching."""
        if self.fuzzy_matcher and not self._customers_fetched:
            try:
                # Fetch customers from API
                customers = self.api_service.get_all_customers(limit=500)
                if customers:
                    self.fuzzy_matcher.refresh_customer_cache(customers)
                    self._customers_fetched = True
                    logger.info(f"Customer cache populated with {len(customers)} customers")
                else:
                    logger.warning("No customers found to populate cache")
            except Exception as e:
                logger.error(f"Failed to fetch customers for fuzzy matching: {e}")

    async def _resolve_customer_with_fuzzy_match(self, customer_name: str) -> tuple:
        """Resolve customer name using fuzzy matching."""
        if not self.fuzzy_matcher or not customer_name:
            return customer_name, None
        
        # Ensure cache is populated
        await self._ensure_customer_cache()
        
        # Find the best match
        best_match = self.fuzzy_matcher.get_closest_customer(customer_name, threshold=65)
        
        if best_match:
            actual_name = best_match.get('CardName')
            card_code = best_match.get('CardCode')
            logger.info(f"Fuzzy matched '{customer_name}' → '{actual_name}' (Code: {card_code})")
            return actual_name, best_match
        
        logger.debug(f"No fuzzy match found for '{customer_name}'")
        return customer_name, None

    def _should_skip_ai(self, text: str) -> bool:
        """Determine if we should skip AI extraction for generic queries."""
        words = text.lower().split()
        generic_patterns = [
            "show items", "list items", "show customers",
            "list customers", "show invoices", "recommend items",
            "forecast demand", "predict sales", "demand forecast",
            "onyesha bidhaa", "orodhesha bidhaa", "onyesha wateja",
        ]
        if len(words) <= 3:
            return True
        return any(p in text.lower() for p in generic_patterns)

    @lru_cache(maxsize=256)
    def _rule_based_entities_cached(self, text: str) -> dict:
        """Cached version of rule-based entity extraction."""
        return self._rule_based_entities_impl(text)

    def _rule_based_entities_impl(self, text: str) -> dict:
        """Implementation of rule-based entity extraction with Swahili support."""
        
        # Normalize Swahili text first if needed
        is_swahili = is_swahili_query(text)
        if is_swahili:
            normalized_text = normalize_swahili_text(text)
            logger.info(f"Normalized Swahili text: '{text}' -> '{normalized_text}'")
        else:
            normalized_text = text
        
        text_lower = normalized_text.lower()
        original_text = text

        # Detect query types
        is_info = IntentRules.is_info_query(normalized_text)
        is_forecast = IntentRules.is_forecast_query(normalized_text)
        is_competitor_pricing = IntentRules.is_competitor_pricing_query(normalized_text)
        is_recommendation = IntentRules.is_recommendation_query(normalized_text)
        is_seasonal = IntentRules.is_seasonal_query(normalized_text)
        is_listing = CustomerRules.is_listing_query(normalized_text)
        is_best_price = IntentRules.is_best_price_query(text_lower)
        is_compare = IntentRules.is_compare_query(text_lower)
        is_price_alert = IntentRules.is_price_alert_query(text_lower)

        # Extract month for seasonal queries
        month = None
        if is_seasonal:
            month = DateRules.extract_month(normalized_text)
            logger.info(f"Seasonal query detected with month: {month}")

        # Extract quantity
        quantity = QuantityRules.extract_quantity(text_lower, is_seasonal)
        listing_limit = QuantityRules.extract_listing_limit(normalized_text, is_listing)
        if listing_limit and not quantity:
            quantity = listing_limit

        # Clean text for entity extraction
        cleaned_text = QuantityRules.clean_text_for_entities(text_lower)

        # Extract date
        date_value = DateRules.extract_date(text_lower)
        if date_value:
            date_value = translate_date(date_value)

        # Extract warehouse (skip for churn/health queries)
        warehouse = WarehouseRules.extract_warehouse(text)

        # Extract detail mode flag
        detail_mode = bool(
            re.search(r"\b(detail|details|spec|specs|information|info|about|maelezo|taarifa)\b", text_lower)
        )

        # Extract customer name
        customer_name = CustomerRules.extract_customer_name(
            original_text, 
            is_listing=is_listing, 
            is_competitor_pricing=is_competitor_pricing
        )

        # Extract item name and items list for quotations
        item_name = None
        items_list = []
        detected_size = None
        exact_size_match_required = False

        # Handle quotation-specific extraction
        if 'quotation' in text_lower or 'quote' in text_lower or 'nukuu' in text_lower:
            item_name, items_list, detected_size, exact_size_match_required = \
                ItemRules.extract_quotation_items(original_text, customer_name, self.api_service)
        
        # If not found in quotation, try regular item extraction
        if not item_name and not items_list:
            item_name, detected_size, exact_size_match_required = \
                ItemRules.extract_item_name(text_lower, cleaned_text, is_recommendation, self.api_service)

        # Clean item name
        if item_name:
            item_name = re.sub(
                r"\b(item|product|details?|specs?|info|for|of|to|with|price|cost|the|a|an|bidhaa|mazao|bei|gharama)\b",
                "", item_name, flags=re.IGNORECASE
            ).strip()

            # If item looks like a company, move to customer
            if CustomerRules.looks_like_company(item_name) and not ItemRules.is_product_name(item_name):
                logger.info(f"Item '{item_name}' looks like company — moving to customer_name")
                if not customer_name:
                    customer_name = item_name
                item_name = None

        # Extract from "for [company]" patterns (fallback)
        if not customer_name and not is_listing and not is_competitor_pricing:
            for_company_match = re.search(r'(?:for|kwa)\s+([A-Z][a-zA-Z0-9\s&\-.]+)$', original_text)
            if for_company_match:
                potential_customer = for_company_match.group(1).strip()
                if CustomerRules.looks_like_company(potential_customer) or CustomerRules.is_customer_code(potential_customer):
                    customer_name = potential_customer

        # Set default forecast days
        if is_forecast and not quantity:
            quantity = 30

        # Build result
        result = {
            "item_name": item_name if item_name else None,
            "base_item_name": None,
            "customer_name": customer_name if customer_name else None,
            "quantity": quantity,
            "warehouse": warehouse,
            "date": date_value,
            "detail_mode": detail_mode,
            "_is_listing": is_listing,  # Store for later use
        }
        
        if items_list:
            result["items"] = items_list
        if detected_size:
            result["_detected_size"] = detected_size
            result["_exact_size_required"] = exact_size_match_required
            result["_normalized_size"] = normalize_size(detected_size)

        return result

    def _rule_based_entities(self, text: str) -> dict:
        """Wrapper for cached rule-based entity extraction."""
        return self._rule_based_entities_cached(text)

    async def extract_async(self, user_message: str, initial_entities: dict = None, context: dict = None) -> dict:
        """
        Extract entities from user message with async support, caching, and context awareness.
        Current message ALWAYS takes priority over session entities.
        """
        # Step 1: Check cache
        cache_key = f"entities:{user_message}"
        cached = await cache_service.get_simple_async(cache_key)
        if cached and not initial_entities and not context:
            logger.debug(f"Entities cache hit: {user_message[:50]}...")
            return cached

        # Step 2: Extract fresh entities from current message
        fresh_entities = self._rule_based_entities(user_message)
        logger.debug(f"Fresh entities from current message: {fresh_entities}")

        # Step 3: Enhance with conversation context
        if context:
            fresh_entities = self.context_enhancer.enhance_with_context(fresh_entities, context, user_message)
            logger.debug(f"Entities after context enhancement: {fresh_entities}")

        # Step 4: Check if this is a pronoun query
        is_pronoun_query = self.context_enhancer.is_pronoun_query(user_message)
        
        # Get is_listing from fresh_entities (set in _rule_based_entities)
        is_listing = fresh_entities.get("_is_listing", False)

        # Step 5: Merge with session entities if provided
        if initial_entities:
            logger.debug(f"Session entities available: {initial_entities}")
            merged_entities = fresh_entities.copy()

            if is_pronoun_query and not fresh_entities.get("customer_name"):
                if initial_entities.get("customer_name"):
                    merged_entities["customer_name"] = initial_entities.get("customer_name")
                    merged_entities["_resolved_from_session"] = True
                    logger.info(f"Resolved pronoun to session customer: {merged_entities['customer_name']}")
                elif initial_entities.get("item_name"):
                    merged_entities["item_name"] = initial_entities.get("item_name")
                    merged_entities["_resolved_from_session"] = True
                    logger.info(f"Resolved pronoun to session item: {merged_entities['item_name']}")

            for key, value in initial_entities.items():
                if key.startswith('_'):
                    continue
                if key not in merged_entities or not merged_entities.get(key):
                    merged_entities[key] = value
                    logger.debug(f"Filled gap from session: {key}={value}")

            for key, value in initial_entities.items():
                if key.startswith('_') and key not in merged_entities:
                    merged_entities[key] = value

            rule_entities = merged_entities
        else:
            rule_entities = fresh_entities

        # Step 6: Apply fuzzy correction for items
        if self.fuzzy_matcher:
            raw_item = rule_entities.get("item_name")
            if raw_item:
                corrected_item = self.fuzzy_matcher.correct_item_typo(raw_item)
                if corrected_item != raw_item:
                    rule_entities["item_name"] = corrected_item
                    rule_entities["_item_corrected_from"] = raw_item
                    logger.info(f"Item fuzzy corrected: '{raw_item}' → '{corrected_item}'")

        # Step 7: Apply fuzzy matching for customer names (IMPORTANT!)
        raw_customer = rule_entities.get("customer_name")
        if raw_customer and not is_listing and not is_pronoun_query:
            # Try to resolve with fuzzy matching
            resolved_customer, customer_data = await self._resolve_customer_with_fuzzy_match(raw_customer)
            
            if resolved_customer and resolved_customer != raw_customer:
                rule_entities["customer_name"] = resolved_customer
                rule_entities["_customer_corrected_from"] = raw_customer
                rule_entities["_customer_code"] = customer_data.get('CardCode') if customer_data else None
                logger.info(f"Customer fuzzy corrected: '{raw_customer}' → '{resolved_customer}'")
            elif resolved_customer:
                # Even if no change, store the code if available
                if customer_data:
                    rule_entities["_customer_code"] = customer_data.get('CardCode')
                logger.debug(f"Customer name verified: '{resolved_customer}'")

        rule_entities["_original_query"] = user_message

        # Step 8: Remove internal flags before returning
        result_entities = {k: v for k, v in rule_entities.items() if not k.startswith('_') or k == "_original_query"}
        result_entities["_is_listing"] = is_listing  # Keep for context

        # Step 9: Return if we have entities
        if any([
            result_entities.get("item_name"),
            result_entities.get("customer_name"),
            result_entities.get("warehouse"),
            result_entities.get("quantity"),
            result_entities.get("detail_mode"),
        ]):
            logger.info(f"Entities detected: {result_entities}")
            await cache_service.set_simple_async(cache_key, result_entities, ttl=300)
            return result_entities

        # Step 10: Skip AI for generic queries
        if self._should_skip_ai(user_message):
            logger.info("Skipping AI entity extraction — generic query")
            await cache_service.set_simple_async(cache_key, result_entities, ttl=60)
            return result_entities

        # Step 11: AI fallback for complex queries
        try:
            if context and context.get("last_intent"):
                context_info = f"\nPrevious conversation context: User was asking about {context.get('last_intent')}. "
                if context.get("referenced_items"):
                    context_info += f"Previous items mentioned: {[i.get('name') for i in context['referenced_items'][:3]]}. "
                prompt = self.prompt_manager.get_entity_prompt(user_message) + context_info
            else:
                prompt = self.prompt_manager.get_entity_prompt(user_message)
                
            response = await self.llm.generate_async(prompt, max_tokens=150)

            json_text = self._extract_json(response)
            if not json_text:
                raise ValueError("No JSON found in AI response")

            entities = json.loads(json_text)

            structured = {
                "item_name": entities.get("item_name"),
                "customer_name": entities.get("customer_name"),
                "quantity": entities.get("quantity"),
                "warehouse": entities.get("warehouse"),
                "date": entities.get("date"),
                "detail_mode": entities.get("detail_mode", False),
            }

            if structured.get("item_name") and self.fuzzy_matcher:
                corrected = self.fuzzy_matcher.correct_item_typo(structured["item_name"])
                if corrected != structured["item_name"]:
                    result_entities["_item_corrected_from"] = structured["item_name"]
                structured["item_name"] = corrected

            if structured.get("customer_name") and self.fuzzy_matcher and not is_listing:
                structured["customer_name"] = clean_customer_name(structured["customer_name"])
                # Apply fuzzy matching
                resolved, customer_data = await self._resolve_customer_with_fuzzy_match(structured["customer_name"])
                if resolved:
                    structured["customer_name"] = resolved
                    if customer_data:
                        result_entities["_customer_code"] = customer_data.get('CardCode')

            for key, value in structured.items():
                if value is not None:
                    result_entities[key] = value

            logger.info(f"Entities detected by AI: {structured}")

            await cache_service.set_simple_async(cache_key, result_entities, ttl=300)
            return result_entities

        except Exception as e:
            logger.warning(f"AI entity extraction failed, using rules. Error: {e}")
            await cache_service.set_simple_async(cache_key, result_entities, ttl=60)
            return result_entities

    def extract(self, user_message: str, initial_entities: dict = None, context: dict = None) -> dict:
        """Sync extraction - for compatibility."""
        return asyncio.run(self.extract_async(user_message, initial_entities, context))

    async def extract_batch(self, messages: list[str]) -> list[dict]:
        """Extract entities from multiple messages in parallel."""
        tasks = [self.extract_async(msg) for msg in messages]
        return await asyncio.gather(*tasks)

    @staticmethod
    def _extract_json(text: str) -> str | None:
        """Extract JSON from text."""
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        return match.group() if match else None


# Singleton instance
entity_extractor = EntityExtractor()