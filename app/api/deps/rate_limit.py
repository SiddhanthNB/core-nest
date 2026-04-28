from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, HTTPException, Request, status
from redis.exceptions import RedisError

from app.api.deps.auth import auth
from app.config.logger import logger
from app.config.redis import redis_client
from app.db.schemas.clients import Client as ClientSchema


async def _increment_with_expiry(key: str, ttl: int) -> int:
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, ttl)
    return int(count)


async def rate_limiter(request: Request, background_tasks: BackgroundTasks, current_client: ClientSchema.Read = Depends(auth)) -> None:
    """
    Apply rate limiting based on the resolved client schema.
    """
    request.state.client = current_client

    if not current_client.rate_limit_config:
        return

    config = current_client.rate_limit_config
    client_id = str(current_client.id)
    now = datetime.now(timezone.utc)

    try:
        if config.requests_per_minute is not None:
            minute_key = f"rate_limit:{client_id}:minute:{now.strftime('%Y%m%d%H%M')}"
            count = await _increment_with_expiry(minute_key, 60)
            if count > config.requests_per_minute:
                retry_after = 60 - now.second
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests per minute - Try Again after {retry_after} seconds",
                    headers={"Retry-After": f"{retry_after}"},
                )

        if config.requests_per_hour is not None:
            hour_key = f"rate_limit:{client_id}:hour:{now.strftime('%Y%m%d%H')}"
            count = await _increment_with_expiry(hour_key, 3600)
            if count > config.requests_per_hour:
                retry_after = 3600 - now.second
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests per hour - Try Again after {retry_after} seconds",
                    headers={"Retry-After": f"{retry_after}"},
                )

        if config.requests_per_day is not None:
            day_key = f"rate_limit:{client_id}:day:{now.strftime('%Y%m%d')}"
            count = await _increment_with_expiry(day_key, 86400)
            if count > config.requests_per_day:
                retry_after = 86400 - now.second
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests per day - Try Again after {retry_after} seconds",
                    headers={"Retry-After": f"{retry_after}"},
                )

        if config.concurrent_requests_limit is not None:
            concurrent_key = f"concurrent:{client_id}"
            current_concurrent_count = await redis_client.incr(concurrent_key)
            await redis_client.expire(concurrent_key, 300)

            if current_concurrent_count > config.concurrent_requests_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many concurrent requests",
                )

            async def decrement_concurrent_counter() -> None:
                await redis_client.decr(concurrent_key)

            background_tasks.add_task(decrement_concurrent_counter)
    except HTTPException:
        raise
    except RedisError as exc:
        logger.error(f"Rate limiting backend failure: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiting unavailable",
        ) from exc
