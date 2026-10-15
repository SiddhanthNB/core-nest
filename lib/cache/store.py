from app.config.redis import redis_client


async def set_cache(key: str, value: str, ttl: int | None = None):
    """Set a value in the cache with an optional TTL in seconds."""
    await redis_client.set(key, value, ex=ttl)


async def get_cache(key: str, ttl: int | None = None) -> str | None:
    """Get a value from the cache; with a TTL, also reset its expiry (sliding)."""
    if ttl is None:
        return await redis_client.get(key)
    return await redis_client.getex(key, ex=ttl)


async def delete_cache(*keys: str):
    """Delete one or more keys from the cache."""
    if keys:
        await redis_client.delete(*keys)


async def update_cache(key: str, value: str):
    """Update an existing key while preserving its TTL."""
    await redis_client.set(key, value, keepttl=True)
