"""
app/api/ai_routes/rag_handlers.py (P1.3 - Tenant-Secured)
===========================================================
RAG (Retrieval-Augmented Generation) handler with tenant isolation.

SECURITY:
- Tenant code is REQUIRED for all searches
- Results are filtered to the requesting tenant only
- Prevents cross-tenant data leakage
"""

import logging
from typing import Optional
from app.services.vector_store import get_vector_store

logger = logging.getLogger(__name__)


async def enhance_with_rag(
    query: str,
    tenant_code: str,
    min_similarity: float = 0.5,
    limit: int = 3
) -> Optional[str]:
    """
    Retrieve relevant knowledge base content to augment the LLM prompt.
    
    SECURITY:
    - Tenant code is REQUIRED
    - Only returns documents from the requesting tenant
    - Prevents data access across tenant boundaries
    
    Args:
        query: The user's search query
        tenant_code: The tenant making the request (REQUIRED for security)
        min_similarity: Minimum similarity threshold (0.0-1.0)
        limit: Maximum number of documents to retrieve
    
    Returns:
        Formatted context string or None if no results found
        
    Raises:
        ValueError: If tenant_code is missing
    """
    if not tenant_code:
        logger.warning("⚠️ RAG search attempted without tenant_code!")
        raise ValueError("tenant_code is required for RAG search")
    
    try:
        vector_store = get_vector_store()
        
        # Search with tenant filtering (security)
        results = await vector_store.search(
            query=query,
            tenant_code=tenant_code,  # ===== TENANT SECURITY =====
            limit=limit,
            min_similarity=min_similarity
        )
        
        if not results:
            logger.debug(f"No relevant documents found for tenant {tenant_code}")
            return None
        
        # Log retrieval
        logger.info(
            f"RAG retrieved {len(results)} documents for tenant {tenant_code} "
            f"(query: {query[:50]}...)"
        )
        
        # Build context from retrieved documents
        context_parts = []
        for i, doc in enumerate(results, 1):
            similarity_pct = doc["similarity"] * 100
            
            # Add document content with metadata
            header = f"[Document {i} - {similarity_pct:.0f}% match]"
            context_parts.append(f"{header}\n{doc['content']}")
        
        # Join with clear separators
        context = "\n\n" + "=" * 60 + "\n\n".join(context_parts)
        
        return context
        
    except ValueError as e:
        # Re-raise validation errors
        raise e
    
    except Exception as e:
        logger.error(f"RAG enhancement failed for tenant {tenant_code}: {e}")
        return None


async def enhance_with_rag_by_intent(
    intent: str,
    query: str,
    tenant_code: str
) -> Optional[str]:
    """
    Retrieve RAG context based on detected intent.
    
    Different intents may benefit from different search strategies.
    
    Args:
        intent: The detected user intent (e.g., GET_ITEMS, GET_CUSTOMERS)
        query: The original user query
        tenant_code: The tenant making the request
    
    Returns:
        Formatted context string or None
    """
    if not tenant_code:
        raise ValueError("tenant_code is required")
    
    # Intent-specific search strategies
    intent_config = {
        "GET_ITEMS": {
            "min_similarity": 0.6,  # Stricter for item searches
            "limit": 5,
        },
        "GET_CUSTOMERS": {
            "min_similarity": 0.5,
            "limit": 3,
        },
        "GET_PRICING": {
            "min_similarity": 0.7,  # Very strict for pricing
            "limit": 3,
        },
        "CREATE_QUOTATION": {
            "min_similarity": 0.5,
            "limit": 5,
        },
        "GET_WAREHOUSES": {
            "min_similarity": 0.6,
            "limit": 2,
        },
        "GET_STOCK_LEVELS": {
            "min_similarity": 0.6,
            "limit": 3,
        },
        "GET_OUTSTANDING_DELIVERIES": {
            "min_similarity": 0.5,
            "limit": 3,
        },
    }
    
    # Get config for this intent, or use defaults
    config = intent_config.get(intent, {"min_similarity": 0.5, "limit": 3})
    
    return await enhance_with_rag(
        query=query,
        tenant_code=tenant_code,
        min_similarity=config["min_similarity"],
        limit=config["limit"]
    )


async def get_rag_stats(tenant_code: str) -> dict:
    """
    Get statistics about the RAG knowledge base for a tenant.
    
    Args:
        tenant_code: The tenant to get stats for
    
    Returns:
        Dictionary with document count and other stats
    """
    if not tenant_code:
        raise ValueError("tenant_code is required")
    
    try:
        vector_store = get_vector_store()
        
        # Count documents for this tenant
        doc_count = await vector_store.count(tenant_code=tenant_code)
        
        # Total documents across all tenants
        total_docs = await vector_store.count(tenant_code=None)
        
        return {
            "tenant_code": tenant_code,
            "documents_in_tenant": doc_count,
            "total_documents": total_docs,
            "percentage_of_total": (doc_count / total_docs * 100) if total_docs > 0 else 0,
        }
    
    except Exception as e:
        logger.error(f"Failed to get RAG stats: {e}")
        return {"error": str(e)}


async def search_knowledge_base(
    query: str,
    tenant_code: str,
    limit: int = 5,
    as_raw_documents: bool = False
) -> Optional[str | list]:
    """
    Direct search on the knowledge base for user queries.
    
    This is different from enhance_with_rag() which augments LLM prompts.
    This returns results directly to the user.
    
    Args:
        query: Search query
        tenant_code: Tenant making the request
        limit: Number of results
        as_raw_documents: If True, return raw document list. If False, format as text.
    
    Returns:
        Formatted text response or list of documents
    """
    if not tenant_code:
        raise ValueError("tenant_code is required")
    
    try:
        vector_store = get_vector_store()
        
        results = await vector_store.search(
            query=query,
            tenant_code=tenant_code,
            limit=limit,
            min_similarity=0.4  # Lower threshold for user-facing search
        )
        
        if not results:
            return "No relevant information found in the knowledge base."
        
        if as_raw_documents:
            return results
        
        # Format as readable text
        lines = [f"Found {len(results)} relevant documents:\n"]
        for i, doc in enumerate(results, 1):
            similarity_pct = doc["similarity"] * 100
            lines.append(f"\n{i}. [{similarity_pct:.0f}% match] {doc['content'][:200]}...")
        
        return "\n".join(lines)
    
    except Exception as e:
        logger.error(f"Knowledge base search failed: {e}")
        return f"Search failed: {str(e)}"