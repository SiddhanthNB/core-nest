from app.config.redis import redis_client


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
    """Update an existing key while preserving its TTL."""
    await redis_client.set(key, value, keepttl=True)


async def touch_cache(key: str, ttl: int):
    """Refresh the expiration time of an existing key."""
    await redis_client.expire(key, ttl)
