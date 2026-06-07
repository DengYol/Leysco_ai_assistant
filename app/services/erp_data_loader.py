"""
app/services/erp_data_loader.py (NEW for P1.3)
===============================================
Load ERP data into the vector store for RAG.

This service:
1. Fetches items, customers, pricing from ERP API
2. Converts ERP data into knowledge base documents
3. Stores in vector database with embeddings
4. Runs on app startup and on schedule (hourly)
5. Implements per-tenant loading
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.services.vector_store import get_vector_store
from app.services.leysco_api.client import get_leysco_api_client
from app.services.cache_service import get_cache_service
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ERPDataLoader:
    """Load ERP data into vector store for RAG."""
    
    def __init__(self):
        self.vector_store = get_vector_store()
        self.cache = get_cache_service()
        self.settings = get_settings()
        self._last_load_time: Dict[str, datetime] = {}
    
    async def load_all_tenant_data(self):
        """
        Load ERP data for all configured tenants.
        
        Call this on app startup to populate vector store.
        """
        # Get list of tenant codes from config
        tenant_codes = self._get_configured_tenants()
        
        logger.info(f"Loading ERP data for {len(tenant_codes)} tenants...")
        
        for tenant_code in tenant_codes:
            try:
                await self.load_tenant_data(tenant_code)
            except Exception as e:
                logger.error(f"Failed to load ERP data for tenant {tenant_code}: {e}")
        
        logger.info("✅ ERP data loading complete")
    
    async def load_tenant_data(self, tenant_code: str):
        """
        Load all ERP data for a specific tenant into vector store.
        
        Args:
            tenant_code: The tenant to load data for
        """
        if not tenant_code:
            raise ValueError("tenant_code is required")
        
        # Check if we've loaded recently (avoid hammering ERP API)
        cache_key = f"erp_load_time:{tenant_code}"
        last_load = self.cache.get_simple(cache_key)
        
        if last_load and isinstance(last_load, str):
            last_load_dt = datetime.fromisoformat(last_load)
            if datetime.utcnow() - last_load_dt < timedelta(minutes=30):
                logger.info(f"Skipping reload for {tenant_code} (recently loaded)")
                return
        
        logger.info(f"Loading ERP data for tenant: {tenant_code}")
        
        try:
            api = get_leysco_api_client(tenant_code)
            
            # Load items
            items_docs = await self._load_items(api, tenant_code)
            logger.info(f"Loaded {len(items_docs)} item documents for {tenant_code}")
            
            # Load customers
            customers_docs = await self._load_customers(api, tenant_code)
            logger.info(f"Loaded {len(customers_docs)} customer documents for {tenant_code}")
            
            # Load pricing matrix
            pricing_docs = await self._load_pricing(api, tenant_code)
            logger.info(f"Loaded {len(pricing_docs)} pricing documents for {tenant_code}")
            
            # Load warehouse info
            warehouse_docs = await self._load_warehouses(api, tenant_code)
            logger.info(f"Loaded {len(warehouse_docs)} warehouse documents for {tenant_code}")
            
            # Total loaded
            total_docs = len(items_docs) + len(customers_docs) + len(pricing_docs) + len(warehouse_docs)
            
            # Clear old data for this tenant to avoid duplicates
            await self.vector_store.clear_tenant_documents(tenant_code)
            
            # Add all new documents
            all_docs = items_docs + customers_docs + pricing_docs + warehouse_docs
            doc_ids = await self.vector_store.add_documents_batch(all_docs, tenant_code)
            
            logger.info(f"✅ Stored {len(doc_ids)} documents in vector store for {tenant_code}")
            
            # Update load time
            self.cache.set_simple(
                cache_key,
                datetime.utcnow().isoformat(),
                ttl=3600  # Cache for 1 hour
            )
        
        except Exception as e:
            logger.error(f"Failed to load ERP data for {tenant_code}: {e}")
            raise
    
    async def _load_items(self, api, tenant_code: str) -> List[Dict[str, Any]]:
        """Load items from ERP into documents."""
        try:
            items = await api.get_items()
            documents = []
            
            # Group items by category for context
            by_category = {}
            for item in items:
                cat = item.get("category", "Other")
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(item)
            
            # Create document per category
            for category, cat_items in by_category.items():
                # Build category summary
                item_names = ", ".join([
                    f"{it.get('name')} (SKU: {it.get('sku')})"
                    for it in cat_items[:10]
                ])
                
                content = f"""
PRODUCT CATEGORY: {category}

Products in this category:
{item_names}

This category contains {len(cat_items)} products total.
Common uses: {category} products are used for crop management and farming operations.
"""
                
                documents.append({
                    "content": content.strip(),
                    "metadata": {
                        "source": "ERP",
                        "type": "product_category",
                        "category": category,
                        "item_count": len(cat_items),
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                })
            
            return documents
        
        except Exception as e:
            logger.warning(f"Failed to load items for {tenant_code}: {e}")
            return []
    
    async def _load_customers(self, api, tenant_code: str) -> List[Dict[str, Any]]:
        """Load customer data from ERP into documents."""
        try:
            customers = await api.get_customers()
            documents = []
            
            # Group customers by region
            by_region = {}
            for cust in customers:
                region = cust.get("region", "Unspecified")
                if region not in by_region:
                    by_region[region] = []
                by_region[region].append(cust)
            
            # Create document per region
            for region, region_customers in by_region.items():
                cust_summary = ", ".join([
                    cust.get("name", "Unknown")
                    for cust in region_customers[:20]
                ])
                
                content = f"""
CUSTOMER REGION: {region}

Active customers in {region}:
{cust_summary}

This region has {len(region_customers)} customers.
Total customer base contact: This region is an important sales territory.
"""
                
                documents.append({
                    "content": content.strip(),
                    "metadata": {
                        "source": "ERP",
                        "type": "customer_region",
                        "region": region,
                        "customer_count": len(region_customers),
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                })
            
            return documents
        
        except Exception as e:
            logger.warning(f"Failed to load customers for {tenant_code}: {e}")
            return []
    
    async def _load_pricing(self, api, tenant_code: str) -> List[Dict[str, Any]]:
        """Load pricing information from ERP into documents."""
        try:
            # Fetch items to get pricing
            items = await api.get_items()
            documents = []
            
            # Group by price range
            price_ranges = {
                "budget": [],
                "mid_range": [],
                "premium": [],
            }
            
            for item in items:
                price = item.get("unit_price", 0)
                
                if price < 100:
                    price_ranges["budget"].append(item)
                elif price < 500:
                    price_ranges["mid_range"].append(item)
                else:
                    price_ranges["premium"].append(item)
            
            # Create document per price range
            for range_name, range_items in price_ranges.items():
                if not range_items:
                    continue
                
                items_list = ", ".join([
                    f"{it.get('name')} (KES {it.get('unit_price')})"
                    for it in range_items[:10]
                ])
                
                content = f"""
PRICE RANGE: {range_name.replace('_', ' ').upper()}

Products in this price range:
{items_list}

Total products: {len(range_items)}
Price range strategy: {range_name.replace('_', ' ').title()} products are important for market segmentation.
"""
                
                documents.append({
                    "content": content.strip(),
                    "metadata": {
                        "source": "ERP",
                        "type": "pricing_range",
                        "price_range": range_name,
                        "item_count": len(range_items),
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                })
            
            return documents
        
        except Exception as e:
            logger.warning(f"Failed to load pricing for {tenant_code}: {e}")
            return []
    
    async def _load_warehouses(self, api, tenant_code: str) -> List[Dict[str, Any]]:
        """Load warehouse information from ERP into documents."""
        try:
            warehouses = await api.get_warehouses()
            documents = []
            
            if not warehouses:
                return []
            
            # Create a comprehensive warehouse document
            warehouse_summary = "\n".join([
                f"- {wh.get('name')} ({wh.get('location')})"
                for wh in warehouses
            ])
            
            content = f"""
WAREHOUSE NETWORK

Leysco operates {len(warehouses)} warehouses:

{warehouse_summary}

Warehouse Management:
- Orders are fulfilled from the nearest warehouse to reduce delivery time
- Stock availability varies by location
- Cross-warehouse transfers available for customer orders
- Ask about "Stock in [warehouse name]" to check location-specific inventory
"""
            
            documents.append({
                "content": content.strip(),
                "metadata": {
                    "source": "ERP",
                    "type": "warehouse_info",
                    "warehouse_count": len(warehouses),
                    "updated_at": datetime.utcnow().isoformat(),
                }
            })
            
            return documents
        
        except Exception as e:
            logger.warning(f"Failed to load warehouses for {tenant_code}: {e}")
            return []
    
    def _get_configured_tenants(self) -> List[str]:
        """Get list of all configured tenant codes."""
        # This reads from config - customize based on your multi-tenant setup
        # Example: Extract from environment variables or database
        
        tenant_codes = []
        
        # Method 1: From environment variables (LEYSCO_TENANTS=TEST001,TEST009,PROD001)
        import os
        env_tenants = os.getenv("LEYSCO_TENANTS", "TEST001,TEST009")
        tenant_codes.extend([t.strip() for t in env_tenants.split(",")])
        
        # Method 2: From config file (if you have one)
        # tenant_codes.extend(self.settings.multi_tenant_codes)
        
        return list(set(tenant_codes))  # Remove duplicates


# ============================================================================
# SINGLETON MANAGEMENT
# ============================================================================

_loader = None


def get_erp_data_loader() -> ERPDataLoader:
    """Get or create ERPDataLoader singleton."""
    global _loader
    if _loader is None:
        _loader = ERPDataLoader()
    return _loader


async def load_erp_data_on_startup():
    """
    Call this in your app startup event to load ERP data.
    
    Usage in main.py:
    
    @app.on_event("startup")
    async def startup_event():
        await load_erp_data_on_startup()
    """
    try:
        loader = get_erp_data_loader()
        await loader.load_all_tenant_data()
        logger.info("✅ ERP data loader initialized")
    except Exception as e:
        logger.error(f"Failed to initialize ERP data loader: {e}")
        # Don't crash the app, but log the error


async def schedule_erp_data_refresh():
    """
    Periodically refresh ERP data (run in background).
    
    Call this in APScheduler to refresh data hourly:
    
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(schedule_erp_data_refresh, 'interval', minutes=60)
    scheduler.start()
    """
    try:
        loader = get_erp_data_loader()
        await loader.load_all_tenant_data()
        logger.info("✅ ERP data refresh completed")
    except Exception as e:
        logger.error(f"ERP data refresh failed: {e}")