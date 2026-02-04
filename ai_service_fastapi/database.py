# database.py - Async Database Connection

from databases import Database
from config import get_settings
import logging

logger = logging.getLogger(__name__)

# Global database instance
database: Database = None


async def get_database() -> Database:
    """Get the database instance"""
    global database
    if database is None:
        settings = get_settings()
        database = Database(settings.DATABASE_URL)
    return database


async def connect_database():
    """Connect to the database"""
    global database
    settings = get_settings()
    database = Database(settings.DATABASE_URL)
    await database.connect()
    logger.info(f"Connected to database: {settings.DATABASE_URL.split('@')[-1]}")


async def disconnect_database():
    """Disconnect from the database"""
    global database
    if database:
        await database.disconnect()
        logger.info("Disconnected from database")


async def fetch_one(query: str, values: dict = None):
    """Execute a query and fetch one result"""
    db = await get_database()
    return await db.fetch_one(query=query, values=values or {})


async def fetch_all(query: str, values: dict = None):
    """Execute a query and fetch all results"""
    db = await get_database()
    return await db.fetch_all(query=query, values=values or {})


async def execute(query: str, values: dict = None):
    """Execute a query without returning results"""
    db = await get_database()
    return await db.execute(query=query, values=values or {})
