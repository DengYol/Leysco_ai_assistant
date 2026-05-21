"""Knowledge base intent handlers"""

from typing import Dict, Any
import logging
from ..base_handler import BaseHandler
from app.ai_engine import leysco_knowledge_base as kb

logger = logging.getLogger(__name__)


class KnowledgeHandler(BaseHandler):
    """Handler for knowledge base intents"""
    
    def company_info(self, language: str) -> dict:
        """Get company information."""
        info = kb.get_company_info()
        
        if language == "sw":
            text = f"{info['name']} - {info['tagline']}\n\n{info['about'].strip()}\n\nThamani Zetu:\n"
        else:
            text = f"{info['name']} - {info['tagline']}\n\n{info['about'].strip()}\n\nOur Values:\n"
        
        for value in info['values']:
            text += f"• {value}\n"
        
        return {"message": text, "data": []}
    
    def product_info(self, language: str) -> dict:
        """Get product brand information."""
        brands = kb.get_brand_info()
        
        if language == "sw":
            text = "Bidhaa za Leysco 100\n\n"
        else:
            text = "Leysco 100 Product Brands\n\n"
        
        for brand_key, brand in brands.items():
            text += f"{brand['name']} - {brand['category']}\n{brand['description'].strip()[:200]}...\n\n"
        
        return {"message": text, "data": []}
    
    def how_to_order(self, language: str) -> dict:
        """Get ordering information."""
        ordering = kb.get_ordering_info()
        
        if language == "sw":
            text = ordering['how_to_order'].strip() + "\n\nMasharti ya Malipo:\n"
            for key, value in ordering['payment_terms'].items():
                label = key.replace('_', ' ').title()
                sw_labels = {
                    "Available Methods": "Njia Zinazopatikana",
                    "Credit Terms": "Masharti ya Mkopo",
                    "Deposit Required": "Malipo ya Awali Yanahitajika"
                }
                display_label = sw_labels.get(label, label)
                text += f"• {display_label}: {', '.join(value) if isinstance(value, list) else value}\n"
        else:
            text = ordering['how_to_order'].strip() + "\n\nPayment Terms:\n"
            for key, value in ordering['payment_terms'].items():
                label = key.replace('_', ' ').title()
                text += f"• {label}: {', '.join(value) if isinstance(value, list) else value}\n"
        
        text += "\n" + ordering['delivery'].strip()
        
        return {"message": text, "data": []}
    
    def payment_methods(self, language: str) -> dict:
        """Get payment methods information."""
        ordering = kb.get_ordering_info()
        
        if language == "sw":
            text = "Njia za Malipo\n\n"
            for method in ordering['payment_terms'].get('available_methods', []):
                text += f"• {method}\n"
        else:
            text = "Payment Methods\n\n"
            for method in ordering['payment_terms'].get('available_methods', []):
                text += f"• {method}\n"
        
        return {"message": text, "data": []}
    
    def contact_info(self, language: str) -> dict:
        """Get contact information."""
        contact = kb.get_contact_info()
        
        if language == "sw":
            text = "Wasiliana na Leysco 100\n\nMsaada kwa Wateja:\n"
            for key, value in contact['customer_support'].items():
                label = key.replace('_', ' ').title()
                sw_labels = {
                    "Phone": "Simu",
                    "Email": "Barua Pepe",
                    "Hours": "Saa za Kufungua"
                }
                display_label = sw_labels.get(label, label)
                text += f"• {display_label}: {value}\n"
            text += "\nMaeneo ya Mauzo:\n"
            for region in contact['sales_regions']:
                text += f"• {region['name']}: {region['contact']}\n"
        else:
            text = "Contact Leysco 100\n\nCustomer Support:\n"
            for key, value in contact['customer_support'].items():
                label = key.replace('_', ' ').title()
                text += f"• {label}: {value}\n"
            text += "\nSales Regions:\n"
            for region in contact['sales_regions']:
                text += f"• {region['name']}: {region['contact']}\n"
        
        return {"message": text, "data": []}
    
    def policy_question(self, language: str) -> dict:
        """Get policy information."""
        policies = kb.get_policies()
        
        if language == "sw":
            text = "Sera za Leysco 100\n\n" + policies['returns'].strip() + "\n\n" + policies['quality_guarantee'].strip()
        else:
            text = "Leysco 100 Policies\n\n" + policies['returns'].strip() + "\n\n" + policies['quality_guarantee'].strip()
        
        return {"message": text, "data": []}
    
    def handle_faq(self, entities: dict, message: str, language: str) -> dict:
        """Handle FAQ questions."""
        user_msg = entities.get("item_name", "") or message
        faq_answer = kb.get_faq_answer(user_msg)
        
        if faq_answer:
            if language == "sw":
                return {"message": f"Maswali Yanayoulizwa Sana: {faq_answer}", "data": []}
            return {"message": f"FAQ: {faq_answer}", "data": []}
        
        if language == "sw":
            return {"message": "Samahani, sikuweza kupata jibu la swali lako. Tafadhali wasiliana na msaada kwa wateja.", "data": []}
        return {"message": "Sorry, I couldn't find an answer to your question. Please contact customer support.", "data": []}