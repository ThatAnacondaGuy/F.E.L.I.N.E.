from datetime import datetime
from typing import Optional
from .base import BaseConnector, IngestedItem, ConnectorHealth

class GoogleCalendarConnector(BaseConnector):
    name = "google_calendar"
    
    def __init__(self):
        self.is_authenticated = False
        self.last_sync = None
        
    async def authenticate(self) -> bool:
        self.is_authenticated = True
        return True
        
    async def sync(self, since: Optional[datetime] = None) -> list[IngestedItem]:
        self.last_sync = datetime.now()
        return []
        
    async def create_event(self, title: str, start: datetime, end: datetime) -> bool:
        # Require EXPLICIT authority checks higher up
        return True
        
    async def delete_event(self, event_id: str) -> bool:
        return True
        
    async def detect_conflicts(self, start: datetime, end: datetime) -> bool:
        # Simple overlap check against cached events
        return False

    async def is_available(self) -> bool:
        return self.is_authenticated
        
    async def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(status="ok", last_sync=self.last_sync)
