"""Audit trail system."""

import uuid
from datetime import datetime
from typing import Optional
from database.connection import get_db
from database.models import AuditEntryModel

class AuditLogger:
    """Logs automated actions to the audit trail."""
    
    @staticmethod
    async def log_action(
        agent: str,
        trigger: str,
        action: str,
        reason: str,
        source: Optional[str] = None,
        result: Optional[str] = None,
        confidence: Optional[float] = None,
        user_approved: Optional[bool] = None
    ) -> str:
        """Log an action and return its ID."""
        entry_id = str(uuid.uuid4())
        timestamp = datetime.now()
        
        entry = AuditEntryModel(
            id=entry_id,
            timestamp=timestamp,
            agent=agent,
            trigger=trigger,
            action=action,
            reason=reason,
            source=source,
            result=result,
            confidence=confidence,
            user_approved=user_approved
        )
        
        # Async generator pattern for get_db
        db_gen = get_db()
        conn = await anext(db_gen)
        try:
            await conn.execute("""
                INSERT INTO audit_entries (
                    id, timestamp, agent, trigger, action, reason, 
                    source, result, confidence, user_approved
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id, entry.timestamp, entry.agent, entry.trigger, entry.action,
                entry.reason, entry.source, entry.result, entry.confidence, entry.user_approved
            ))
            await conn.commit()
            return entry_id
        finally:
            try:
                await anext(db_gen)
            except StopAsyncIteration:
                pass
