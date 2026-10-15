from __future__ import annotations

from datetime import UTC, datetime
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


def _client_schema(*, requests_per_minute: int | None = None, requests_per_hour: int | None = None, requests_per_day: int | None = None, concurrent_requests_limit: int | None = None):  # fmt: skip
    now = datetime.now(UTC)
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
        get=mocker.AsyncMock(side_effect=RedisError("boom")),
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


# a multiple of 60 and 3600, so window boundaries are easy to reason about
_T0 = 1_800_000_000


def _clock(mocker, now: float) -> None:
    mocker.patch("app.api.deps.rate_limit.time", SimpleNamespace(time=lambda: now))


@pytest.mark.asyncio
async def test_sliding_window_blocks_burst_across_window_edge(mocker) -> None:
    mocker.patch("app.api.deps.rate_limit.redis_client", fakeredis.aioredis.FakeRedis(decode_responses=True))
    client = _client_schema(requests_per_minute=2)
    _clock(mocker, _T0 + 59)
    for _ in range(2):
        await rate_limiter(_request(), BackgroundTasks(), current_client=client)

    # a fixed window would reset here; the sliding window still counts the previous minute in full
    _clock(mocker, _T0 + 60)
    with pytest.raises(HTTPException) as exc_info:
        await rate_limiter(_request(), BackgroundTasks(), current_client=client)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "30"


@pytest.mark.asyncio
async def test_sliding_window_allows_once_previous_window_decays(mocker) -> None:
    mocker.patch("app.api.deps.rate_limit.redis_client", fakeredis.aioredis.FakeRedis(decode_responses=True))
    client = _client_schema(requests_per_minute=2)
    _clock(mocker, _T0 + 59)
    for _ in range(2):
        await rate_limiter(_request(), BackgroundTasks(), current_client=client)

    _clock(mocker, _T0 + 60 + 31)  # previous minute now weighs 29/60: 2 * 0.48 + 1 <= 2
    await rate_limiter(_request(), BackgroundTasks(), current_client=client)


@pytest.mark.asyncio
@pytest.mark.parametrize("field, window", [("requests_per_hour", 3600), ("requests_per_day", 86400)])
async def test_sliding_window_retry_after_waits_for_window_to_end_and_decay(mocker, field, window) -> None:
    mocker.patch("app.api.deps.rate_limit.redis_client", fakeredis.aioredis.FakeRedis(decode_responses=True))
    now = _T0 // window * window + 15
    _clock(mocker, now)

    with pytest.raises(HTTPException) as exc_info:
        await rate_limiter(_request(), BackgroundTasks(), current_client=_client_schema(**{field: 0}))

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == str((window - 15) + window)


@pytest.mark.asyncio
async def test_rate_limiter_concurrent_rejection_releases_slot(mocker) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch("app.api.deps.rate_limit.redis_client", fake_redis)
    client = _client_schema(concurrent_requests_limit=1)
    concurrent_key = f"core-nest:concurrent:{client.id}"

    await rate_limiter(_request(), BackgroundTasks(), current_client=client)
    for _ in range(3):
        with pytest.raises(HTTPException) as exc_info:
            await rate_limiter(_request(), BackgroundTasks(), current_client=client)
        assert exc_info.value.status_code == 429

    assert int(await fake_redis.get(concurrent_key)) == 1


@pytest.mark.asyncio
async def test_rate_limiter_applies_default_limits_without_config(mocker) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch("app.api.deps.rate_limit.redis_client", fake_redis)
    mocker.patch("app.api.deps.rate_limit._DEFAULT_RATE_LIMITS", SimpleNamespace(requests_per_minute=1, requests_per_hour=None, requests_per_day=None, concurrent_requests_limit=None))  # fmt: skip
    client = _client_schema()
    client.rate_limit_config = None

    await rate_limiter(_request(), BackgroundTasks(), current_client=client)
    with pytest.raises(HTTPException) as exc_info:
        await rate_limiter(_request(), BackgroundTasks(), current_client=client)

    assert exc_info.value.status_code == 429
