from datetime import datetime
from typing import Optional
from .base import BaseAgent, AgentContext, AgentResult, AgentStatus, AuthorityLevel, SystemEvent

class LearningAgent(BaseAgent):
    name = "learning"
    description = "Maintains skill graph and structured learning paths."
    authority_level = AuthorityLevel(can_write=True, requires_approval=False)
    
    def __init__(self):
        self._is_active = False
        self.skill_graph = {
            "GPU Architecture": ["CUDA"],
            "CUDA": ["Memory Hierarchy", "Parallel Programming"],
            "Memory Hierarchy": ["Optimization"],
            "Optimization": ["Benchmarking"]
        }
        
    async def initialize(self) -> None:
        self._is_active = True
        
    async def process(self, context: AgentContext) -> AgentResult:
        # Determine next concept based on mock current level
        current_focus = "CUDA"
        next_concepts = self.skill_graph.get(current_focus, [])
        return AgentResult(
            data={"current_focus": current_focus, "next_concepts": next_concepts},
            recommendations=[f"Next in NVIDIA learning path: {c}" for c in next_concepts]
        )

    async def on_event(self, event: SystemEvent) -> Optional[AgentResult]:
        if event.event_type == "learning_session_completed":
            return AgentResult(notifications=["Learning time logged."])
        return None
        
    async def get_status(self) -> AgentStatus:
        return AgentStatus(name=self.name, is_active=self._is_active)
        
    async def shutdown(self) -> None:
        self._is_active = False
