from datetime import datetime
from typing import Optional
from .base import BaseConnector, IngestedItem, ConnectorHealth

class MessageCaptureConnector(BaseConnector):
    name = "message_capture"
    
    def __init__(self):
        self.is_authenticated = True
        self.last_sync = None
        self.queue = []
        
    async def authenticate(self) -> bool:
        return True
        
    async def sync(self, since: Optional[datetime] = None) -> list[IngestedItem]:
        self.last_sync = datetime.now()
        items = []
        while self.queue:
            msg = self.queue.pop(0)
            items.append(IngestedItem(
                source=self.name,
                source_id=f"capture_{datetime.now().timestamp()}",
                content=msg,
                metadata={"format": "plain"},
                timestamp=datetime.now()
            ))
        return items
        
    async def receive_message(self, text: str) -> dict:
        self.queue.append(text)
        return {"status": "accepted", "message_length": len(text)}
        
    async def is_available(self) -> bool:
        return True
        
    async def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(status="ok", last_sync=self.last_sync)
