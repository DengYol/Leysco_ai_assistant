"""
Conversation Enhancer - Makes all responses more natural and conversational
"""
import logging
import random
from typing import Dict, Any, List, Optional
import re

logger = logging.getLogger(__name__)


class ConversationEnhancer:
    """
    Enhances responses to make them more conversational and human-like.
    Adds personality, context-appropriate tone, and natural language.
    """
    
    def __init__(self):
        # Conversational openers based on intent
        self.openers = {
            "GREETING": [
                "Hey there! 👋",
                "Hello! How can I help you today?",
                "Hi! What can I do for you?",
                "Good to see you! What are you looking for?"
            ],
            "GET_ITEMS": [
                "📦 Here are the items I found:",
                "I've got some products for you:",
                "Check out these items:",
                "Here's what's available:"
            ],
            "GET_ITEM_PRICE": [
                "💰 Here's the pricing info:",
                "I found these prices for you:",
                "Let me check the prices:",
                "Here's what I found on pricing:"
            ],
            "GET_STOCK_LEVELS": [
                "📊 Here's the stock situation:",
                "Let me check inventory:",
                "Current stock levels:",
                "Here's what's available:"
            ],
            "GET_CUSTOMERS": [
                "👥 Here are your customers:",
                "I found these customers:",
                "Your customer list:",
                "Here are the customers I found:"
            ],
            "COMPANY_INFO": [
                "🏢 Let me tell you about Leysco!",
                "Here's some info about us:",
                "Great question! ",
                "I'd love to share that:"
            ],
            "HOW_TO_ORDER": [
                "📝 I can help you with that!",
                "Here's how ordering works:",
                "Let me walk you through it:",
                "Ordering is easy! Here's how:"
            ],
            "PAYMENT_METHODS": [
                "💳 We accept several payment methods:",
                "Here's how you can pay:",
                "Payment is flexible:",
                "You can pay via:"
            ],
            "CONTACT_INFO": [
                "📞 You can reach us through:",
                "Here's our contact information:",
                "We're here to help! ",
                "Get in touch with us:"
            ],
            "GET_LOW_STOCK_ALERTS": [
                "⚠️ Heads up! Here are low stock items:",
                "I've detected some items running low:",
                "Time to reorder! ",
                "Low stock alerts:"
            ],
            "CREATE_QUOTATION": [
                "✅ Great! I'll create that quotation:",
                "Here's your quotation:",
                "I've prepared a quote for you:",
                "Quotation ready! "
            ],
            "RECOMMEND_ITEMS": [
                "🎯 Based on your interests, I recommend:",
                "Here are some suggestions:",
                "You might like these:",
                "Popular choices:"
            ],
            "TRAINING_MODULE": [
                "🎓 I'd be happy to teach you!",
                "Here's a step-by-step guide:",
                "Let me show you how:",
                "Learning is fun! Here's how:"
            ],
            "TRAINING_VIDEO": [
                "🎥 Check out these video tutorials:",
                "Here are some helpful videos:",
                "Visual learning? I've got you covered:",
                "Watch and learn:"
            ],
            "TRAINING_GUIDE": [
                "📚 Here are the documentation guides:",
                "I found these helpful resources:",
                "Need detailed instructions? Here you go:",
                "Documentation available:"
            ],
            "TRAINING_FAQ": [
                "❓ Frequently asked questions:",
                "Here are common questions and answers:",
                "Great question! Here's what others ask:",
                "FAQ time:"
            ],
            "TRAINING_GLOSSARY": [
                "📖 Let me explain that term:",
                "Here's what that means:",
                "Great question! Here's the definition:",
                "Happy to clarify! "
            ],
            "TRAINING_WEBINAR": [
                "🎓 Upcoming training sessions:",
                "Here are our live webinars:",
                "Join us for these training events:",
                "Learn live with our experts:"
            ],
            "TRAINING_ONBOARDING": [
                "👋 Welcome to Leysco! I'm here to help you get started.",
                "New here? Let me show you around!",
                "Welcome aboard! Here's what you need to know:",
                "Excited to have you! Let's get started:"
            ],
            # Decision Support Intents
            "ANALYZE_INVENTORY_HEALTH": [
                "📊 Here's your inventory health report:",
                "I've analyzed your inventory:",
                "Here's the complete inventory analysis:",
                "📈 Inventory health check results:"
            ],
            "GET_REORDER_DECISIONS": [
                "🔄 Here are your reorder recommendations:",
                "Based on current stock levels, I recommend:",
                "Here's what you should reorder:",
                "📦 Reorder decisions:"
            ],
            "ANALYZE_PRICING_OPPORTUNITIES": [
                "💰 I found some pricing opportunities:",
                "Here are the best pricing insights:",
                "Check out these price trends:",
                "📉 Price analysis results:"
            ],
            "ANALYZE_CUSTOMER_BEHAVIOR": [
                "👥 Here's my analysis of this customer:",
                "I've analyzed their purchase patterns:",
                "Customer insights revealed:",
                "📋 Customer behavior analysis:"
            ],
            "FORECAST_DEMAND": [
                "📈 Here's the demand forecast:",
                "Based on historical data, I predict:",
                "Future demand looks like this:",
                "🔮 Demand forecast results:"
            ],
            "UNKNOWN": [
                "🤔 Hmm, I'm not quite sure about that.",
                "I'm still learning! Could you rephrase?",
                "I didn't catch that. Can you try again?",
                "Not sure about that one. Try asking about products, prices, or customers!"
            ]
        }
        
        # Friendly closers
        self.closers = [
            " Anything else I can help with?",
            " Let me know if you need more details.",
            " Hope that helps! 😊",
            " Is there anything else you'd like to know?",
            " Happy to help with more questions!",
            " What else can I do for you?",
            " Just ask if you need anything else!"
        ]
        
        # Data summary templates
        self.data_summaries = {
            "items": "📦 Found {count} item{s}",
            "customers": "👥 Found {count} customer{s}",
            "prices": "💰 Found pricing for {count} item{s}",
            "stock": "📊 Checked stock for {count} item{s}",
            "orders": "📋 Found {count} order{s}",
            "quotes": "💼 Found {count} quotation{s}",
            "warehouses": "🏭 Found {count} warehouse{s}",
            "alerts": "⚠️ Found {count} alert{s}",
            "videos": "🎥 Found {count} video{s}",
            "guides": "📚 Found {count} guide{s}",
            "faqs": "❓ Found {count} FAQ{s}",
            "terms": "📖 Found {count} term{s}",
            "inventory": "📊 Analyzed {count} item{s}",
            "recommendations": "🔄 Generated {count} recommendation{s}",
            "opportunities": "💰 Found {count} opportunity{s}",
            "insights": "📋 Generated {count} insight{s}",
            "forecast": "📈 Created forecast for {count} item{s}"
        }
        
        # Contextual tips
        self.tips = {
            "GET_ITEMS": "Try asking for 'prices' or 'stock levels' for specific items!",
            "GET_ITEM_PRICE": "Want to check stock? Ask 'how many in stock?'",
            "GET_CUSTOMERS": "Ask 'show customer details for [name]' for more info.",
            "GET_STOCK_LEVELS": "Use 'low stock alerts' to see what needs reordering.",
            "HOW_TO_ORDER": "Ready to order? Try 'create quotation for [customer]'.",
            "COMPANY_INFO": "Ask about 'payment methods' or 'contact info' for more details.",
            "CREATE_QUOTATION": "You can also ask for 'quotations for [customer]' to see past quotes.",
            "RECOMMEND_ITEMS": "Tell me what you're interested in for better recommendations!",
            "TRAINING_MODULE": "Want to watch a video instead? Ask for 'video tutorial'.",
            "TRAINING_GLOSSARY": "Ask about any term like 'SKU', 'MOQ', or 'UOM'.",
            "ANALYZE_INVENTORY_HEALTH": "You can also check specific warehouses with 'inventory health in Nairobi'.",
            "GET_REORDER_DECISIONS": "Need forecasts too? Try 'forecast demand for [item]'.",
            "ANALYZE_PRICING_OPPORTUNITIES": "Check specific items with 'price analysis for [item]'.",
            "ANALYZE_CUSTOMER_BEHAVIOR": "Compare customers with 'analyze multiple customers'.",
            "FORECAST_DEMAND": "Adjust forecast period with 'forecast for 60 days'."
        }
        
        # Intents that have their own formatting and should NOT get openers
        self.SKIP_OPENER_INTENTS = {
            "GET_CROSS_SELL",
            "GET_UPSELL", 
            "GET_SEASONAL_RECOMMENDATIONS",
            "GET_TRENDING_PRODUCTS",
            "GET_ITEMS",
            "GET_ITEM_PRICE",
            "GET_CUSTOMERS",
            "GET_STOCK_LEVELS",
            "GET_WAREHOUSES",
            "GET_LOW_STOCK_ALERTS",
            "GREETING",
            "THANKS",
            "SMALL_TALK"
        }
        
        # Intents that should NOT get tips
        self.SKIP_TIP_INTENTS = {
            "GREETING", 
            "THANKS", 
            "SMALL_TALK", 
            "GET_CROSS_SELL",
            "GET_UPSELL",
            "GET_SEASONAL_RECOMMENDATIONS",
            "GET_TRENDING_PRODUCTS"
        }
        
        # Intents that should NOT get closers
        self.SKIP_CLOSER_INTENTS = {
            "GET_CROSS_SELL",
            "GET_UPSELL",
            "GET_SEASONAL_RECOMMENDATIONS",
            "GET_TRENDING_PRODUCTS"
        }
    
    def enhance(self, intent: str, original_message: str, data: Optional[List] = None, user_message: str = "") -> str:
        """
        Take a raw response and make it conversational
        """
        # Clean up the original message (remove any existing prefixes)
        clean_message = self._clean_message(original_message)
        
        # Start with the clean message
        enhanced = clean_message
        
        # Choose an appropriate opener (skip for intents with their own formatting)
        if intent not in self.SKIP_OPENER_INTENTS:
            opener = self._get_opener(intent, user_message)
            if opener:
                enhanced = f"{opener}\n\n{enhanced}"
        
        # Add data summary if available (skip for intents that have their own summaries)
        if data is not None and intent not in self.SKIP_OPENER_INTENTS:
            summary = self._get_data_summary(intent, data)
            if summary:
                enhanced += f"\n\n{summary}"
        
        # Add a contextual tip (skip for certain intents)
        if intent not in self.SKIP_TIP_INTENTS:
            tip = self._get_tip(intent, user_message)
            if tip:
                enhanced += f"\n\n💡 **Tip:** {tip}"
        
        # Add a friendly closer (skip for intents that have their own closers/tips)
        if intent not in self.SKIP_CLOSER_INTENTS:
            enhanced += random.choice(self.closers)
        
        return enhanced
    
    def _clean_message(self, message: str) -> str:
        """Remove any existing prefixes or formatting that might duplicate"""
        # Remove common prefixes if they exist
        prefixes_to_remove = [
            r"^Found \d+ items?:?\s*\n?",
            r"^Here are .+?:?\s*\n?",
            r"^I found .+?:?\s*\n?",
            r"^📦.*?\n",
            r"^💰.*?\n",
            r"^👥.*?\n",
            r"^📊.*?\n",
            r"^⚠️.*?\n",
            r"^✅.*?\n",
            r"^🎓.*?\n"
        ]
        
        cleaned = message
        for pattern in prefixes_to_remove:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        return cleaned.strip()
    
    def _get_opener(self, intent: str, user_message: str) -> str:
        """Get appropriate opener based on intent and context"""
        # Check for specific keywords in user message
        if "thank" in user_message.lower():
            return random.choice([
                "You're very welcome! 😊",
                "My pleasure!",
                "Happy to help!",
                "Anytime!"
            ])
        
        if "sorry" in user_message.lower():
            return random.choice([
                "No problem at all!",
                "No worries!",
                "That's okay!",
                "No need to apologize!"
            ])
        
        # Get intent-based opener
        openers = self.openers.get(intent, self.openers["UNKNOWN"])
        
        # Don't use UNKNOWN openers for known intents (prevents "Hmm..." messages)
        if intent != "UNKNOWN" and openers == self.openers["UNKNOWN"]:
            return ""  # Return empty string for known intents
        
        return random.choice(openers)
    
    def _get_data_summary(self, intent: str, data: List) -> Optional[str]:
        """Generate a summary of the data found"""
        if not data:
            return None
        
        count = len(data)
        s = "s" if count != 1 else ""
        
        # Determine data type
        intent_lower = intent.lower()
        
        if "ITEM" in intent_lower and "PRICE" not in intent_lower:
            template = self.data_summaries.get("items", "Found {count} item{s}")
        elif "CUSTOMER" in intent_lower:
            template = self.data_summaries.get("customers", "Found {count} customer{s}")
        elif "PRICE" in intent_lower:
            template = self.data_summaries.get("prices", "Found pricing for {count} item{s}")
        elif "STOCK" in intent_lower:
            template = self.data_summaries.get("stock", "Checked stock for {count} item{s}")
        elif "ORDER" in intent_lower:
            template = self.data_summaries.get("orders", "Found {count} order{s}")
        elif "QUOTE" in intent_lower or "QUOTATION" in intent_lower:
            template = self.data_summaries.get("quotes", "Found {count} quotation{s}")
        elif "WAREHOUSE" in intent_lower:
            template = self.data_summaries.get("warehouses", "Found {count} warehouse{s}")
        elif "ALERT" in intent_lower:
            template = self.data_summaries.get("alerts", "Found {count} alert{s}")
        elif "TRAINING_VIDEO" in intent_lower:
            template = self.data_summaries.get("videos", "Found {count} video{s}")
        elif "TRAINING_GUIDE" in intent_lower:
            template = self.data_summaries.get("guides", "Found {count} guide{s}")
        elif "TRAINING_FAQ" in intent_lower:
            template = self.data_summaries.get("faqs", "Found {count} FAQ{s}")
        elif "TRAINING_GLOSSARY" in intent_lower:
            template = self.data_summaries.get("terms", "Found {count} term{s}")
        elif "ANALYZE_INVENTORY_HEALTH" in intent_lower:
            template = self.data_summaries.get("inventory", "Analyzed {count} item{s}")
        elif "GET_REORDER_DECISIONS" in intent_lower:
            template = self.data_summaries.get("recommendations", "Generated {count} recommendation{s}")
        elif "ANALYZE_PRICING_OPPORTUNITIES" in intent_lower:
            template = self.data_summaries.get("opportunities", "Found {count} opportunity{s}")
        elif "ANALYZE_CUSTOMER_BEHAVIOR" in intent_lower:
            template = self.data_summaries.get("insights", "Generated {count} insight{s}")
        elif "FORECAST_DEMAND" in intent_lower:
            template = self.data_summaries.get("forecast", "Created forecast for {count} item{s}")
        else:
            return None
        
        return template.format(count=count, s=s)
    
    def _get_tip(self, intent: str, user_message: str) -> Optional[str]:
        """Get a contextual tip based on intent"""
        # Check if user seems confused
        if "?" not in user_message and len(user_message) < 20:
            return "Feel free to ask a more specific question!"
        
        # Return intent-specific tip
        return self.tips.get(intent)
    
    def format_error(self, error_message: str) -> str:
        """Format error messages in a friendly way"""
        friendly_errors = {
            "timeout": "⏳ The system is taking a moment. Let's try again in a bit!",
            "not found": "🔍 Hmm, I couldn't find that. Could you check the spelling?",
            "missing": "🤔 I need a bit more information to help with that.",
            "api": "📡 Having trouble connecting. Please try again in a moment.",
            "rate limit": "⏱️ Too many requests! Let's wait a moment and try again."
        }
        
        # Check which error type matches
        for key, friendly in friendly_errors.items():
            if key in error_message.lower():
                return friendly
        
        # Default friendly error
        return f"😕 {error_message} Let me know if you need help with something else!"
    
    def celebrate_success(self, action: str) -> str:
        """Celebrate successful actions"""
        celebrations = {
            "CREATE_QUOTATION": [
                "🎉 Quotation created successfully! Great job!",
                "✅ Done! Your quotation is ready.",
                "🎯 Perfect! Quotation has been created."
            ],
            "default": [
                "✅ Done!",
                "🎉 Success!",
                "✨ All set!"
            ]
        }
        
        choices = celebrations.get(action, celebrations["default"])
        return random.choice(choices)