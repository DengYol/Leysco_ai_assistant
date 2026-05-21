"""RAG (Retrieval-Augmented Generation) knowledge base endpoints (Manager only)"""

from fastapi import APIRouter, Depends, Query
from typing import Dict
import logging

from .utils import utf8_json_response
from app.api.dependencies import require_manager_role
from app.services.vector_store import get_vector_store
from app.services.knowledge_ingestion import get_knowledge_ingestion_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/knowledge/ingest")
async def ingest_knowledge_base(
    context: Dict = Depends(require_manager_role)
):
    """
    Ingest all knowledge base content into vector store.
    Manager-only endpoint.
    """
    ingestion_service = get_knowledge_ingestion_service()
    results = await ingestion_service.ingest_all()
    
    vector_store = get_vector_store()
    total_docs = await vector_store.count()
    
    return utf8_json_response({
        "success": True,
        "documents_ingested": results,
        "total_documents": total_docs,
        "message": "Knowledge base ingestion complete"
    })


@router.get("/knowledge/search")
async def search_knowledge_base(
    query: str,
    limit: int = Query(5, ge=1, le=10),
    context: Dict = Depends(require_manager_role)
):
    """
    Search the knowledge base.
    Manager-only endpoint.
    """
    vector_store = get_vector_store()
    results = await vector_store.search(query, limit=limit)
    
    return utf8_json_response({
        "success": True,
        "query": query,
        "results": [
            {
                "content": r["content"],
                "metadata": r["metadata"],
                "similarity": r["similarity"]
            }
            for r in results
        ]
    })


@router.get("/knowledge/stats")
async def get_knowledge_stats(
    context: Dict = Depends(require_manager_role)
):
    """
    Get knowledge base statistics.
    Manager-only endpoint.
    """
    vector_store = get_vector_store()
    total_docs = await vector_store.count()
    
    return utf8_json_response({
        "success": True,
        "total_documents": total_docs,
        "vector_store_type": "postgresql" if vector_store._pg_connection else "in_memory",
        "embedding_dimension": 384
    })