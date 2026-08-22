import os
from datetime import datetime, timedelta
from typing import Optional
from .base import BaseConnector, IngestedItem, ConnectorHealth

class GithubConnector(BaseConnector):
    name = "github"
    
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        self.is_authenticated = bool(self.token)
        self.last_sync = None
        
    async def authenticate(self) -> bool:
        self.is_authenticated = bool(self.token)
        return self.is_authenticated
        
    async def sync(self, since: Optional[datetime] = None) -> list[IngestedItem]:
        if not self.is_authenticated:
            return []
            
        self.last_sync = datetime.now()
        # Mock fetching commits/PRs
        item = IngestedItem(
            source=self.name,
            source_id="commit_789",
            content="Added GPU optimization to training script",
            metadata={"repo": "Meow-OS", "type": "commit"},
            timestamp=datetime.now()
        )
        return [item]
        
    async def is_available(self) -> bool:
        return self.is_authenticated
        
    async def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(status="ok" if self.is_authenticated else "missing_token", last_sync=self.last_sync)
