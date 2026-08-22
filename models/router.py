import logging
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from .ollama_client import OllamaClient
from .cloud_fallback import CloudFallback
from core.config import get_config

logger = logging.getLogger(__name__)

class ModelTask(str, Enum):
    CLASSIFY = "classify"
    EXTRACT = "extract"
    PLAN = "plan"
    SUMMARIZE = "summarize"
    EMBED = "embed"
    REASON = "reason"
    CHAT = "chat"

class ModelResponse(BaseModel):
    text: str
    model_used: str
    tokens_used: int = 0
    latency_ms: float = 0.0

class ModelRouter:
    """Routes requests to the appropriate model based on task type."""
    
    def __init__(self, ollama_client: OllamaClient, cloud_fallback: Optional[CloudFallback] = None):
        self.client = ollama_client
        self.cloud_fallback = cloud_fallback
        self.config = get_config()
        self.model_map: Dict[ModelTask, str] = {
            ModelTask.CLASSIFY: self.config.get("models.classify", "llama3.2:1b"),
            ModelTask.EXTRACT: self.config.get("models.extract", "llama3.2:1b"),
            ModelTask.PLAN: self.config.get("models.plan", "llama3.1:8b"),
            ModelTask.SUMMARIZE: self.config.get("models.summarize", "llama3.1:8b"),
            ModelTask.EMBED: self.config.get("models.embed", "nomic-embed-text"),
            ModelTask.REASON: self.config.get("models.reason", "deepseek-r1:8b"),
            ModelTask.CHAT: self.config.get("models.chat", "llama3.1:8b"),
        }

    async def is_available(self) -> bool:
        """Check if routing targets are available."""
        return await self.client.is_healthy()

    async def route(self, task_type: ModelTask, prompt: str, **kwargs) -> ModelResponse:
        """Route a task to the appropriate model, using fallback if necessary."""
        local_model = self.model_map.get(task_type, "llama3.1:8b")
        
        try:
            # Try local model first
            response = await self.client.generate(model=local_model, prompt=prompt, stream=False, **kwargs)
            return ModelResponse(
                text=response.get("response", ""),
                model_used=local_model,
                tokens_used=response.get("eval_count", 0),
                latency_ms=response.get("total_duration", 0) / 1_000_000 # ns to ms
            )
        except Exception as e:
            logger.warning(f"Local model {local_model} failed for task {task_type}: {e}")
            if self.cloud_fallback:
                logger.info(f"Falling back to cloud model for task {task_type}")
                return await self.cloud_fallback.generate(task_type, prompt, **kwargs)
            raise e
