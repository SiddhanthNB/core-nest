from app.config.logger import logger
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status, Request, BackgroundTasks
from app.config.redis import redis_client
from app.api.dependencies import get_current_client
from app.api.schemas.client_schemas import ClientOut

async def apply_rate_limiting(request: Request, background_tasks: BackgroundTasks, current_client: ClientOut = Depends(get_current_client)):
    """
    FastAPI dependency to apply rate limiting based on client configuration.
    """
    if not current_client.rate_limit_config:
        return

    client_id = str(current_client.id)
    now = datetime.now(timezone.utc)

    try:
        if current_client.rate_limit_config.requests_per_minute is not None:
            minute_key = f"rate_limit:{client_id}:minute:{now.strftime('%Y%m%d%H%M')}"
            count = await redis_client.incr(minute_key)

            if count == 1:
                await redis_client.expire(minute_key, 60)

            if count > current_client.rate_limit_config.requests_per_minute:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Too many requests per minute - Try Again after {60 - now.second} seconds", headers={"Retry-After": f"{60 - now.second}"})
    except HTTPStatusError as e:
        raise
    except Exception as e:
        logger.error(f"Error occurred while applying rate limiting in minute: {e}")

    try:
        if current_client.rate_limit_config.requests_per_hour is not None:
            hour_key = f"rate_limit:{client_id}:hour:{now.strftime('%Y%m%d%H')}"
            count = await redis_client.incr(hour_key)

            if count == 1:
                await redis_client.expire(hour_key, 3600)

            if count > current_client.rate_limit_config.requests_per_hour:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Too many requests per hour - Try Again after {3600 - now.second} seconds", headers={"Retry-After": f"{3600 - now.second}"})
    except HTTPStatusError as e:
        raise
    except Exception as e:
        logger.error(f"Error occurred while applying rate limiting in hour: {e}")

    try:
        if current_client.rate_limit_config.requests_per_day is not None:
            day_key = f"rate_limit:{client_id}:day:{now.strftime('%Y%m%d')}"
            count = await redis_client.incr(day_key)

            if count == 1:
                await redis_client.expire(day_key, 86400)

            if count > current_client.rate_limit_config.requests_per_day:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Too many requests per day - Try Again after {86400 - now.second} seconds", headers={"Retry-After": f"{86400 - now.second}"})
    except HTTPStatusError as e:
        raise
    except Exception as e:
        logger.error(f"Error occurred while applying rate limiting in day: {e}")


    try:
        if current_client.rate_limit_config.concurrent_requests_limit is not None:
            concurrent_key = f"concurrent:{client_id}"
            current_concurrent_count = await redis_client.incr(concurrent_key)

            await redis_client.expire(concurrent_key, 300)
            if current_concurrent_count > current_client.rate_limit_config.concurrent_requests_limit:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many concurrent requests")

            async def decrement_concurrent_counter():
                await redis_client.decr(concurrent_key)

            background_tasks.add_task(decrement_concurrent_counter)
    except HTTPStatusError as e:
        raise
    except Exception as e:
        logger.error(f"Error occurred while applying rate limiting in concurrent requests: {e}")
