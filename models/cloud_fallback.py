import logging
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
import re

logger = logging.getLogger(__name__)

class CloudFallback(ABC):
    """Abstract base class for cloud model fallbacks."""
    
    @abstractmethod
    async def generate(self, task_type: str, prompt: str, **kwargs) -> Any:
        pass
        
    def filter_sensitive_data(self, text: str) -> str:
        """Strip potentially sensitive data before sending to cloud."""
        # Simple regex for things like emails, passwords, API keys.
        # This is a very basic implementation.
        text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[EMAIL REDACTED]', text)
        text = re.sub(r'(?i)(password|secret|key|token)[\s=:]+[\w\-]+', r'\1 [REDACTED]', text)
        return text

class GeminiFallback(CloudFallback):
    """Gemini API fallback."""
    def __init__(self, api_key: str):
        self.api_key = api_key
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.genai = genai
            self.model = genai.GenerativeModel('gemini-1.5-pro')
            self.enabled = True
        except ImportError:
            logger.error("google-generativeai not installed. Gemini fallback disabled.")
            self.enabled = False

    async def generate(self, task_type: str, prompt: str, **kwargs) -> Any:
        if not self.enabled:
            raise RuntimeError("Gemini fallback not available")
        from .router import ModelResponse
        
        safe_prompt = self.filter_sensitive_data(prompt)
        # We use sync generate_content here, in a real async setting we'd run in executor
        # or use the async client if available in the SDK
        response = self.model.generate_content(safe_prompt)
        
        return ModelResponse(
            text=response.text,
            model_used="gemini-1.5-pro",
            tokens_used=0,
            latency_ms=0.0
        )
