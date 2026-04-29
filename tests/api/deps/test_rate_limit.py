from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import fakeredis.aioredis
import pytest
from fastapi import BackgroundTasks, HTTPException
from redis.exceptions import RedisError
from starlette.requests import Request

from app.api.deps.rate_limit import rate_limiter


def _request() -> Request:
    return Request({"type": "http", "headers": []})


def _client_schema(*, requests_per_minute: int | None = None, requests_per_hour: int | None = None, requests_per_day: int | None = None, concurrent_requests_limit: int | None = None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        rate_limit_config=SimpleNamespace(
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
            requests_per_day=requests_per_day,
            concurrent_requests_limit=concurrent_requests_limit,
        ),
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_rate_limiter_raises_429_when_limit_is_exceeded(mocker) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch("app.api.deps.rate_limit.redis_client", fake_redis)

    request = _request()
    background_tasks = BackgroundTasks()
    client = _client_schema(requests_per_minute=0)

    with pytest.raises(HTTPException) as exc_info:
        await rate_limiter(request, background_tasks, current_client=client)

    assert exc_info.value.status_code == 429
    assert request.state.client == client


@pytest.mark.asyncio
async def test_rate_limiter_raises_503_when_redis_fails(mocker) -> None:
    fake_redis = SimpleNamespace(
        incr=mocker.AsyncMock(side_effect=RedisError("boom")),
        expire=mocker.AsyncMock(),
        decr=mocker.AsyncMock(),
    )
    mocker.patch("app.api.deps.rate_limit.redis_client", fake_redis)

    request = _request()
    background_tasks = BackgroundTasks()
    client = _client_schema(requests_per_minute=1)

    with pytest.raises(HTTPException) as exc_info:
        await rate_limiter(request, background_tasks, current_client=client)

    assert exc_info.value.status_code == 503
