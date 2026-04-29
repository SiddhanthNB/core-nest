from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
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
    now = datetime.now(timezone.utc)
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
    touch_cache = mocker.patch("app.api.deps.auth.touch_cache", new=mocker.AsyncMock())
    set_cache = mocker.patch("app.api.deps.auth.set_cache", new=mocker.AsyncMock())
    get_cache.return_value = cached_schema.model_dump_json()

    client = await auth(request)

    assert request.state.client == client
    touch_cache.assert_awaited_once_with(
        f"client:{hashlib.sha256('secret-key'.encode()).hexdigest()}",
        ttl=CACHE_TTL,
    )
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
