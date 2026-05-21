"""Conversational response enhancer for more natural interactions"""

import random
import re
from typing import Dict, Any, Optional


class ConversationalEnhancer:
    """Enhances responses to be more conversational and natural"""
    
    @staticmethod
    def add_acknowledgment(response: str, intent: str, language: str = "en") -> str:
        """Add a natural acknowledgment prefix based on intent"""
        if response.startswith(("Sure!", "Here", "I've", "Let me", "Got it", "Hmm", "Sorry")):
            return response
        
        acknowledgments = {
            "GET_ITEM_PRICE": {
                "en": ["Sure thing! ", "Got it! ", "One moment... ", "Coming right up! "],
                "sw": ["Sawa! ", "Nimeelewa! ", "Subiri kidogo... "]
            },
            "GET_TOP_SELLING_ITEMS": {
                "en": ["Here's what's trending! ", "Check this out! ", "Popular picks: "],
                "sw": ["Hizi ndizo! ", "Angalia hizi! "]
            },
            "default": {
                "en": ["Okay! ", "Got it! ", "Sure! ", "Absolutely! "],
                "sw": ["Sawa! ", "Nimeelewa! ", "Ndio! "]
            }
        }
        
        ack_list = acknowledgments.get(intent, acknowledgments["default"]).get(language, ["", " "])
        return random.choice(ack_list) + response
    
    @staticmethod
    def add_empathy(response: str, has_error: bool = False) -> str:
        """Add empathetic phrases for error cases"""
        if not has_error:
            return response
        
        empathy_phrases = [
            "I understand that can be frustrating. ",
            "Let me try to help with that. ",
            "I see the issue. ",
            "I'll work on finding a solution for you. "
        ]
        
        return random.choice(empathy_phrases) + response
    
    @staticmethod
    def simplify_price_display(price_text: str, language: str = "en") -> str:
        """Simplify price display for better readability"""
        if language == "sw":
            # Remove excessive formatting if any
            price_text = re.sub(r'\*\*', '', price_text)
            return price_text
        else:
            price_text = re.sub(r'\*\*', '', price_text)
            return price_text
    
    @staticmethod
    def add_section_breaks(text: str) -> str:
        """Add appropriate section breaks for better readability"""
        # Ensure list items are properly formatted
        if "•" in text:
            # Add proper spacing for list items
            text = re.sub(r'•', '\n•', text)
        
        # Add spacing after colons
        text = re.sub(r':', ': ', text)
        
        return text
    
    @staticmethod
    def add_emoji_for_intent(response: str, intent: str) -> str:
        """Add appropriate emojis based on intent"""
        if any(emoji in response for emoji in ["🔍", "🔥", "💰", "📦", "💡"]):
            return response
        
        intent_emojis = {
            "GET_ITEM_PRICE": "💰 ",
            "GET_TOP_SELLING_ITEMS": "🔥 ",
            "GET_SLOW_MOVING_ITEMS": "📉 ",
            "GET_OUTSTANDING_DELIVERIES": "🚚 ",
            "CREATE_QUOTATION": "📄 ",
            "GREETING": "👋 ",
            "THANKS": "🙏 ",
        }
        
        emoji = intent_emojis.get(intent, "")
        if emoji and not response.startswith(emoji):
            return emoji + response
        
        return response
    
    @staticmethod
    def enhance(
        response: str, 
        intent: str, 
        language: str = "en", 
        has_error: bool = False,
        data: Optional[Any] = None
    ) -> str:
        """Apply all enhancements to make response more conversational"""
        if not response:
            return response
        
        # Skip enhancement for very short responses
        if len(response) < 20:
            return response
        
        enhanced = response
        
        # Add emoji
        enhanced = ConversationalEnhancer.add_emoji_for_intent(enhanced, intent)
        
        # Add acknowledgment (skip for error responses)
        if not has_error and not response.startswith(("Sorry", "Hmm", "I couldn't")):
            enhanced = ConversationalEnhancer.add_acknowledgment(enhanced, intent, language)
        
        # Add empathy for errors
        if has_error:
            enhanced = ConversationalEnhancer.add_empathy(enhanced, True)
        
        # Simplify formatting
        enhanced = ConversationalEnhancer.simplify_price_display(enhanced, language)
        
        # Add section breaks
        enhanced = ConversationalEnhancer.add_section_breaks(enhanced)
        
        return enhanced


conversational_enhancer = ConversationalEnhancer()