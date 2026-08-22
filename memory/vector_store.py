import os
import chromadb
from typing import Any, Dict, List, Optional
from models.embeddings import EmbeddingManager
import logging

logger = logging.getLogger(__name__)

class VectorStore:
    """Wrapper around ChromaDB for vector storage."""
    
    def __init__(self, data_dir: str, embedding_manager: EmbeddingManager):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.data_dir)
        self.embedding_manager = embedding_manager
        
        self.collections = {}
        for name in ["emails", "tasks", "documents", "opportunities", "memories", "notes"]:
            self.collections[name] = self.client.get_or_create_collection(name=name)

    async def add(self, collection_name: str, id: str, text: str, metadata: Optional[Dict[str, Any]] = None):
        """Add an item to a collection."""
        collection = self._get_collection(collection_name)
        embedding = await self.embedding_manager.embed_text(text)
        collection.add(
            ids=[id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata] if metadata else None
        )

    async def search(self, collection_name: str, query: str, n_results: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Search a collection."""
        collection = self._get_collection(collection_name)
        query_embedding = await self.embedding_manager.embed_text(query)
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filters
        )
        
        formatted = []
        if results and results.get("ids") and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                formatted.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i] if results.get("documents") else "",
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "distance": results["distances"][0][i] if results.get("distances") else 0.0,
                })
        return formatted

    def update(self, collection_name: str, id: str, text: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, embedding: Optional[List[float]] = None):
        """Update an item in a collection."""
        collection = self._get_collection(collection_name)
        update_kwargs = {"ids": [id]}
        if text is not None: update_kwargs["documents"] = [text]
        if metadata is not None: update_kwargs["metadatas"] = [metadata]
        if embedding is not None: update_kwargs["embeddings"] = [embedding]
        collection.update(**update_kwargs)

    def delete(self, collection_name: str, id: str):
        """Delete an item from a collection."""
        collection = self._get_collection(collection_name)
        collection.delete(ids=[id])

    def get(self, collection_name: str, id: str) -> Optional[Dict[str, Any]]:
        """Get an item from a collection by ID."""
        collection = self._get_collection(collection_name)
        result = collection.get(ids=[id])
        if result and result["ids"]:
            return {
                "id": result["ids"][0],
                "document": result["documents"][0] if result.get("documents") else "",
                "metadata": result["metadatas"][0] if result.get("metadatas") else {},
            }
        return None

    def _get_collection(self, name: str):
        if name not in self.collections:
            raise ValueError(f"Collection {name} not found")
        return self.collections[name]
