from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from .base import BaseAgent, AgentContext, AgentResult, AgentStatus, AuthorityLevel, SystemEvent

class Course(BaseModel):
    id: str
    name: str
    code: str
    priority: str

class AcademicAgent(BaseAgent):
    name = "academic"
    description = "Tracks courses, assignments, and exams for TE Comp Eng."
    authority_level = AuthorityLevel(can_write=True, requires_approval=False)
    
    def __init__(self):
        self._is_active = False
        self.courses = [
            Course(id="c1", name="Artificial Intelligence", code="PCC301COM", priority="HIGHEST"),
            Course(id="c2", name="Computer Networks", code="PCC302COM", priority="Standard"),
            Course(id="c3", name="Theory of Computation", code="PCC303COM", priority="Standard"),
            Course(id="c4", name="Robotics and Automation", code="MDM331COM", priority="High"),
            Course(id="c5", name="Cloud Computing", code="PEC321BCOM", priority="High"),
            Course(id="c6", name="IPR", code="Open Elective", priority="Standard"),
            Course(id="c7", name="Technical Seminar", code="ELC342COM", priority="Research Milestones")
        ]
        self.assignments = []
        
    async def initialize(self) -> None:
        self._is_active = True
        
    async def process(self, context: AgentContext) -> AgentResult:
        return AgentResult(data={"courses": [c.model_dump() for c in self.courses]})

    async def on_event(self, event: SystemEvent) -> Optional[AgentResult]:
        if event.event_type == "new_classroom_assignment":
            # Priority boost for AI
            course_id = event.payload.get("course_id")
            priority = "HIGHEST" if course_id == "c1" else "Normal"
            self.assignments.append(event.payload)
            return AgentResult(
                actions=[{"type": "create_work_plan", "assignment": event.payload, "priority": priority}]
            )
        return None
        
    async def get_status(self) -> AgentStatus:
        return AgentStatus(name=self.name, is_active=self._is_active, stats={"assignments_tracked": len(self.assignments)})
        
    async def shutdown(self) -> None:
        self._is_active = False
