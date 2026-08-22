from datetime import datetime
from typing import Optional
from .base import BaseAgent, AgentContext, AgentResult, AgentStatus, AuthorityLevel, SystemEvent

class CareerAgent(BaseAgent):
    name = "career"
    description = "Tracks NVIDIA career goal hierarchy and skills."
    authority_level = AuthorityLevel(can_write=True, requires_approval=False)
    
    def __init__(self):
        self._is_active = False
        self.skills = {
            "C++": 0.6, "Python": 0.8, "Linux": 0.5, "DSA": 0.7, 
            "Systems": 0.4, "CUDA": 0.2, "GPU Architecture": 0.2,
            "Parallel Programming": 0.3, "ML": 0.6, "DL": 0.5, 
            "GenAI": 0.4, "Research": 0.3
        }
        
    async def initialize(self) -> None:
        self._is_active = True
        
    async def process(self, context: AgentContext) -> AgentResult:
        # Gap analysis
        weak_skills = [k for k, v in self.skills.items() if v < 0.4]
        return AgentResult(
            data={"weak_skills": weak_skills},
            recommendations=[f"Focus on improving {s}" for s in weak_skills[:2]]
        )

    async def on_event(self, event: SystemEvent) -> Optional[AgentResult]:
        if event.event_type == "project_completed":
            # Adjust skills based on project tags
            return AgentResult(notifications=["Skill levels updated from project completion."])
        return None
        
    async def get_status(self) -> AgentStatus:
        return AgentStatus(name=self.name, is_active=self._is_active)
        
    async def shutdown(self) -> None:
        self._is_active = False
