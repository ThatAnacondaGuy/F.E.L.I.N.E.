from datetime import datetime
from typing import Optional
from .base import BaseConnector, IngestedItem, ConnectorHealth

class RssReaderConnector(BaseConnector):
    name = "rss_reader"
    
    def __init__(self):
        self.is_authenticated = True # No auth needed
        self.last_sync = None
        self.seen_guids = set()
        self.feeds = ["https://news.developer.nvidia.com/feed/"]
        
    async def authenticate(self) -> bool:
        return True
        
    async def sync(self, since: Optional[datetime] = None) -> list[IngestedItem]:
        self.last_sync = datetime.now()
        items = []
        # Mock feedparser logic
        for feed in self.feeds:
            # fetch feed...
            guid = "mock_guid_1"
            if guid not in self.seen_guids:
                self.seen_guids.add(guid)
                items.append(IngestedItem(
                    source=self.name,
                    source_id=guid,
                    content="NVIDIA releases new CUDA toolkit features.",
                    metadata={"url": feed, "title": "New CUDA Toolkit"},
                    timestamp=datetime.now()
                ))
        return items
        
    async def is_available(self) -> bool:
        return True
        
    async def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(status="ok", last_sync=self.last_sync)
