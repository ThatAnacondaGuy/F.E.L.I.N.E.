from abc import ABC, abstractmethod
from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class IngestedItem(BaseModel):
    source: str
    source_id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    raw_data: Any = None

class ConnectorHealth(BaseModel):
    status: str
    last_sync: Optional[datetime] = None
    error: Optional[str] = None
    latency_ms: float = 0.0

class BaseConnector(ABC):
    name: str
    is_authenticated: bool = False
    last_sync: Optional[datetime] = None
    
    @abstractmethod
    async def authenticate(self) -> bool:
        pass
        
    @abstractmethod
    async def sync(self, since: Optional[datetime] = None) -> list[IngestedItem]:
        pass
        
    @abstractmethod
    async def is_available(self) -> bool:
        pass
        
    @abstractmethod
    async def health_check(self) -> ConnectorHealth:
        pass
