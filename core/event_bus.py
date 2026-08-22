"""Internal pub/sub event system."""

import asyncio
import logging
from enum import Enum
from typing import Callable, Dict, List, Any, Awaitable
from datetime import datetime
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class EventType(str, Enum):
    TASK_CREATED = "TASK_CREATED"
    DEADLINE_APPROACHING = "DEADLINE_APPROACHING"
    EMAIL_RECEIVED = "EMAIL_RECEIVED"
    CALENDAR_CONFLICT = "CALENDAR_CONFLICT"
    SYSTEM_STARTUP = "SYSTEM_STARTUP"

class Event(BaseModel):
    type: EventType
    payload: Dict[str, Any]
    source: str
    timestamp: datetime = Field(default_factory=datetime.now)

EventHandler = Callable[[Event], Awaitable[None]]

class EventBus:
    """Async event bus for pub/sub communication."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
            cls._instance._subscribers = {}
        return cls._instance
        
    def subscribe(self, event_type: EventType | str, handler: EventHandler):
        """Subscribe to an event type. Use '*' for wildcard."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        
    def unsubscribe(self, event_type: EventType | str, handler: EventHandler):
        """Unsubscribe from an event type."""
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass
                
    async def publish(self, event: Event):
        """Publish an event to all subscribers."""
        handlers = self._subscribers.get(event.type, []) + self._subscribers.get("*", [])
        
        async def run_handler(h: EventHandler):
            try:
                await h(event)
            except Exception as e:
                logger.error(f"Error in event handler {h.__name__} for event {event.type}: {e}")
                
        # Run all handlers concurrently, isolating failures
        if handlers:
            await asyncio.gather(*(run_handler(h) for h in handlers))
