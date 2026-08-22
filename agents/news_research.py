from datetime import datetime
from typing import Optional
from .base import BaseAgent, AgentContext, AgentResult, AgentStatus, AuthorityLevel, SystemEvent, LLMAgentMixin

class NewsResearchAgent(BaseAgent, LLMAgentMixin):
    name = "news_research"
    description = "Monitors AI/GPU news and summarizes key items without flooding."
    authority_level = AuthorityLevel(can_write=True, requires_approval=False)
    
    def __init__(self):
        self._is_active = False
        self.daily_items = 0
        self.last_reset = datetime.now()
        
    async def initialize(self) -> None:
        self._is_active = True
        
    async def process(self, context: AgentContext) -> AgentResult:
        # Check reset
        if (datetime.now() - self.last_reset).days >= 1:
            self.daily_items = 0
            self.last_reset = datetime.now()
        return AgentResult()

    async def on_event(self, event: SystemEvent) -> Optional[AgentResult]:
        if event.event_type == "rss_item":
            if self.daily_items >= 5:
                return None # Don't flood
                
            content = event.payload.get("title", "").lower()
            keywords = ["ai", "ml", "gpu", "cuda", "nvidia", "model release"]
            if any(k in content for k in keywords):
                self.daily_items += 1
                return AgentResult(
                    data={"article": event.payload},
                    notifications=[f"Relevant News: {event.payload.get('title')}"]
                )
        return None
        
    async def get_status(self) -> AgentStatus:
        return AgentStatus(name=self.name, is_active=self._is_active)
        
    async def shutdown(self) -> None:
        self._is_active = False
