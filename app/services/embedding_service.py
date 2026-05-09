"""
app/services/embedding_service.py
==================================
Embedding Service for RAG (Retrieval-Augmented Generation)
Converts text to vector embeddings for semantic search.

SUPPORTS:
- Sentence Transformers (local, free)
- OpenAI embeddings (optional, more accurate)
- Gemini embeddings (optional)
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# Try to import sentence-transformers (local, free)
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMER_AVAILABLE = True
    logger.info("✅ SentenceTransformer available (local embeddings)")
except ImportError:
    SENTENCE_TRANSFORMER_AVAILABLE = False
    logger.warning("SentenceTransformer not installed. Install with: pip install sentence-transformers")

# Try to import OpenAI embeddings (optional)
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.debug("OpenAI not available (optional)")

# Try to import Google Gemini embeddings (optional)
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.debug("Google Gemini not available (optional)")


class EmbeddingService:
    """
    Service for generating text embeddings.
    Falls back to local SentenceTransformer if available.
    """
    
    # Embedding dimension for different models
    DIMENSIONS = {
        "all-MiniLM-L6-v2": 384,      # Default local model
        "all-mpnet-base-v2": 768,     # More accurate local model
        "text-embedding-ada-002": 1536, # OpenAI
        "models/embedding-001": 768,   # Gemini
    }
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the embedding model."""
        if SENTENCE_TRANSFORMER_AVAILABLE:
            try:
                self.model = SentenceTransformer(self.model_name)
                logger.info(f"✅ Embedding model loaded: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                self.model = None
        else:
            logger.warning("No embedding model available. RAG will be disabled.")
    
    def get_dimension(self) -> int:
        """Get the embedding dimension for the current model."""
        return self.DIMENSIONS.get(self.model_name, 384)
    
    async def embed(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding vector for a single text.
        
        Args:
            text: The text to embed
        
        Returns:
            List of floats (embedding vector) or None if failed
        """
        if not self.model:
            logger.warning("Embedding model not available")
            return None
        
        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None, lambda: self.model.encode(text).tolist()
            )
            return embedding
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return None
    
    async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embedding vectors for multiple texts.
        
        Args:
            texts: List of texts to embed
        
        Returns:
            List of embedding vectors (None for failures)
        """
        if not self.model:
            logger.warning("Embedding model not available")
            return [None] * len(texts)
        
        try:
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None, lambda: self.model.encode(texts).tolist()
            )
            return embeddings
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            return [None] * len(texts)
    
    @lru_cache(maxsize=1000)
    def embed_sync(self, text: str) -> Optional[List[float]]:
        """Synchronous embedding with caching."""
        if not self.model:
            return None
        try:
            return self.model.encode(text).tolist()
        except Exception as e:
            logger.error(f"Sync embedding failed: {e}")
            return None


# Singleton instance
_embedding_service = None


def get_embedding_service() -> EmbeddingService:
    """Get or create EmbeddingService singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service