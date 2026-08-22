from abc import ABC, abstractmethod
from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class AuthorityLevel(BaseModel):
    can_read: bool = True
    can_write: bool = False
    can_delete: bool = False
    requires_approval: bool = True

class AgentContext(BaseModel):
    db: Any
    config: Any
    event_bus: Any
    model_router: Any
    memory: Any
    user_request: Optional[str] = None

class AgentResult(BaseModel):
    actions: list[dict] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    notifications: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)

class AgentStatus(BaseModel):
    name: str
    is_active: bool
    last_run: Optional[datetime] = None
    stats: dict[str, Any] = Field(default_factory=dict)

class SystemEvent(BaseModel):
    event_type: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)

class BaseAgent(ABC):
    name: str
    description: str
    authority_level: AuthorityLevel
    
    @abstractmethod
    async def initialize(self) -> None:
        pass
        
    @abstractmethod
    async def process(self, context: AgentContext) -> AgentResult:
        pass
        
    @abstractmethod
    async def on_event(self, event: SystemEvent) -> Optional[AgentResult]:
        pass
        
    @abstractmethod
    async def get_status(self) -> AgentStatus:
        pass
        
    @abstractmethod
    async def shutdown(self) -> None:
        pass

class LLMAgentMixin:
    async def query_llm(self, model_router: Any, prompt: str, system_prompt: Optional[str] = None) -> str:
        # TODO(Phase 2): Implement exact router call
        return "LLM Response Placeholder"

class ScheduledAgentMixin:
    schedule_cron: str
    async def run_scheduled(self, context: AgentContext) -> AgentResult:
        return await self.process(context)
