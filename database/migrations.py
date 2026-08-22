"""Database migrations system."""

import aiosqlite
import logging
import os

logger = logging.getLogger(__name__)

async def apply_migration(conn: aiosqlite.Connection, name: str, sql: str):
    """Apply a single migration."""
    async with conn.execute("SELECT 1 FROM migrations WHERE name = ?", (name,)) as cursor:
        if await cursor.fetchone():
            return # Already applied
            
    logger.info(f"Applying migration: {name}")
    try:
        await conn.executescript(sql)
        await conn.execute("INSERT INTO migrations (name) VALUES (?)", (name,))
        await conn.commit()
    except Exception as e:
        await conn.rollback()
        logger.error(f"Failed to apply migration {name}: {e}")
        raise

async def run_migrations(db_path: str, schema_path: str):
    """Run all pending migrations."""
    db_exists = os.path.exists(db_path)
    
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        
        # Create migrations table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.commit()
        
        if not db_exists or not await conn.execute("SELECT 1 FROM migrations WHERE name = '001_initial_schema'"):
            with open(schema_path, "r") as f:
                schema_sql = f.read()
            await apply_migration(conn, "001_initial_schema", schema_sql)
            
    logger.info("Migrations complete")
