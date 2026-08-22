import sqlite3
import json
import uuid
import datetime
import logging
from typing import List, Optional, Any, Dict
from enum import Enum
from pydantic import BaseModel, Field

from .vector_store import VectorStore

logger = logging.getLogger(__name__)

class MemoryCategory(str, Enum):
    FACTS = "facts"
    PREFERENCES = "preferences"
    GOALS = "goals"
    HABITS = "habits"
    PROJECTS = "projects"
    TASK_HISTORY = "task_history"
    DECISIONS = "decisions"
    CONTEXT = "context"
    LEARNING_STATE = "learning_state"

class Memory(BaseModel):
    id: str
    category: MemoryCategory
    key: str
    value: str
    context: Optional[str] = None
    source: str
    confidence: float
    created_at: str
    updated_at: str
    sensitive: bool = False

class MemoryStore:
    """Personal memory CRUD with SQLite for structure and ChromaDB for semantic search."""
    
    def __init__(self, db_path: str, vector_store: VectorStore):
        self.db_path = db_path
        self.vector_store = vector_store
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    category TEXT,
                    key TEXT,
                    value TEXT,
                    context TEXT,
                    source TEXT,
                    confidence REAL,
                    created_at TEXT,
                    updated_at TEXT,
                    sensitive INTEGER
                )
            ''')
            conn.commit()

    async def remember(self, category: MemoryCategory, key: str, value: str, context: Optional[str] = None, source: str = "system", confidence: float = 1.0, sensitive: bool = False) -> Memory:
        mem_id = str(uuid.uuid4())
        now = datetime.datetime.now().isoformat()
        
        memory = Memory(
            id=mem_id, category=category, key=key, value=value,
            context=context, source=source, confidence=confidence,
            created_at=now, updated_at=now, sensitive=sensitive
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                '''INSERT INTO memories (id, category, key, value, context, source, confidence, created_at, updated_at, sensitive)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (mem_id, category.value, key, value, context, source, confidence, now, now, int(sensitive))
            )
        
        doc_text = f"{category.value}: {key} - {value}. Context: {context}"
        metadata = {"category": category.value, "key": key, "confidence": confidence, "sensitive": sensitive}
        await self.vector_store.add("memories", mem_id, doc_text, metadata)
        
        return memory

    def recall(self, category: MemoryCategory, key: str) -> Optional[Memory]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM memories WHERE category = ? AND key = ? ORDER BY updated_at DESC LIMIT 1", (category.value, key))
            row = cursor.fetchone()
            if row:
                return Memory(**dict(row))
        return None

    async def search_memory(self, query: str, category: Optional[MemoryCategory] = None) -> List[Memory]:
        filters = {"category": category.value} if category else None
        results = await self.vector_store.search("memories", query, n_results=10, filters=filters)
        
        memories = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for res in results:
                cursor = conn.execute("SELECT * FROM memories WHERE id = ?", (res["id"],))
                row = cursor.fetchone()
                if row:
                    memories.append(Memory(**dict(row)))
        return memories

    def forget(self, memory_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.vector_store.delete("memories", memory_id)

    def update_memory(self, memory_id: str, value: str, confidence: Optional[float] = None):
        now = datetime.datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            if confidence is not None:
                conn.execute("UPDATE memories SET value = ?, confidence = ?, updated_at = ? WHERE id = ?", (value, confidence, now, memory_id))
            else:
                conn.execute("UPDATE memories SET value = ?, updated_at = ? WHERE id = ?", (value, now, memory_id))
        
        # In a full implementation, we should also update the vector store here

    def list_memories(self, category: Optional[MemoryCategory] = None, limit: int = 50) -> List[Memory]:
        query = "SELECT * FROM memories"
        params = []
        if category:
            query += " WHERE category = ?"
            params.append(category.value)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        
        memories = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                memories.append(Memory(**dict(row)))
        return memories

    def export_memories(self) -> str:
        memories = self.list_memories(limit=10000)
        return json.dumps([m.model_dump() for m in memories], indent=2)

    def apply_policies(self):
        """Auto-expire low-confidence memories after 30 days."""
        thirty_days_ago = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id FROM memories WHERE confidence < 0.5 AND updated_at < ?", (thirty_days_ago,))
            rows = cursor.fetchall()
            for row in rows:
                self.forget(row[0])
