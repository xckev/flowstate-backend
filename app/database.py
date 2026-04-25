"""MongoDB Motor async client — opened/closed via FastAPI lifespan."""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError("MongoDB client is not initialised. Call connect_db() first.")
    return _client


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[get_settings().mongodb_db_name]


async def connect_db() -> None:
    """Open the MongoDB connection. Called on app startup."""
    global _client
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongodb_uri)
    # Ensure unique indexes exist
    db = _client[settings.mongodb_db_name]
    await db.users.create_index("user_id", unique=True)
    await db.preferences.create_index("user_id", unique=True)
    # OAuth state store — TTL index auto-deletes documents after 10 minutes
    await db.oauth_states.create_index("created_at", expireAfterSeconds=600)


async def close_db() -> None:
    """Close the MongoDB connection. Called on app shutdown."""
    global _client
    if _client:
        _client.close()
        _client = None
