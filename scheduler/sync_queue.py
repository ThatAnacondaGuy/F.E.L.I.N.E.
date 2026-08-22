import sqlite3
import uuid
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class SyncQueue:
    """Offline sync queue."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sync_queue (
                    id TEXT PRIMARY KEY,
                    action TEXT,
                    payload TEXT,
                    status TEXT,
                    retries INTEGER DEFAULT 0,
                    created_at TEXT,
                    last_attempt TEXT
                )
            ''')
            conn.commit()

    def enqueue(self, action: str, payload: Dict[str, Any]):
        item_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO sync_queue (id, action, payload, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (item_id, action, json.dumps(payload), "pending", now)
            )
        logger.info(f"Enqueued action: {action} [{item_id}]")

    def is_online(self) -> bool:
        """Check if we have internet connection."""
        import socket
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=2)
            return True
        except OSError:
            return False

    async def process_queue(self, action_handlers: Dict[str, Any]):
        if not self.is_online():
            logger.info("Offline. Skipping sync queue processing.")
            return

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM sync_queue WHERE status = 'pending' OR status = 'failed' ORDER BY created_at ASC LIMIT 50")
            items = cursor.fetchall()

        for item in items:
            item_id = item['id']
            action = item['action']
            payload = json.loads(item['payload'])
            retries = item['retries']
            
            if retries > 5:
                self._update_status(item_id, "dead_letter")
                continue
                
            try:
                if action in action_handlers:
                    await action_handlers[action](payload)
                    self._update_status(item_id, "completed")
                else:
                    logger.warning(f"No handler for action: {action}")
                    self._update_status(item_id, "failed", retries + 1)
            except Exception as e:
                logger.error(f"Failed to process {item_id}: {e}")
                self._update_status(item_id, "failed", retries + 1)

    def _update_status(self, item_id: str, status: str, retries: Optional[int] = None):
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            if retries is not None:
                conn.execute(
                    "UPDATE sync_queue SET status = ?, retries = ?, last_attempt = ? WHERE id = ?",
                    (status, retries, now, item_id)
                )
            else:
                conn.execute(
                    "UPDATE sync_queue SET status = ?, last_attempt = ? WHERE id = ?",
                    (status, now, item_id)
                )
