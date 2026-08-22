"""Database connection manager."""

import aiosqlite
import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages SQLite database connections."""
    
    _instance = None
    _db_path = "meow_os.db"
    
    def __new__(cls, db_path: str | None = None):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            if db_path:
                cls._instance._db_path = db_path
        return cls._instance
    
    @classmethod
    def set_db_path(cls, path: str):
        """Set the database path."""
        cls._db_path = path
        
    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Get a database connection with WAL mode and foreign keys enabled."""
        conn = await aiosqlite.connect(self._db_path)
        try:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = aiosqlite.Row
            yield conn
        finally:
            await conn.close()

async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """FastAPI dependency for database connection."""
    db_manager = DatabaseManager()
    async with db_manager.get_connection() as conn:
        yield conn

async def init_db(db_path: str):
    """Initialize database connection manager."""
    DatabaseManager.set_db_path(db_path)
    logger.info(f"Initialized database at {db_path}")
