from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from .base import BaseAgent, AgentContext, AgentResult, AgentStatus, AuthorityLevel, SystemEvent

class Opportunity(BaseModel):
    title: str
    source: str
    url: str
    deadline: Optional[datetime]
    score: float = 0.0

class OpportunityAgent(BaseAgent):
    name = "opportunity"
    description = "Discovers and scores opportunities for career advancement."
    authority_level = AuthorityLevel(can_write=True, requires_approval=True)
    
    def __init__(self):
        self._is_active = False
        self.seen_urls = set()
        
    async def initialize(self) -> None:
        self._is_active = True
        
    def _score_opportunity(self, item: dict) -> float:
        score = 50.0
        content = str(item.get("content", "")).lower()
        if "nvidia" in content: score += 20
        if "cuda" in content or "gpu" in content: score += 15
        if "hackathon" in content: score += 10
        return min(score, 100.0)

    async def process(self, context: AgentContext) -> AgentResult:
        return AgentResult()
        
    async def on_event(self, event: SystemEvent) -> Optional[AgentResult]:
        if event.event_type == "item_ingested":
            payload = event.payload
            url = payload.get("metadata", {}).get("url", "")
            if url in self.seen_urls:
                return None
            
            score = self._score_opportunity(payload)
            if score > 60:
                self.seen_urls.add(url)
                opp = Opportunity(title=payload.get("content", "")[:50], source=payload.get("source", "unknown"), url=url, deadline=None, score=score)
                return AgentResult(data={"opportunity": opp.model_dump()}, actions=[{"type": "prompt_user", "options": ["Register", "Save", "Ignore"]}])
        return None
        
    async def get_status(self) -> AgentStatus:
        return AgentStatus(name=self.name, is_active=self._is_active, stats={"seen": len(self.seen_urls)})
        
    async def shutdown(self) -> None:
        self._is_active = False
