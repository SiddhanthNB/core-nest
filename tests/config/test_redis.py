from __future__ import annotations

import pytest
from fakeredis import FakeAsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.config import constants
from app.config import redis as redis_config


class _DownRedis:
    def __init__(self):
        self.calls = 0

    async def incr(self, *_):
        self.calls += 1
        raise RedisConnectionError("unreachable")


def test_redis_url_uses_tls_with_upstash_token() -> None:
    assert constants.REDIS_URL.startswith("rediss://default:")
    assert constants.REDIS_URL.endswith(":6379")


@pytest.mark.asyncio
async def test_fallback_serves_commands_while_redis_is_down(mocker) -> None:
    primary = _DownRedis()
    client = redis_config._FallbackRedis(primary, FakeAsyncRedis(decode_responses=True))

    assert await client.incr("counter") == 1
    assert await client.incr("counter") == 2  # state is kept in memory
    assert primary.calls == 1  # skipped Redis after the first failure instead of timing out again


@pytest.mark.asyncio
async def test_fallback_retries_redis_after_the_skip_window(mocker) -> None:
    primary = _DownRedis()
    client = redis_config._FallbackRedis(primary, FakeAsyncRedis(decode_responses=True))
    clock = mocker.patch.object(redis_config.time, "monotonic", return_value=1000.0)

    await client.incr("counter")
    clock.return_value = 1000.0 + redis_config._PRIMARY_RETRY_SECONDS
    await client.incr("counter")

    assert primary.calls == 2


@pytest.mark.asyncio
async def test_fallback_uses_redis_when_it_is_up() -> None:
    primary, fallback = FakeAsyncRedis(decode_responses=True), FakeAsyncRedis(decode_responses=True)
    client = redis_config._FallbackRedis(primary, fallback)

    await client.set("key", "value")

    assert await primary.get("key") == "value"
    assert await fallback.get("key") is None
