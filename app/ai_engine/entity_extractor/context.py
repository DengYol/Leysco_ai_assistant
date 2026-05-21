"""Context-aware entity enhancement for follow-up queries"""

import re
import logging
from typing import Dict, Optional
from .constants import FOLLOWUP_INDICATORS, PRONOUN_WORDS

logger = logging.getLogger(__name__)


class ContextEnhancer:
    """Enhances entity extraction with conversation context"""
    
    def is_followup_query(self, text: str) -> bool:
        """Check if query is a follow-up to previous conversation."""
        text_lower = text.lower()
        for indicator in FOLLOWUP_INDICATORS:
            if indicator in text_lower:
                return True
        return False
    
    def is_pronoun_query(self, text: str) -> bool:
        """Check if query contains pronoun words (no specific customer name)."""
        text_lower = text.lower()
        has_pronoun = any(word in text_lower for word in PRONOUN_WORDS)
        pronoun_phrases = [
            r'\b(?:their|his|her|its|wake|yake|yetu|yako)\s+(?:orders?|details?|info|quotation|delivery|invoices?)',
            r'(?:show|get|find|check|onyesha|tafuta|angalia)\s+(?:their|his|her|its|wake|yake|yetu|yako)\s+(?:orders?|details?)',
        ]
        has_pronoun_phrase = any(re.search(pattern, text_lower) for pattern in pronoun_phrases)
        return has_pronoun or has_pronoun_phrase
    
    def extract_referenced_item_from_context(self, text: str, context: Dict) -> Optional[str]:
        """Extract item name from context when user refers to 'it', 'that', 'the first one', etc."""
        text_lower = text.lower()
        
        # Check for ordinal references
        ordinals = {
            "first": 0, "1st": 0, "one": 0, "kwanza": 0, "ya kwanza": 0,
            "second": 1, "2nd": 1, "two": 1, "pili": 1, "ya pili": 1,
            "third": 2, "3rd": 2, "three": 2, "tatu": 2, "ya tatu": 2,
            "fourth": 3, "4th": 3, "four": 3, "nne": 3, "ya nne": 3,
            "fifth": 4, "5th": 4, "five": 4, "tano": 4, "ya tano": 4,
        }
        
        last_results = context.get("last_results", [])
        
        for word, index in ordinals.items():
            if word in text_lower:
                if index < len(last_results):
                    item = last_results[index]
                    item_name = item.get("ItemName") or item.get("name")
                    if item_name:
                        logger.info(f"Resolved ordinal '{word}' to item: {item_name}")
                        return item_name
        
        # Check for pronoun references
        pronoun_words = ["it", "this", "that", "the item", "hii", "hiyo", "ile", "hicho", "kile"]
        if any(word in text_lower for word in pronoun_words):
            referenced_items = context.get("referenced_items", [])
            if referenced_items:
                item_name = referenced_items[0].get("name")
                if item_name:
                    logger.info(f"Resolved pronoun to item: {item_name}")
                    return item_name
        
        return None
    
    def extract_referenced_customer_from_context(self, text: str, context: Dict) -> Optional[str]:
        """Extract customer name from context when user refers to 'them', 'that customer', etc."""
        text_lower = text.lower()
        
        customer_reference_words = ["customer", "them", "they", "that company", "mteja", "wale", "hao"]
        if any(word in text_lower for word in customer_reference_words):
            referenced_customers = context.get("referenced_customers", [])
            if referenced_customers:
                customer_name = referenced_customers[0].get("name")
                if customer_name:
                    logger.info(f"Resolved customer reference: {customer_name}")
                    return customer_name
        
        return None
    
    def enhance_with_context(self, entities: dict, context: Dict, message: str) -> dict:
        """Enhance extracted entities with conversation context."""
        if not context:
            return entities
        
        enhanced = entities.copy()
        
        # Skip if we already have values
        has_item = entities.get("item_name")
        has_customer = entities.get("customer_name")
        
        # Check if this is a follow-up query
        is_followup = self.is_followup_query(message)
        is_pronoun = self.is_pronoun_query(message)
        
        # Fill missing item from context
        if not has_item and (is_followup or is_pronoun):
            context_item = self.extract_referenced_item_from_context(message, context)
            if context_item:
                enhanced["item_name"] = context_item
                enhanced["_resolved_from_context"] = True
                logger.info(f"Filled item from context: {context_item}")
        
        # Fill missing customer from context
        if not has_customer and (is_followup or is_pronoun):
            context_customer = self.extract_referenced_customer_from_context(message, context)
            if context_customer:
                enhanced["customer_name"] = context_customer
                enhanced["_resolved_from_context"] = True
                logger.info(f"Filled customer from context: {context_customer}")
        
        # If user asks for price and we have an item from context
        price_words = ["price", "cost", "how much", "bei", "gharama", "ngapi"]
        if any(word in message.lower() for word in price_words) and not has_item:
            context_item = self.extract_referenced_item_from_context(message, context)
            if context_item:
                enhanced["item_name"] = context_item
                enhanced["_resolved_from_context"] = True
                logger.info(f"Filled item for price query from context: {context_item}")
        
        # If user asks for stock and we have an item from context
        stock_words = ["stock", "hisa", "viwango", "idadi", "zilizopo"]
        if any(word in message.lower() for word in stock_words) and not has_item:
            context_item = self.extract_referenced_item_from_context(message, context)
            if context_item:
                enhanced["item_name"] = context_item
                enhanced["_resolved_from_context"] = True
                logger.info(f"Filled item for stock query from context: {context_item}")
        
        # Add context flag
        if enhanced != entities:
            enhanced["_context_used"] = True
        
        return enhanced