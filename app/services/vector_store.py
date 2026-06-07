"""
app/services/vector_store.py (P1.3 - Tenant-Scoped)
====================================================
Vector Database Service for RAG with Tenant Isolation

CHANGES:
- All documents tagged with tenant_code in metadata
- Search filtered by tenant_code (data isolation)
- Async/await for PostgreSQL operations
- asyncpg for efficient async database access
"""

import logging
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import uuid
import asyncio

from app.services.cache_service import get_cache_service
from app.services.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)

# Try to import asyncpg for async PostgreSQL
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    logger.warning("asyncpg not installed. Using in-memory vector store only.")


@dataclass
class Document:
    """Document for vector storage"""
    id: str
    content: str
    metadata: Dict[str, Any]  # MUST include tenant_code
    embedding: Optional[List[float]] = None


class VectorStore:
    """
    Async vector database for semantic search with tenant scoping.
    
    SECURITY:
    - Every document MUST have metadata['tenant_code']
    - Search always filters by tenant_code
    - Data from different tenants is completely isolated
    """
    
    def __init__(self):
        self.cache = get_cache_service()
        self.embedding_service = get_embedding_service()
        self._in_memory_docs: List[Document] = []
        self._db_pool = None  # asyncpg connection pool
        self._init_task = None
    
    async def initialize(self):
        """Initialize PostgreSQL connection pool (async). Call on app startup."""
        if not ASYNCPG_AVAILABLE:
            logger.warning("asyncpg not available. Vector store in memory only.")
            return
        
        try:
            import os
            
            # Create connection pool
            self._db_pool = await asyncpg.create_pool(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                database=os.getenv("POSTGRES_DB", "leysco_ai"),
                user=os.getenv("POSTGRES_USER", "postgres"),
                password=os.getenv("POSTGRES_PASSWORD", "postgres"),
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            
            # Create extension and table
            async with self._db_pool.acquire() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                
                # Create documents table if not exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS vector_documents (
                        id TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        metadata JSONB NOT NULL,
                        embedding vector(384),
                        tenant_code TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                
                # Create indexes for performance
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS documents_tenant_idx 
                    ON vector_documents (tenant_code)
                """)
                
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS documents_embedding_idx 
                    ON vector_documents USING ivfflat (embedding vector_cosine_ops)
                    WHERE tenant_code IS NOT NULL
                """)
            
            logger.info("✅ Async PostgreSQL vector store initialized with tenant scoping")
            
        except Exception as e:
            logger.error(f"PostgreSQL initialization failed: {e}. Falling back to in-memory.")
            self._db_pool = None
    
    async def add_document(
        self,
        content: str,
        metadata: Dict[str, Any],
        tenant_code: str,
        embedding: Optional[List[float]] = None
    ) -> str:
        """
        Add a document to the vector store.
        
        Args:
            content: The document text
            metadata: Additional metadata (source, category, etc.)
            tenant_code: The tenant this document belongs to
            embedding: Optional pre-computed embedding
        
        Returns:
            Document ID
            
        Raises:
            ValueError: If tenant_code is missing
        """
        if not tenant_code:
            raise ValueError("tenant_code is required for vector store isolation")
        
        doc_id = str(uuid.uuid4())
        
        # Ensure tenant_code is in metadata
        metadata["tenant_code"] = tenant_code
        
        # Generate embedding if not provided
        if embedding is None:
            embedding = await self.embedding_service.embed(content)
        
        if embedding is None:
            logger.warning(f"Failed to generate embedding for document {doc_id}")
            return doc_id
        
        # Store in PostgreSQL if available
        if self._db_pool:
            try:
                async with self._db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO vector_documents 
                        (id, content, metadata, embedding, tenant_code)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        doc_id,
                        content,
                        json.dumps(metadata),
                        embedding,
                        tenant_code,
                    )
                logger.debug(f"✅ Document {doc_id} added to PostgreSQL (tenant: {tenant_code})")
                return doc_id
            except Exception as e:
                logger.error(f"Failed to add document to PostgreSQL: {e}")
        
        # Fallback to in-memory
        doc = Document(
            id=doc_id,
            content=content,
            metadata=metadata,
            embedding=embedding
        )
        self._in_memory_docs.append(doc)
        logger.debug(f"✅ Document {doc_id} added to in-memory store (tenant: {tenant_code})")
        
        return doc_id
    
    async def add_documents_batch(
        self,
        documents: List[Dict[str, Any]],
        tenant_code: str
    ) -> List[str]:
        """
        Add multiple documents to the vector store.
        
        Args:
            documents: List of {"content": str, "metadata": dict}
            tenant_code: The tenant these documents belong to
        
        Returns:
            List of document IDs
        """
        if not tenant_code:
            raise ValueError("tenant_code is required for batch add")
        
        # Generate embeddings in batch
        contents = [doc["content"] for doc in documents]
        embeddings = await self.embedding_service.embed_batch(contents)
        
        doc_ids = []
        for i, doc in enumerate(documents):
            doc_id = await self.add_document(
                content=doc["content"],
                metadata=doc.get("metadata", {}),
                tenant_code=tenant_code,
                embedding=embeddings[i] if i < len(embeddings) else None
            )
            doc_ids.append(doc_id)
        
        return doc_ids
    
    async def search(
        self,
        query: str,
        tenant_code: str,
        limit: int = 5,
        min_similarity: float = 0.5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents using semantic search.
        
        SECURITY: Automatically filters by tenant_code.
        
        Args:
            query: The search query
            tenant_code: Tenant making the request (REQUIRED for security)
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold (0.0-1.0)
            filter_metadata: Optional additional metadata filter
        
        Returns:
            List of matching documents with similarity scores (same tenant only)
        
        Raises:
            ValueError: If tenant_code is missing
        """
        if not tenant_code:
            raise ValueError("tenant_code is required for secure search")
        
        # Generate query embedding
        query_embedding = await self.embedding_service.embed(query)
        
        if query_embedding is None:
            logger.warning("Failed to generate query embedding")
            return []
        
        # Search in PostgreSQL if available
        if self._db_pool:
            try:
                async with self._db_pool.acquire() as conn:
                    # Build parameterized query with tenant filtering
                    sql = """
                        SELECT 
                            id, content, metadata, 
                            1 - (embedding <=> $1::vector) as similarity
                        FROM vector_documents
                        WHERE tenant_code = $2
                    """
                    params = [query_embedding, tenant_code]
                    
                    # Add optional metadata filters
                    if filter_metadata:
                        for key, value in filter_metadata.items():
                            sql += f" AND metadata->>${ len(params) + 1 } = ${ len(params) + 2 }"
                            params.append(key)
                            params.append(str(value))
                    
                    sql += " ORDER BY embedding <=> $1::vector LIMIT $" + str(len(params) + 1)
                    params.append(limit)
                    
                    results = await conn.fetch(sql, *params)
                    
                    return [
                        {
                            "id": row["id"],
                            "content": row["content"],
                            "metadata": json.loads(row["metadata"]),
                            "similarity": float(row["similarity"])
                        }
                        for row in results
                        if float(row["similarity"]) >= min_similarity
                    ]
            except Exception as e:
                logger.error(f"PostgreSQL search failed: {e}")
        
        # Fallback to in-memory search (with tenant filtering)
        results = []
        for doc in self._in_memory_docs:
            # ===== TENANT SECURITY CHECK =====
            if doc.metadata.get("tenant_code") != tenant_code:
                continue  # Skip documents from other tenants
            
            if doc.embedding is None:
                continue
            
            # Calculate cosine similarity
            similarity = self._cosine_similarity(query_embedding, doc.embedding)
            
            if similarity >= min_similarity:
                results.append({
                    "id": doc.id,
                    "content": doc.content,
                    "metadata": doc.metadata,
                    "similarity": similarity
                })
        
        # Sort by similarity and limit
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0
        
        return dot_product / (norm_a * norm_b)
    
    async def delete_document(self, doc_id: str, tenant_code: str) -> bool:
        """
        Delete a document from the vector store.
        
        SECURITY: Can only delete documents from your own tenant.
        """
        if self._db_pool:
            try:
                async with self._db_pool.acquire() as conn:
                    # Only allow deletion if document belongs to tenant
                    result = await conn.execute(
                        """
                        DELETE FROM vector_documents 
                        WHERE id = $1 AND tenant_code = $2
                        """,
                        doc_id,
                        tenant_code,
                    )
                    return result == "DELETE 1"
            except Exception as e:
                logger.error(f"Failed to delete document: {e}")
        
        # Remove from in-memory (with tenant check)
        original_len = len(self._in_memory_docs)
        self._in_memory_docs = [
            d for d in self._in_memory_docs 
            if not (d.id == doc_id and d.metadata.get("tenant_code") == tenant_code)
        ]
        return len(self._in_memory_docs) < original_len
    
    async def count(self, tenant_code: Optional[str] = None) -> int:
        """
        Get total number of documents in the vector store.
        
        If tenant_code provided: count for that tenant only.
        If tenant_code None: count across all tenants.
        """
        if self._db_pool:
            try:
                async with self._db_pool.acquire() as conn:
                    if tenant_code:
                        result = await conn.fetchval(
                            "SELECT COUNT(*) FROM vector_documents WHERE tenant_code = $1",
                            tenant_code
                        )
                    else:
                        result = await conn.fetchval(
                            "SELECT COUNT(*) FROM vector_documents"
                        )
                    return result or 0
            except Exception as e:
                logger.error(f"Failed to count documents: {e}")
        
        # In-memory count (with tenant filter)
        if tenant_code:
            return sum(
                1 for d in self._in_memory_docs 
                if d.metadata.get("tenant_code") == tenant_code
            )
        return len(self._in_memory_docs)
    
    async def clear_tenant_documents(self, tenant_code: str) -> int:
        """
        Delete all documents for a specific tenant.
        
        USE WITH CARE: This is permanent.
        """
        if self._db_pool:
            try:
                async with self._db_pool.acquire() as conn:
                    result = await conn.execute(
                        "DELETE FROM vector_documents WHERE tenant_code = $1",
                        tenant_code
                    )
                    # Extract count from result string
                    count = int(result.split()[-1]) if result else 0
                    logger.info(f"Deleted {count} documents for tenant {tenant_code}")
                    return count
            except Exception as e:
                logger.error(f"Failed to clear tenant documents: {e}")
        
        # In-memory clear
        original_len = len(self._in_memory_docs)
        self._in_memory_docs = [
            d for d in self._in_memory_docs 
            if d.metadata.get("tenant_code") != tenant_code
        ]
        removed = original_len - len(self._in_memory_docs)
        logger.info(f"Cleared {removed} in-memory documents for tenant {tenant_code}")
        return removed
    
    async def close(self):
        """Close database pool (call on app shutdown)."""
        if self._db_pool:
            await self._db_pool.close()
            logger.info("Vector store connection pool closed")


# ============================================================================
# SINGLETON MANAGEMENT
# ============================================================================

_vector_store = None


def get_vector_store() -> VectorStore:
    """Get or create VectorStore singleton."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


async def init_vector_store():
    """Initialize vector store (call on app startup)."""
    store = get_vector_store()
    await store.initialize()
    return store


async def close_vector_store():
    """Close vector store (call on app shutdown)."""
    if _vector_store:
        await _vector_store.close()