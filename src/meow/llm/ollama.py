"""Minimal Ollama client with structured (JSON-schema constrained) output."""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx


class LLMError(RuntimeError):
    pass


class JSONChat(Protocol):
    """What the rest of Meow needs from a model. Tests supply a fake."""

    def chat_json(self, model: str, system: str, user: str, schema: dict[str, Any]) -> Any: ...


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 180,
        transport: httpx.BaseTransport | None = None,
        think: bool | None = None,
    ) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        self.think = think

    def close(self) -> None:
        self._http.close()

    def version(self) -> str:
        return str(self._get("/api/version").get("version", "unknown"))

    def installed_models(self) -> list[str]:
        return [m["name"] for m in self._get("/api/tags").get("models", [])]

    def chat_json(self, model: str, system: str, user: str, schema: dict[str, Any]) -> Any:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0},
        }
        if self.think is not None:
            body["think"] = self.think
        try:
            resp = self._http.post("/api/chat", json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama unreachable ({exc}). Is `ollama serve` running?") from exc
        if resp.status_code == 404:
            raise LLMError(f"Model {model!r} is not installed. Run: ollama pull {model}")
        if resp.is_error:
            raise LLMError(f"Ollama error {resp.status_code}: {resp.text[:300]}")
        content = resp.json().get("message", {}).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model returned invalid JSON: {content[:200]!r}") from exc

    def _get(self, path: str) -> dict[str, Any]:
        try:
            resp = self._http.get(path)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama unreachable ({exc}). Is `ollama serve` running?") from exc
        data: dict[str, Any] = resp.json()
        return data
