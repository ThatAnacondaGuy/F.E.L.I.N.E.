from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel
from .base import BaseAgent, AgentContext, AgentResult, AgentStatus, AuthorityLevel, SystemEvent

class IngestedItem(BaseModel):
    source: str
    source_id: str
    content: str
    metadata: dict[str, Any]
    timestamp: datetime
    raw_data: Any

class IngestionAgent(BaseAgent):
    name = "ingestion"
    description = "Orchestrates connectors to pull data and routes via event bus."
    authority_level = AuthorityLevel(can_write=True, requires_approval=False)
    
    def __init__(self, connectors: list[Any]):
        self.connectors = connectors
        self.sync_times = {}
        self._is_active = False
        
    async def initialize(self) -> None:
        self._is_active = True
        
    async def process(self, context: AgentContext) -> AgentResult:
        all_items = []
        errors = []
        
        for connector in self.connectors:
            try:
                if await connector.is_available():
                    since = self.sync_times.get(connector.name)
                    items = await connector.sync(since)
                    all_items.extend(items)
                    self.sync_times[connector.name] = datetime.now()
                    
                    for item in items:
                        # Route via event bus
                        await context.event_bus.publish("item_ingested", item.model_dump())
            except Exception as e:
                errors.append(f"{connector.name} failed: {str(e)}")
                
        return AgentResult(
            data={"items_synced": len(all_items), "errors": errors},
            notifications=[f"Ingestion complete with {len(errors)} errors."] if errors else []
        )
        
    async def on_event(self, event: SystemEvent) -> Optional[AgentResult]:
        if event.event_type == "force_sync":
            # Ignore context here or mock it
            pass
        return None
        
    async def get_status(self) -> AgentStatus:
        return AgentStatus(name=self.name, is_active=self._is_active, stats={"sync_times": self.sync_times})
        
    async def shutdown(self) -> None:
        self._is_active = False
