import asyncio
from app.config.redis import delete_cache

def flush_client_cache(mapper, connection, target):
    """
    Flushes the client's cache entry from Redis.
    This function is called on after_update and after_delete events.
    """
    hashed_key = target.hashed_api_key
    if hashed_key:
        asyncio.run(delete_cache(f"client:{hashed_key}")) #implement bg tasks using redis later
