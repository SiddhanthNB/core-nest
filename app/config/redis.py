import redis.asyncio as redis
from app.utils import constants

redis_client = redis.from_url(constants.REDIS_URL, decode_responses=True)

# CACHE OPS
async def set_cache(key: str, value: str, ttl: int | None = None):
    """Set a value in the cache with an optional TTL in seconds."""
    await redis_client.set(key, value, ex=ttl)

async def get_cache(key: str) -> str | None:
    """Get a value from the cache."""
    return await redis_client.get(key)

async def delete_cache(*keys: str):
    """Delete one or more keys from the cache."""
    if keys:
        await redis_client.delete(*keys)

async def update_cache(key: str, value: str):
    """
    Updates the value of an existing key while preserving its TTL.
    """
    # The keepttl=True option ensures the existing expiration is not removed.
    await redis_client.set(key, value, keepttl=True)

async def touch_cache(key: str, ttl: int):
    """
    Updates the expiration time (TTL) of an existing key in seconds.
    """
    await redis_client.expire(key, ttl)
