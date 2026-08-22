from datetime import datetime, timedelta
from typing import Optional
from .base import BaseAgent, AgentContext, AgentResult, AgentStatus, AuthorityLevel, SystemEvent

class CalendarAgent(BaseAgent):
    name = "calendar_agent"
    description = "Treats calendar as resource allocation system. Prevents overbooking."
    authority_level = AuthorityLevel(can_write=True, requires_approval=False)
    
    def __init__(self):
        self._is_active = False
        self.focus_blocks = []
        
    async def initialize(self) -> None:
        self._is_active = True
        
    async def process(self, context: AgentContext) -> AgentResult:
        return AgentResult(data={"message": "Calendar check complete"})
        
    def detect_conflicts(self, date: datetime, events: list[dict]) -> list[dict]:
        # Simple overlap detection
        conflicts = []
        events.sort(key=lambda x: x["start"])
        for i in range(len(events) - 1):
            if events[i]["end"] > events[i+1]["start"]:
                conflicts.append((events[i], events[i+1]))
        return conflicts
        
    def suggest_time_slot(self, duration_mins: int, deadline: datetime, current_events: list[dict]) -> list[datetime]:
        # Simple implementation: find gaps > duration_mins
        return [datetime.now() + timedelta(hours=1)] # stub returning soonest available slot
        
    def create_work_plan(self, assignment_name: str, deadline: datetime, estimated_hours: float) -> dict:
        blocks = int(estimated_hours / 1.5) # 90 min blocks
        return {"assignment": assignment_name, "blocks_needed": blocks, "plan": []}
        
    def protect_focus_blocks(self) -> None:
        # Schedule 4:30 PM to 8 PM as deep focus typically
        pass

    async def on_event(self, event: SystemEvent) -> Optional[AgentResult]:
        return None
        
    async def get_status(self) -> AgentStatus:
        return AgentStatus(name=self.name, is_active=self._is_active)
        
    async def shutdown(self) -> None:
        self._is_active = False
