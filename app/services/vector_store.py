"""
app/services/vector_store.py
=============================
Vector Database Service for RAG
Stores and retrieves document embeddings for semantic search.

SUPPORTS:
- PostgreSQL with pgvector (recommended)
- In-memory fallback (for testing)
"""

import logging
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import uuid

from app.services.cache_service import get_cache_service
from app.services.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)

# Try to import psycopg2 for PostgreSQL
try:
    import psycopg2
    from psycopg2.extras import Json
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False
    logger.warning("psycopg2 not installed. Using in-memory vector store.")


@dataclass
class Document:
    """Document for vector storage"""
    id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None


class VectorStore:
    """
    Vector database for semantic search.
    Uses PostgreSQL with pgvector or falls back to in-memory.
    """
    
    def __init__(self):
        self.cache = get_cache_service()
        self.embedding_service = get_embedding_service()
        self._in_memory_docs: List[Document] = []
        self._pg_connection = None
        self._init_postgres()
    
    def _init_postgres(self):
        """Initialize PostgreSQL connection with pgvector."""
        if not PG_AVAILABLE:
            return
        
        try:
            # Connect to PostgreSQL (configure these in .env)
            import os
            self._pg_connection = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", "5432"),
                database=os.getenv("POSTGRES_DB", "leysco_ai"),
                user=os.getenv("POSTGRES_USER", "postgres"),
                password=os.getenv("POSTGRES_PASSWORD", "postgres")
            )
            
            # Create vector extension if not exists
            cursor = self._pg_connection.cursor()
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
            # Create documents table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vector_documents (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    metadata JSONB,
                    embedding vector(384),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Create index for similarity search
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS documents_embedding_idx 
                ON vector_documents USING ivfflat (embedding vector_cosine_ops)
            """)
            
            self._pg_connection.commit()
            logger.info("✅ PostgreSQL vector store initialized")
            
        except Exception as e:
            logger.warning(f"PostgreSQL connection failed: {e}. Using in-memory store.")
            self._pg_connection = None
    
    async def add_document(
        self,
        content: str,
        metadata: Dict[str, Any],
        embedding: Optional[List[float]] = None
    ) -> str:
        """
        Add a document to the vector store.
        
        Args:
            content: The document text
            metadata: Additional metadata (source, category, etc.)
            embedding: Optional pre-computed embedding
        
        Returns:
            Document ID
        """
        doc_id = str(uuid.uuid4())
        
        # Generate embedding if not provided
        if embedding is None:
            embedding = await self.embedding_service.embed(content)
        
        if embedding is None:
            logger.warning(f"Failed to generate embedding for document {doc_id}")
            return doc_id
        
        # Store in PostgreSQL if available
        if self._pg_connection:
            try:
                cursor = self._pg_connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO vector_documents (id, content, metadata, embedding)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (doc_id, content, json.dumps(metadata), embedding)
                )
                self._pg_connection.commit()
                logger.debug(f"✅ Document {doc_id} added to PostgreSQL vector store")
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
        logger.debug(f"✅ Document {doc_id} added to in-memory vector store")
        
        return doc_id
    
    async def add_documents_batch(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Add multiple documents to the vector store.
        
        Args:
            documents: List of {"content": str, "metadata": dict}
        
        Returns:
            List of document IDs
        """
        # Generate embeddings in batch
        contents = [doc["content"] for doc in documents]
        embeddings = await self.embedding_service.embed_batch(contents)
        
        doc_ids = []
        for i, doc in enumerate(documents):
            doc_id = await self.add_document(
                content=doc["content"],
                metadata=doc.get("metadata", {}),
                embedding=embeddings[i] if i < len(embeddings) else None
            )
            doc_ids.append(doc_id)
        
        return doc_ids
    
    async def search(
        self,
        query: str,
        limit: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents using semantic search.
        
        Args:
            query: The search query
            limit: Maximum number of results
            filter_metadata: Optional metadata filter
        
        Returns:
            List of matching documents with similarity scores
        """
        # Generate query embedding
        query_embedding = await self.embedding_service.embed(query)
        
        if query_embedding is None:
            logger.warning("Failed to generate query embedding")
            return []
        
        # Search in PostgreSQL if available
        if self._pg_connection:
            try:
                cursor = self._pg_connection.cursor()
                
                # Build query with optional metadata filter
                sql = """
                    SELECT id, content, metadata, 1 - (embedding <=> %s::vector) as similarity
                    FROM vector_documents
                """
                params = [query_embedding]
                
                if filter_metadata:
                    # Simple metadata filter (can be extended)
                    for key, value in filter_metadata.items():
                        sql += f" AND metadata->>'{key}' = %s"
                        params.append(str(value))
                
                sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
                params.append(query_embedding)
                params.append(limit)
                
                cursor.execute(sql, params)
                results = cursor.fetchall()
                
                return [
                    {
                        "id": row[0],
                        "content": row[1],
                        "metadata": row[2],
                        "similarity": float(row[3])
                    }
                    for row in results
                ]
            except Exception as e:
                logger.error(f"PostgreSQL search failed: {e}")
        
        # Fallback to in-memory search (brute force)
        results = []
        for doc in self._in_memory_docs:
            if doc.embedding is None:
                continue
            
            # Calculate cosine similarity
            similarity = self._cosine_similarity(query_embedding, doc.embedding)
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
    
    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document from the vector store."""
        if self._pg_connection:
            try:
                cursor = self._pg_connection.cursor()
                cursor.execute("DELETE FROM vector_documents WHERE id = %s", (doc_id,))
                self._pg_connection.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to delete document: {e}")
        
        # Remove from in-memory
        self._in_memory_docs = [d for d in self._in_memory_docs if d.id != doc_id]
        return True
    
    async def count(self) -> int:
        """Get total number of documents in the vector store."""
        if self._pg_connection:
            try:
                cursor = self._pg_connection.cursor()
                cursor.execute("SELECT COUNT(*) FROM vector_documents")
                return cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"Failed to count documents: {e}")
        
        return len(self._in_memory_docs)


# Singleton instance
_vector_store = None


def get_vector_store() -> VectorStore:
    """Get or create VectorStore singleton."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store