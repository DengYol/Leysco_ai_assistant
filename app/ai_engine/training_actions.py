"""
app/ai_engine/training_actions.py
=================================
Complete Training Module for Leysco100
Based on actual system modules and sub-modules

Optimized with:
- Caching for training content
- Async support
- Faster lookups with dict indexing
- LRU cache for frequently accessed modules
"""

import logging
import asyncio
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime
from functools import lru_cache, wraps

from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


# Cache decorator for training responses
def cache_training(ttl_seconds: int = 3600):
    """Cache training responses for 1 hour."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            cache = get_cache_service()
            
            # Generate cache key
            func_name = func.__name__
            # Filter out self and get meaningful args
            cache_str = f"training:{func_name}:{str(args[1:])}:{str(sorted(kwargs.items()))}"
            cache_key = hashlib.md5(cache_str.encode()).hexdigest()
            
            # Check cache
            cached = cache.get_simple(cache_key)
            if cached is not None:
                logger.info(f"⚡ Training cache hit: {func_name}")
                return cached
            
            # Execute function
            result = func(self, *args, **kwargs)
            
            # Cache result
            if result:
                cache.set_simple(cache_key, result, ttl=ttl_seconds)
            
            return result
        return wrapper
    return decorator


class TrainingActions:
    """
    Handles training and onboarding for all Leysco100 modules.
    Based on actual system structure from screenshots.
    Optimized with caching for better performance.
    """

    def __init__(self):
        # Initialize training modules (same as your existing structure)
        self.training_modules = {
            # ... (your existing 19 modules dictionary - keep as is)
        }
        
        # Training videos
        self.training_videos = {
            # ... (your existing training videos)
        }
        
        # FAQ database
        self.faqs = {
            # ... (your existing FAQs)
        }
        
        # Glossary
        self.glossary = {
            # ... (your existing glossary)
        }
        
        # Webinar schedule
        self.webinars = [
            # ... (your existing webinars)
        ]
        
        # Cache for module lookups
        self._module_index = None
        self._submodule_index = None
        self._build_indexes()

    def _build_indexes(self):
        """Build quick lookup indexes for modules and sub-modules."""
        self._module_index = {}
        self._submodule_index = {}
        
        for module_id, module in self.training_modules.items():
            # Index by module title (lowercase)
            self._module_index[module["title"].lower()] = module_id
            
            # Index by module_id
            self._module_index[module_id] = module_id
            
            # Index sub-modules
            for sub_id, sub_module in module.get("sub_modules", {}).items():
                if isinstance(sub_module, dict):
                    sub_title = sub_module.get("title", sub_id.replace("_", " ")).lower()
                    self._submodule_index[sub_title] = (module_id, sub_id)
                    self._submodule_index[sub_id] = (module_id, sub_id)

    @lru_cache(maxsize=128)
    def _get_cached_module(self, module_id: str) -> Optional[Dict]:
        """Cached module lookup."""
        return self.training_modules.get(module_id)

    @lru_cache(maxsize=256)
    def _get_cached_submodule(self, module_id: str, sub_id: str) -> Optional[Dict]:
        """Cached sub-module lookup."""
        module = self.training_modules.get(module_id)
        if module:
            sub = module.get("sub_modules", {}).get(sub_id)
            if isinstance(sub, dict):
                return sub
        return None

    # =========================================================
    # MAIN HANDLER METHODS - WITH CACHING
    # =========================================================

    @cache_training(ttl_seconds=3600)
    def handle_training_module(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle general training requests"""
        text = message.lower() if message else ''
        
        # Check if asking for specific module by title or id
        for keyword, module_id in self._module_index.items():
            if keyword in text:
                module = self._get_cached_module(module_id)
                if module:
                    return self._format_module_response(module_id, module)
        
        # Check if asking for specific sub-module
        for keyword, (module_id, sub_id) in self._submodule_index.items():
            if keyword in text:
                module = self._get_cached_module(module_id)
                sub_module = self._get_cached_submodule(module_id, sub_id)
                if module and sub_module:
                    return self._format_submodule_response(module_id, sub_id, module, sub_module)
        
        # If no specific module, show all available
        return self._show_all_modules()

    @cache_training(ttl_seconds=3600)
    def handle_training_video(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle video tutorial requests"""
        text = message.lower() if message else ''
        
        for topic, url in self.training_videos.items():
            if topic in text:
                topic_name = topic.replace("_", " ").title()
                return f"🎥 **{topic_name} Video Tutorial**\n\nWatch now: {url}\n\n📚 Related modules: {self._get_related_modules(topic)}"
        
        return self._list_all_videos()

    @cache_training(ttl_seconds=3600)
    def handle_training_guide(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle documentation requests"""
        text = message.lower() if message else ''
        
        for module_id, module in self.training_modules.items():
            if module_id in text or module["title"].lower() in text:
                return f"📄 **{module['title']} Documentation**\n\nAccess the full guide: {module['doc_url']}\n\n{module['description']}"
        
        return "📚 **All Documentation**\n\nAccess all guides at: https://docs.leysco.com"

    @cache_training(ttl_seconds=1800)
    def handle_training_faq(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle FAQ requests"""
        text = message.lower() if message else ''
        
        for category, faqs in self.faqs.items():
            if category in text:
                return self._format_faq_response(category, faqs)
        
        return self._show_faq_menu()

    @cache_training(ttl_seconds=3600)
    def handle_training_glossary(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle glossary/term definition requests"""
        text = message.lower() if message else ''
        
        for term, definition in self.glossary.items():
            if term.lower() in text:
                return f"{definition}\n\nNeed another term defined? Just ask!"
        
        return self._show_all_terms()

    @cache_training(ttl_seconds=1800)
    def handle_training_webinar(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Handle webinar requests"""
        return self._show_webinar_schedule()

    def handle_onboarding_welcome(self, language: str = "en") -> str:
        """Welcome message for new users"""
        return self._get_onboarding_welcome()

    # =========================================================
    # ASYNC VERSIONS
    # =========================================================

    async def handle_training_module_async(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Async version of handle_training_module."""
        return await asyncio.to_thread(self.handle_training_module, entities, message, language)

    async def handle_training_video_async(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Async version of handle_training_video."""
        return await asyncio.to_thread(self.handle_training_video, entities, message, language)

    async def handle_training_faq_async(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Async version of handle_training_faq."""
        return await asyncio.to_thread(self.handle_training_faq, entities, message, language)

    async def handle_training_glossary_async(self, entities: Dict[str, Any], message: str = "", language: str = "en") -> str:
        """Async version of handle_training_glossary."""
        return await asyncio.to_thread(self.handle_training_glossary, entities, message, language)

    # =========================================================
    # FORMATTING HELPERS (unchanged - keep as is)
    # =========================================================

    def _format_module_response(self, module_id: str, module: Dict) -> str:
        """Format a module response with sub-modules"""
        response = f"**{module['title']}**\n\n"
        response += f"_{module['description']}_\n\n"
        response += f"⏱️ **Estimated time:** {module['estimated_time']}\n\n"
        
        response += "**📌 Sub-Modules:**\n"
        for sub_id, sub_module in module.get("sub_modules", {}).items():
            if isinstance(sub_module, dict) and "title" in sub_module:
                response += f"• **{sub_module['title']}**\n"
            elif isinstance(sub_module, dict) and sub_module.get("sub_modules"):
                response += f"• **{sub_module.get('title', sub_id.replace('_', ' ').title())}** (group)\n"
            else:
                response += f"• **{sub_id.replace('_', ' ').title()}**\n"
        
        response += f"\n📺 **Video:** {module['video_url']}"
        response += f"\n📄 **Documentation:** {module['doc_url']}"
        
        response += "\n\nWhich sub-module would you like to learn about? Just ask!"
        return response

    def _format_submodule_response(self, module_id: str, sub_id: str, module: Dict, sub_module: Dict) -> str:
        """Format a sub-module response with detailed steps"""
        response = f"**{module['title']} → {sub_module['title']}**\n\n"
        
        response += "**Step-by-Step Guide:**\n"
        for step in sub_module['steps']:
            response += f"{step}\n"
        
        if sub_module.get('tips'):
            response += "\n**💡 Pro Tips:**\n"
            for tip in sub_module['tips']:
                response += f"{tip}\n"
        
        response += f"\n📺 **Video:** {module['video_url']}"
        response += f"\n📄 **Documentation:** {module['doc_url']}"
        
        return response

    def _format_faq_response(self, category: str, faqs: List[Dict]) -> str:
        """Format FAQ response"""
        category_name = category.title()
        response = f"❓ **{category_name} - Frequently Asked Questions**\n\n"
        
        for i, faq in enumerate(faqs, 1):
            response += f"{i}. **Q:** {faq['q']}\n"
            response += f"   **A:** {faq['a']}\n\n"
        
        return response

    def _show_all_modules(self) -> str:
        """Show all available training modules"""
        response = "🎓 **Leysco100 Training Academy**\n\n"
        response += "I can teach you how to use all 19 modules:\n\n"
        
        for module_id, module in self.training_modules.items():
            response += f"**{module['title']}**\n"
            response += f"_{module['description']}_\n"
            sub_count = len(module.get('sub_modules', {}))
            response += f"⏱️ {module['estimated_time']} | 📚 {sub_count} sub-modules\n\n"
        
        response += "Just tell me what you'd like to learn:\n"
        response += "• 'How to use Sales module'\n"
        response += "• 'Teach me Inventory management'\n"
        response += "• 'Show me Production sub-modules'\n"
        response += "• 'Create purchase order guide'\n"
        response += "• 'How to reconcile bank statements'"
        return response

    def _list_all_videos(self) -> str:
        """List all available video tutorials"""
        response = "🎬 **Leysco100 Video Tutorial Library**\n\n"
        
        for topic, url in self.training_videos.items():
            topic_name = topic.replace("_", " ").title()
            response += f"• **{topic_name}:** {url}\n"
        
        response += "\nWhich tutorial would you like to watch? Just say the topic name!"
        return response

    def _show_faq_menu(self) -> str:
        """Show FAQ categories menu"""
        return "❓ **Frequently Asked Questions**\n\n" \
               "Choose a category:\n\n" \
               "1️⃣ **Administration** - Users, settings, approvals\n" \
               "2️⃣ **Sales** - Quotes, orders, invoices\n" \
               "3️⃣ **Purchase** - POs, receipts, vendor invoices\n" \
               "4️⃣ **Inventory** - Items, stock, counting\n" \
               "5️⃣ **Banking** - Payments, reconciliation\n" \
               "6️⃣ **Production** - BOMs, production orders\n" \
               "7️⃣ **Logistics** - Routes, dispatch, tracking\n" \
               "8️⃣ **Gate Pass** - Security, vehicle movement\n" \
               "9️⃣ **Dashboard** - Analytics, KPIs\n\n" \
               "Just say 'inventory FAQ' or ask your specific question!"

    def _show_all_terms(self) -> str:
        """Show all glossary terms"""
        response = "📚 **Leysco100 Glossary of Terms**\n\n"
        
        for term in sorted(self.glossary.keys()):
            response += f"{self.glossary[term]}\n\n"
        
        response += "Which term would you like to learn more about? Just ask!"
        return response

    def _show_webinar_schedule(self) -> str:
        """Show upcoming webinar schedule"""
        response = "🎓 **Upcoming Live Training Webinars**\n\n"
        
        for webinar in self.webinars:
            response += f"**{webinar['topic']}**\n"
            response += f"📅 {webinar['date']} at {webinar['time']}\n"
            response += f"⏱️ {webinar['duration']} with {webinar['instructor']}\n\n"
        
        response += "To register, email training@leysco.com or ask your system administrator."
        return response

    def _get_onboarding_welcome(self) -> str:
        """Welcome message for new users"""
        return """👋 **Karibu Leysco100! Welcome to your new ERP system.**

I'm your personal training assistant, here to help you learn the system step by step.

**🎓 What I Can Teach You:**

📊 **19 Main Modules** with 150+ sub-modules:

• ⚙️ **Administration** - System setup, users, permissions
• 💰 **Financials** - Chart of accounts, taxes, currencies
• 💳 **Banking** - Banks, accounts, payments
• 📦 **Inventory** - Items, warehouses, stock
• 🏭 **Production** - BOMs, orders, costing
• 🛠️ **Resources** - Capacity, availability
• 🔧 **Service** - Contracts, support
• 📤 **Data Imports** - Excel, integrations
• 🔧 **Utilities** - Approvals, monitoring
• 💼 **Sales** - Quotes, orders, invoices
• 📥 **Purchase** - POs, receipts, vendor invoices
• 👥 **Business Partners** - Customers, vendors
• 💳 **Banking Transactions** - Payments, reconciliation
• 📊 **Inventory Transactions** - Movements, reports
• 🛠️ **Resources Mgmt** - Capacity, pricing
• 🚚 **Logistics Hub** - Routes, dispatch, GPS
• 🏭 **Production Ops** - Manufacturing execution
• 🚪 **Gate Pass Mgmt** - Security, vehicle control
• 📊 **Dashboard** - Analytics, insights

**💬 Try Asking:**
• "How do I create a sales order?" - Step-by-step guide
• "Show me inventory sub-modules" - List related topics
• "What does BOM mean?" - Learn terminology
• "Sales module FAQ" - Common questions
• "Show all training modules" - Complete list

What would you like to learn today? I'm here to help! 🚀"""

    def _get_related_modules(self, topic: str) -> str:
        """Get related modules for a topic"""
        relations = {
            "administration": "Users, Permissions, Settings",
            "financials": "Accounting, Taxes, Currencies",
            "banking_master": "Banks, Accounts",
            "inventory_master": "Items, Warehouses, UoM",
            "production_master": "Resources, Routes",
            "resources_master": "Resource Groups, Properties",
            "service": "Contracts",
            "data_imports": "Excel, Integration",
            "utilities": "Approvals, Monitoring",
            "sales": "Quotes, Orders, Invoices",
            "purchase": "POs, Receipts, Invoices",
            "bp": "Customers, Vendors",
            "banking_transactions": "Payments, Reconciliation",
            "inventory_transactions": "Movements, Reports",
            "resources": "Capacity, Pricing",
            "logistics": "Routes, Dispatch, GPS",
            "production": "BOMs, Orders, Costing",
            "gatepass": "Security, Vehicle Movement",
            "dashboard": "Analytics, KPIs"
        }
        return relations.get(topic, "Various related modules")

    def clear_cache(self):
        """Clear training cache."""
        self._build_indexes()
        self._get_cached_module.cache_clear()
        self._get_cached_submodule.cache_clear()
        logger.info("Training cache cleared")