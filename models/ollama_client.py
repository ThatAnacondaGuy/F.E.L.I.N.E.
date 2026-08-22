import httpx
import logging
import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class OllamaClient:
    """Async client for interacting with the local Ollama API."""

    def __init__(self, base_url: str = "http://localhost:11434", timeout: int = 120):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        retries = 3
        backoff = 1
        for attempt in range(retries):
            try:
                response = await self.client.request(method, endpoint, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.ConnectError:
                logger.error(f"Failed to connect to Ollama at {self.base_url}")
                if attempt == retries - 1:
                    raise ConnectionError("Ollama is not running or unreachable")
            except Exception as e:
                logger.error(f"Ollama request error: {e}")
                if attempt == retries - 1:
                    raise
            await asyncio.sleep(backoff)
            backoff *= 2
        return {}

    async def generate(
        self, model: str, prompt: str, stream: bool = False, **kwargs
    ) -> Dict[str, Any] | AsyncGenerator[str, None]:
        """Generate a response using Ollama."""
        payload = {"model": model, "prompt": prompt, "stream": stream, **kwargs}
        if stream:
            return self._stream_generate(payload)
        else:
            return await self._request("POST", "/api/generate", json=payload)

    async def _stream_generate(self, payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        async with self.client.stream("POST", "/api/generate", json=payload) as response:
            async for chunk in response.aiter_text():
                yield chunk

    async def chat(
        self, model: str, messages: List[Dict[str, str]], stream: bool = False, **kwargs
    ) -> Dict[str, Any] | AsyncGenerator[str, None]:
        """Send a chat completion request to Ollama."""
        payload = {"model": model, "messages": messages, "stream": stream, **kwargs}
        if stream:
            return self._stream_chat(payload)
        else:
            return await self._request("POST", "/api/chat", json=payload)

    async def _stream_chat(self, payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        async with self.client.stream("POST", "/api/chat", json=payload) as response:
            async for chunk in response.aiter_text():
                yield chunk

    async def embed(self, model: str, input_text: str | List[str]) -> Dict[str, Any]:
        """Generate embeddings for the given input."""
        payload = {"model": model, "input": input_text}
        return await self._request("POST", "/api/embed", json=payload)

    async def list_models(self) -> List[Dict[str, Any]]:
        """List locally available models."""
        response = await self._request("GET", "/api/tags")
        return response.get("models", [])

    async def is_healthy(self) -> bool:
        """Check if Ollama is running and responsive."""
        try:
            response = await self.client.get("/")
            return response.status_code == 200
        except httpx.RequestError:
            return False

    async def close(self):
        await self.client.aclose()
