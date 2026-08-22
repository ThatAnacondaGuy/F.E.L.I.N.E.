from datetime import datetime
from typing import Optional
from .base import BaseConnector, IngestedItem, ConnectorHealth

class GmailConnector(BaseConnector):
    name = "gmail"
    
    def __init__(self):
        self.is_authenticated = False
        self.last_sync = None
        self.history_id = None
        self.credentials = None
        
    async def authenticate(self) -> bool:
        # Mocking google-auth-oauthlib InstalledAppFlow
        self.is_authenticated = True
        return True
        
    async def sync(self, since: Optional[datetime] = None) -> list[IngestedItem]:
        if not self.is_authenticated:
            await self.authenticate()
            
        # Mock fetching emails with gmail.readonly
        items = []
        # Pagination & rate limit handling would go here
        
        item = IngestedItem(
            source=self.name,
            source_id="msg_123",
            content="Important AI Conference details inside.",
            metadata={"subject": "AI Conf", "from": "no-reply@aiconf.org", "labels": ["INBOX"]},
            timestamp=datetime.now(),
            raw_data={"id": "msg_123"}
        )
        items.append(item)
        self.last_sync = datetime.now()
        return items
        
    async def is_available(self) -> bool:
        return self.is_authenticated
        
    async def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(
            status="ok" if self.is_authenticated else "unauthenticated",
            last_sync=self.last_sync,
            latency_ms=150.0
        )
