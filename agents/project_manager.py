from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
from .base import BaseAgent, AgentContext, AgentResult, AgentStatus, AuthorityLevel, SystemEvent

class Project(BaseModel):
    name: str
    status: str
    last_activity: datetime
    repo_url: Optional[str]
    resume_value: int

class ProjectManagerAgent(BaseAgent):
    name = "project_manager"
    description = "Tracks projects, github activity, and detects stale work."
    authority_level = AuthorityLevel(can_write=True, requires_approval=False)
    
    def __init__(self):
        self._is_active = False
        self.projects = []
        
    async def initialize(self) -> None:
        self._is_active = True
        
    async def process(self, context: AgentContext) -> AgentResult:
        stale_projects = []
        now = datetime.now()
        for p in self.projects:
            if (now - p.last_activity) > timedelta(days=4) and p.status != "COMPLETED":
                stale_projects.append(p.name)
                
        recs = [f"Project {p} has been inactive for >4 days. Next action?" for p in stale_projects]
        return AgentResult(recommendations=recs, data={"stale_projects": stale_projects})

    async def on_event(self, event: SystemEvent) -> Optional[AgentResult]:
        if event.event_type == "github_commit":
            repo = event.payload.get("repo")
            for p in self.projects:
                if p.repo_url and repo in p.repo_url:
                    p.last_activity = datetime.now()
            return AgentResult(data={"updated_repo": repo})
        return None
        
    async def get_status(self) -> AgentStatus:
        return AgentStatus(name=self.name, is_active=self._is_active)
        
    async def shutdown(self) -> None:
        self._is_active = False
