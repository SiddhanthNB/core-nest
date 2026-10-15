import math
import time
from types import SimpleNamespace

from fastapi import BackgroundTasks, Depends, HTTPException, Request, status
from redis.exceptions import RedisError

from app.api.deps.auth import auth
from app.config import constants
from app.config.logger import logger
from app.config.redis import redis_client
from app.db.schemas.clients import Client as ClientSchema

_DEFAULT_RATE_LIMITS = SimpleNamespace(**constants.DEFAULT_RATE_LIMITS)


# (name, seconds, config field)
_WINDOWS = (("minute", 60, "requests_per_minute"), ("hour", 3600, "requests_per_hour"), ("day", 86400, "requests_per_day"))  # fmt: skip


async def _increment_with_expiry(key: str, ttl: int) -> int:
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, ttl)
    return int(count)


async def _decrement_concurrent_counter(key: str) -> None:
    await redis_client.decr(key)


async def _sliding_window(key: str, window: int, now: float) -> tuple[int, int, float]:
    """Count this request; return (previous window count, current window count, seconds into current window)."""
    window_start = int(now) // window * window
    previous = int(await redis_client.get(f"{key}:{window_start - window}") or 0)
    # kept for two windows: it is read as the "previous" window during the next one
    current = await _increment_with_expiry(f"{key}:{window_start}", 2 * window)
    return previous, current, now - window_start


def _retry_after(previous: int, current: int, limit: int, elapsed: float, window: int) -> int:
    if current < limit:  # over only because of the previous window: wait for its weight to decay
        wait = window * (1 - (limit - current) / previous) - elapsed
    else:  # wait for this window to end and then decay
        wait = (window - elapsed) + window * (1 - limit / current)
    return max(1, math.ceil(wait))


async def rate_limiter(request: Request, background_tasks: BackgroundTasks, current_client: ClientSchema.Read = Depends(auth)) -> None:  # fmt: skip
    """
    Apply sliding-window rate limits based on the resolved client schema.
    """
    request.state.client = current_client

    config = current_client.rate_limit_config or _DEFAULT_RATE_LIMITS
    client_id = str(current_client.id)
    now = time.time()

    try:
        for name, window, field in _WINDOWS:
            limit = getattr(config, field)
            if limit is None:
                continue
            # previous window weighted by how much of it still overlaps the last `window` seconds
            previous, current, elapsed = await _sliding_window(f"{constants.REDIS_KEY_PREFIX}:rate_limit:{client_id}:{name}", window, now)  # fmt: skip
            if previous * (1 - elapsed / window) + current > limit:
                retry_after = _retry_after(previous, current, limit, elapsed, window)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests per {name} - Try Again after {retry_after} seconds",
                    headers={"Retry-After": f"{retry_after}"},
                )

        if config.concurrent_requests_limit is not None:
            concurrent_key = f"{constants.REDIS_KEY_PREFIX}:concurrent:{client_id}"
            current_concurrent_count = await redis_client.incr(concurrent_key)
            await redis_client.expire(concurrent_key, 300)

            if current_concurrent_count > config.concurrent_requests_limit:
                await _decrement_concurrent_counter(concurrent_key)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many concurrent requests",
                )

            background_tasks.add_task(_decrement_concurrent_counter, concurrent_key)
    except HTTPException:
        raise
    except RedisError as exc:
        logger.error(f"Rate limiting backend failure: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiting unavailable",
        ) from exc
