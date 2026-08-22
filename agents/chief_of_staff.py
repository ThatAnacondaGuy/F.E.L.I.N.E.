from datetime import datetime
from typing import Optional
from .base import BaseAgent, AgentContext, AgentResult, AgentStatus, AuthorityLevel, SystemEvent, LLMAgentMixin

class ChiefOfStaffAgent(BaseAgent, LLMAgentMixin):
    name = "chief_of_staff"
    description = "The brain of Meow OS. Synthesizes data and manages Aniket's priorities."
    authority_level = AuthorityLevel(can_read=True, can_write=True, can_delete=False, requires_approval=False)
    
    def __init__(self):
        self._is_active = False
        self._last_run = None
    
    async def initialize(self) -> None:
        self._is_active = True
        
    async def process(self, context: AgentContext) -> AgentResult:
        self._last_run = datetime.now()
        req = context.user_request or ""
        if "morning" in req.lower():
            return await self.generate_morning_briefing(context)
        elif "evening" in req.lower():
            return await self.generate_evening_review(context)
        elif "weekly" in req.lower():
            return await self.generate_weekly_review(context)
        
        # Default fallback synthesis
        response = await self.query_llm(context.model_router, f"Synthesize priorities for request: {req}")
        return AgentResult(recommendations=[response], data={"type": "synthesis"})
        
    async def generate_morning_briefing(self, context: AgentContext) -> AgentResult:
        # Pull from other agents in a real impl
        briefing = "Good morning Aniket.\nSchedule: Classes 9:15-16:30.\nPriority: AI Coursework & NVIDIA prep."
        return AgentResult(data={"briefing": briefing}, notifications=["Morning briefing ready."])
        
    async def generate_evening_review(self, context: AgentContext) -> AgentResult:
        review = "Evening Review.\nCompleted: 3 tasks. Missed: 1.\nTomorrow: Focus on Cloud Computing."
        return AgentResult(data={"review": review})
        
    async def generate_weekly_review(self, context: AgentContext) -> AgentResult:
        review = "Weekly Review.\nAcademic: On track.\nCareer: +2 hrs NVIDIA prep. Needs more CUDA."
        return AgentResult(data={"review": review})

    async def on_event(self, event: SystemEvent) -> Optional[AgentResult]:
        if event.event_type == "high_priority_conflict":
            # Conflict resolution logic
            return AgentResult(recommendations=["Reschedule lower priority task"])
        return None
        
    async def get_status(self) -> AgentStatus:
        return AgentStatus(name=self.name, is_active=self._is_active, last_run=self._last_run)
        
    async def shutdown(self) -> None:
        self._is_active = False
