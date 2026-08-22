import logging
from typing import List
from .ollama_client import OllamaClient
from core.config import get_config
import math

logger = logging.getLogger(__name__)

class EmbeddingManager:
    """Manages embedding generation and caching."""
    
    def __init__(self, ollama_client: OllamaClient):
        self.client = ollama_client
        self.config = get_config()
        self.model = self.config.get("models.embed", "nomic-embed-text")
        self.dim = 768
        self._cache = {}

    def _normalize(self, vector: List[float]) -> List[float]:
        """Normalize the embedding vector to unit length."""
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            return vector
        return [x / norm for x in vector]

    async def embed_text(self, text: str) -> List[float]:
        """Generate normalized embedding for a single text."""
        if text in self._cache:
            return self._cache[text]
            
        response = await self.client.embed(model=self.model, input_text=text)
        embeddings = response.get("embeddings", [])
        if not embeddings:
            raise ValueError("No embeddings returned")
            
        vector = embeddings[0]
        if len(vector) != self.dim:
            logger.warning(f"Expected embedding dimension {self.dim}, got {len(vector)}")
            
        normalized = self._normalize(vector)
        self._cache[text] = normalized
        return normalized

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate normalized embeddings for a batch of texts."""
        uncached_texts = [t for t in texts if t not in self._cache]
        
        if uncached_texts:
            response = await self.client.embed(model=self.model, input_text=uncached_texts)
            embeddings = response.get("embeddings", [])
            for text, vector in zip(uncached_texts, embeddings):
                self._cache[text] = self._normalize(vector)
                
        return [self._cache[t] for t in texts]
