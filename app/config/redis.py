import redis.asyncio as redis
from app.config import constants

redis_client = redis.from_url(constants.REDIS_URL, decode_responses=True)

__all__ = ["redis_client"]
