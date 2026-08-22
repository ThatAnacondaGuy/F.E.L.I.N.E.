import json
from datetime import datetime
from typing import Optional
from .base import BaseAgent, AgentContext, AgentResult, AgentStatus, AuthorityLevel, SystemEvent, LLMAgentMixin

class TaskExtractionAgent(BaseAgent, LLMAgentMixin):
    name = "task_extraction"
    description = "Extracts structured tasks from unstructured text."
    authority_level = AuthorityLevel(can_write=True, requires_approval=True)
    
    def __init__(self):
        self._is_active = False
        
    async def initialize(self) -> None:
        self._is_active = True
        
    async def process(self, context: AgentContext) -> AgentResult:
        text = context.user_request or ""
        return await self._extract_from_text(context, text, "manual_input")
        
    async def on_event(self, event: SystemEvent) -> Optional[AgentResult]:
        if event.event_type == "item_ingested":
            content = event.payload.get("content", "")
            source = event.payload.get("source", "unknown")
            return await self._extract_from_text(None, content, source)  # context missing in event currently
        return None
        
    async def _extract_from_text(self, context: Any, text: str, source: str) -> AgentResult:
        prompt = f"Extract tasks from this text: {text}. Return JSON with title, description, deadline, priority, category."
        # Fake LLM call for now
        # response = await self.query_llm(context.model_router, prompt)
        extracted = {
            "title": "Extracted Task",
            "description": text[:50],
            "deadline": datetime.now().isoformat(),
            "priority": "high",
            "category": "academic",
            "provenance": source,
            "status": "DRAFT"
        }
        return AgentResult(data={"extracted_tasks": [extracted]}, confidence=0.85)

    async def get_status(self) -> AgentStatus:
        return AgentStatus(name=self.name, is_active=self._is_active)
        
    async def shutdown(self) -> None:
        self._is_active = False
