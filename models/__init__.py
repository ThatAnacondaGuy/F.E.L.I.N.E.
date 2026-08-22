"""
Models package for Meow OS.
"""

from .ollama_client import OllamaClient
from .router import ModelRouter, ModelTask, ModelResponse
from .embeddings import EmbeddingManager
from .cloud_fallback import CloudFallback

__all__ = [
    "OllamaClient",
    "ModelRouter",
    "ModelTask",
    "ModelResponse",
    "EmbeddingManager",
    "CloudFallback",
]
