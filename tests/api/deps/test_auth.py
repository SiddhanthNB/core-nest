from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import fakeredis.aioredis
import pytest
from redis.exceptions import RedisError
from starlette.requests import Request

from app.api.deps.auth import CACHE_TTL, auth
from app.db.schemas.clients import Client as ClientSchema


def _request_with_auth(token: str = "secret-key") -> Request:
    scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    }
    return Request(scope)


def _client_payload() -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        name="Test Client",
        is_active=True,
        created_at=now,
        updated_at=now,
        rate_limit_config=SimpleNamespace(
            id=1,
            client_id=uuid4(),
            requests_per_minute=10,
            requests_per_hour=100,
            requests_per_day=1000,
            concurrent_requests_limit=2,
            created_at=now,
            updated_at=now,
        ),
    )


@pytest.mark.asyncio
async def test_auth_uses_cache_and_attaches_request_state(mocker) -> None:
    request = _request_with_auth()
    cached_client = _client_payload()

    cached_schema = ClientSchema.Read.model_validate(cached_client)

    get_cache = mocker.patch("app.api.deps.auth.get_cache", new=mocker.AsyncMock())
    set_cache = mocker.patch("app.api.deps.auth.set_cache", new=mocker.AsyncMock())
    get_cache.return_value = cached_schema.model_dump_json()

    client = await auth(request)

    assert request.state.client == client
    set_cache.assert_not_called()


@pytest.mark.asyncio
async def test_auth_db_miss_eager_loads_rate_limit_config_and_caches(mocker) -> None:
    request = _request_with_auth()
    orm_client = _client_payload()

    class _FakeQuery:
        def __init__(self, results):
            self.results = results
            self.limit_value = None

        def limit(self, value):
            self.limit_value = value
            return self

        async def aexec(self):
            return self.results

    mocker.patch("app.api.deps.auth.get_cache", new=mocker.AsyncMock(return_value=None))
    set_cache = mocker.patch("app.api.deps.auth.set_cache", new=mocker.AsyncMock())
    fake_query = _FakeQuery([orm_client])
    where = mocker.patch("app.api.deps.auth.Client.where", return_value=fake_query)

    client = await auth(request)

    assert request.state.client == client
    where.assert_called_once()
    assert fake_query.limit_value == 1
    set_cache.assert_awaited_once()


@pytest.mark.asyncio
async def test_auth_falls_back_to_db_when_cache_read_fails(mocker) -> None:
    request = _request_with_auth()
    orm_client = _client_payload()

    class _FakeQuery:
        def __init__(self, results):
            self.results = results

        def limit(self, value):
            return self

        async def aexec(self):
            return self.results

    mocker.patch("app.api.deps.auth.get_cache", new=mocker.AsyncMock(side_effect=RedisError("boom")))
    set_cache = mocker.patch("app.api.deps.auth.set_cache", new=mocker.AsyncMock())
    where = mocker.patch("app.api.deps.auth.Client.where", return_value=_FakeQuery([orm_client]))

    client = await auth(request)

    assert request.state.client == client
    where.assert_called_once()
    set_cache.assert_awaited_once()


@pytest.mark.asyncio
async def test_auth_succeeds_when_cache_write_fails(mocker) -> None:
    request = _request_with_auth()
    orm_client = _client_payload()

    class _FakeQuery:
        def __init__(self, results):
            self.results = results

        def limit(self, value):
            return self

        async def aexec(self):
            return self.results

    mocker.patch("app.api.deps.auth.get_cache", new=mocker.AsyncMock(return_value=None))
    mocker.patch("app.api.deps.auth.set_cache", new=mocker.AsyncMock(side_effect=RedisError("boom")))
    where = mocker.patch("app.api.deps.auth.Client.where", return_value=_FakeQuery([orm_client]))

    client = await auth(request)

    assert request.state.client == client
    where.assert_called_once()


@pytest.mark.asyncio
async def test_auth_cache_hit_does_not_refresh_ttl(mocker) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch("lib.cache.store.redis_client", fake_redis)
    request = _request_with_auth()
    cache_key = f"client:{hashlib.sha256(b'secret-key').hexdigest()}"
    cached_schema = ClientSchema.Read.model_validate(_client_payload())
    await fake_redis.set(cache_key, cached_schema.model_dump_json(), ex=CACHE_TTL)
    await fake_redis.expire(cache_key, 10)

    client = await auth(request)

    assert request.state.client == client
    assert 0 < await fake_redis.ttl(cache_key) <= 10
