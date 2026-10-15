import time

import redis.asyncio as redis
from fakeredis import FakeAsyncRedis
from redis.exceptions import RedisError

from app.config import constants
from app.config.logger import logger

# after a Redis failure, skip it for this long instead of waiting on a timeout for every command
_PRIMARY_RETRY_SECONDS = 30


class _FallbackRedis:
    """Runs each command on Redis; while Redis is unreachable, runs it on an in-process copy instead (exact with a single worker)."""  # fmt: skip

    def __init__(self, primary, fallback):
        self._primary = primary
        self._fallback = fallback
        self._primary_down_until = 0.0

    def __getattr__(self, name):
        async def command(*args, **kwargs):
            if time.monotonic() >= self._primary_down_until:
                try:
                    return await getattr(self._primary, name)(*args, **kwargs)
                except RedisError as exc:
                    self._primary_down_until = time.monotonic() + _PRIMARY_RETRY_SECONDS
                    logger.warning(f"Redis unavailable ({type(exc).__name__}); using in-memory fallback for {_PRIMARY_RETRY_SECONDS}s")  # fmt: skip
            return await getattr(self._fallback, name)(*args, **kwargs)

        return command


redis_client = _FallbackRedis(
    redis.from_url(
        constants.REDIS_URL,
        decode_responses=True,
        health_check_interval=30,
        socket_keepalive=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    ),
    FakeAsyncRedis(decode_responses=True),
)

__all__ = ["redis_client"]
