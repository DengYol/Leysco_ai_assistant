"""RAG (Retrieval-Augmented Generation) handlers"""

from typing import Optional
from app.services.vector_store import get_vector_store
import logging

logger = logging.getLogger(__name__)


async def enhance_with_rag(query: str, tenant_code: str) -> Optional[str]:
    """
    Retrieve relevant knowledge base content to augment the prompt.
    """
    try:
        vector_store = get_vector_store()
        
        # Search for relevant documents
        results = await vector_store.search(query, limit=3)
        
        if not results:
            return None
        
        # Filter by similarity threshold (0.5 = moderately similar)
        relevant_docs = [r for r in results if r["similarity"] > 0.5]
        
        if not relevant_docs:
            return None
        
        # Build context from retrieved documents
        context_parts = []
        for doc in relevant_docs:
            context_parts.append(doc["content"])
        
        context = "\n\n---\n\n".join(context_parts)
        
        logger.info(f"RAG retrieved {len(relevant_docs)} relevant documents")
        return context
        
    except Exception as e:
        logger.error(f"RAG enhancement failed: {e}")
        return None