"""
app/services/knowledge_ingestion.py
====================================
Knowledge Base Ingestion for RAG
Loads documentation, FAQs, and policies into the vector store.

SOURCES:
- Training documents
- FAQ pages
- Company policies
- Product documentation
"""

import logging
import os
from typing import List, Dict, Any

from app.services.vector_store import get_vector_store

logger = logging.getLogger(__name__)


class KnowledgeIngestionService:
    """
    Ingests knowledge base content into the vector store.
    """
    
    def __init__(self):
        self.vector_store = get_vector_store()
    
    async def ingest_all(self) -> Dict[str, int]:
        """
        Ingest all knowledge sources.
        Returns count of documents ingested per category.
        """
        results = {
            "faq": 0,
            "training": 0,
            "policies": 0,
            "product_info": 0,
            "company_info": 0
        }
        
        # Ingest FAQ
        faq_count = await self.ingest_faq()
        results["faq"] = faq_count
        
        # Ingest training documents
        training_count = await self.ingest_training_docs()
        results["training"] = training_count
        
        # Ingest policies
        policies_count = await self.ingest_policies()
        results["policies"] = policies_count
        
        # Ingest product info
        product_count = await self.ingest_product_info()
        results["product_info"] = product_count
        
        # Ingest company info
        company_count = await self.ingest_company_info()
        results["company_info"] = company_count
        
        logger.info(f"📚 Knowledge ingestion complete: {results}")
        return results
    
    async def ingest_faq(self) -> int:
        """Ingest FAQ content."""
        faqs = [
            {
                "question": "How do I create a quotation?",
                "answer": "To create a quotation:\n1. Go to Marketing → Documents → Quotation\n2. Select customer\n3. Add items with quantities\n4. Set valid until date\n5. Click Save\n\nYou can also ask the AI: 'Create quotation for [customer] with [items]'"
            },
            {
                "question": "How do I check stock levels?",
                "answer": "To check stock levels:\n1. Go to Inventory → Stock Report\n2. Search by item code or name\n3. View current on-hand quantity\n\nYou can also ask the AI: 'Stock of [item name]'"
            },
            {
                "question": "How do I track a delivery?",
                "answer": "To track a delivery:\n1. Go to Marketing → Documents → Delivery\n2. Enter delivery number\n3. View status and tracking info\n\nYou can also ask the AI: 'Track delivery [number]'"
            },
            {
                "question": "What are your payment terms?",
                "answer": "Our standard payment terms:\n- 50% deposit upon order confirmation\n- 50% before delivery\n- For approved credit customers: Net 30 days\n- Accepted payment methods: M-Pesa, Bank Transfer, Cheque, Cash"
            },
            {
                "question": "How do I process a return?",
                "answer": "To process a return:\n1. Go to Marketing → Documents → Return\n2. Select original invoice\n3. Select items to return\n4. Specify reason\n5. Click Save\n\nReturns must be requested within 7 days of delivery."
            },
            {
                "question": "What is your delivery policy?",
                "answer": "Delivery Policy:\n- Nairobi: 1-2 business days\n- Other major towns: 3-5 business days\n- Remote areas: 5-7 business days\n- Free delivery on orders over KES 50,000\n- Same-day delivery available for orders before 11 AM (additional fee applies)"
            }
        ]
        
        documents = []
        for faq in faqs:
            documents.append({
                "content": f"Q: {faq['question']}\nA: {faq['answer']}",
                "metadata": {
                    "source": "faq",
                    "category": "help",
                    "question": faq["question"]
                }
            })
        
        doc_ids = await self.vector_store.add_documents_batch(documents)
        return len(doc_ids)
    
    async def ingest_training_docs(self) -> int:
        """Ingest training documentation."""
        training_docs = [
            {
                "title": "Sales Rep Quick Guide",
                "content": """
                LEYSCO SALES REP QUICK GUIDE
                
                Common Tasks:
                
                1. CHECKING PRICES
                - Ask AI: "Price of [product name]"
                - Or check customer-specific pricing: "Price of [product] for [customer]"
                
                2. CHECKING STOCK
                - Ask AI: "Stock level of [product]"
                - View warehouse stock: "Stock in [warehouse name]"
                
                3. CREATING QUOTATIONS
                - Ask AI: "Create quotation for [customer] with [quantity] [product]"
                - AI will guide you through the process
                
                4. TRACKING DELIVERIES
                - Ask AI: "Track delivery [number]"
                - View outstanding: "Outstanding deliveries"
                
                5. CUSTOMER MANAGEMENT
                - View customer details: "Customer details for [name]"
                - View orders: "Orders for [customer]"
                - View invoices: "Invoices for [customer]"
                
                6. ANALYTICS (Managers only)
                - "Show top selling items"
                - "Show slow moving items"
                - "Analyze inventory health"
                - "Show reorder decisions"
                """
            },
            {
                "title": "Product Categories Guide",
                "content": """
                LEYSCO PRODUCT CATEGORIES
                
                VEGETABLES:
                - Cabbage seeds (various varieties)
                - Tomato seeds (various varieties)
                - Onion seeds
                - Pepper seeds
                - Cucumber seeds
                
                FRUITS:
                - Watermelon seeds
                - Melon seeds
                - Strawberry seedlings
                
                CROPS:
                - Maize seeds
                - Wheat seeds
                - Rice seeds
                - Bean seeds
                
                AGROCHEMICALS:
                - Fertilizers (NPK, DAP, CAN, UREA)
                - Pesticides
                - Herbicides
                - Fungicides
                
                TOOLS & EQUIPMENT:
                - Sprayers
                - Irrigation equipment
                - Harvesting tools
                - Storage solutions
                """
            }
        ]
        
        documents = []
        for doc in training_docs:
            documents.append({
                "content": doc["content"],
                "metadata": {
                    "source": "training",
                    "category": "training",
                    "title": doc["title"]
                }
            })
        
        doc_ids = await self.vector_store.add_documents_batch(documents)
        return len(doc_ids)
    
    async def ingest_policies(self) -> int:
        """Ingest company policies."""
        policies = [
            {
                "title": "Return Policy",
                "content": """
                LEYSCO RETURN POLICY
                
                Eligibility:
                - Items must be returned within 7 days of delivery
                - Items must be in original condition and packaging
                - Proof of purchase required
                
                Non-returnable items:
                - Perishable goods (seeds, fresh produce)
                - Opened chemicals
                - Custom orders
                
                Process:
                1. Contact customer support with order number
                2. Get return authorization
                3. Ship items back (customer pays return shipping unless defective)
                4. Refund processed within 5-7 business days
                """
            },
            {
                "title": "Credit Policy",
                "content": """
                LEYSCO CREDIT POLICY
                
                Credit Terms:
                - Net 30 days for approved customers
                - 1.5% monthly late fee on overdue balances
                - Credit limit based on purchase history and payment record
                
                Credit Application:
                - Submit business registration certificate
                - Provide 3 trade references
                - Complete credit application form
                - Allow 5-7 business days for approval
                """
            }
        ]
        
        documents = []
        for policy in policies:
            documents.append({
                "content": policy["content"],
                "metadata": {
                    "source": "policy",
                    "category": "policy",
                    "title": policy["title"]
                }
            })
        
        doc_ids = await self.vector_store.add_documents_batch(documents)
        return len(doc_ids)
    
    async def ingest_product_info(self) -> int:
        """Ingest product information."""
        products = [
            {
                "name": "Vegimax",
                "content": """
                VEGIMAX - Premium Vegetable Fertilizer
                
                Benefits:
                - Balanced NPK formulation (14-14-14)
                - Promotes healthy leaf and root growth
                - Suitable for all vegetables
                
                Application:
                - Apply 50kg per acre
                - Apply at planting and 4 weeks after
                - Water thoroughly after application
                
                Available sizes:
                - 1kg (KES 750)
                - 5kg (KES 3,500)
                - 25kg (KES 16,000)
                - 50kg (KES 30,000)
                """
            },
            {
                "name": "Cabbage Seeds",
                "content": """
                CABBAGE SEEDS - Various Varieties
                
                Varieties:
                1. Gloria F1 - 60 days to harvest, disease resistant
                2. Riana F1 - 65 days to harvest, good for highlands
                3. Conquestador F1 - 70 days to harvest, large heads
                
                Planting Instructions:
                - Sow in nursery first
                - Transplant after 4-5 weeks
                - Spacing: 60cm x 60cm
                
                Seed rate: 200g per acre
                Expected yield: 15-20 tons per acre
                """
            }
        ]
        
        documents = []
        for product in products:
            documents.append({
                "content": product["content"],
                "metadata": {
                    "source": "product",
                    "category": "product",
                    "product_name": product["name"]
                }
            })
        
        doc_ids = await self.vector_store.add_documents_batch(documents)
        return len(doc_ids)
    
    async def ingest_company_info(self) -> int:
        """Ingest company information."""
        company_docs = [
            {
                "title": "About Leysco",
                "content": """
                ABOUT LEYSCO LIMITED
                
                Leysco Limited is a leading agricultural inputs distributor in Kenya.
                
                Founded: 2005
                
                Mission: To provide high-quality agricultural inputs that increase farm productivity.
                
                Products:
                - Seeds (vegetables, fruits, grains)
                - Fertilizers
                - Agrochemicals
                - Farm tools and equipment
                
                Locations:
                - Head Office: APA Arcade, Hurlingham, Nairobi
                - Warehouse: Industrial Area, Nairobi
                - Regional offices: Mombasa, Kisumu, Eldoret
                
                Contact:
                - Phone: +254(0) 780 457 591
                - Email: info@leysco.com
                - Website: www.leysco.com
                """
            }
        ]
        
        documents = []
        for doc in company_docs:
            documents.append({
                "content": doc["content"],
                "metadata": {
                    "source": "company",
                    "category": "company",
                    "title": doc["title"]
                }
            })
        
        doc_ids = await self.vector_store.add_documents_batch(documents)
        return len(doc_ids)


# Singleton instance
_knowledge_ingestion = None


def get_knowledge_ingestion_service() -> KnowledgeIngestionService:
    """Get or create KnowledgeIngestionService singleton."""
    global _knowledge_ingestion
    if _knowledge_ingestion is None:
        _knowledge_ingestion = KnowledgeIngestionService()
    return _knowledge_ingestion