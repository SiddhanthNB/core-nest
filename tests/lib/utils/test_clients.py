from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import fakeredis.aioredis
import pytest
from redis.exceptions import RedisError

from app.api.deps.auth import client_cache_key, hash_api_key
from app.config import constants
from lib.utils import clients


class _Column:
    def __init__(self, field: str):
        self.field = field

    def __eq__(self, value):  # Client.name == "Acme" -> ("name", "Acme")
        return (self.field, value)


class _Query:
    def __init__(self, store, predicate=None):
        self.store, self.predicate = store, predicate

    def _matches(self, client) -> bool:
        return self.predicate is None or getattr(client, self.predicate[0]) == self.predicate[1]

    def order_by(self, *_):
        return self

    async def aexec(self):
        return [client for client in self.store.clients if self._matches(client)]

    async def adelete(self):
        self.store.clients = [client for client in self.store.clients if not self._matches(client)]
        return 1


class _Record(SimpleNamespace):
    async def aupdate(self, **fields):
        for key, value in fields.items():
            setattr(self, key, value)
        return self


@pytest.fixture
def store(mocker):
    store = SimpleNamespace(clients=[])

    async def _create_client(**fields):
        record = _Record(id=uuid4(), is_active=True, created_at=datetime.now(UTC), rate_limit_config=None, **fields)
        store.clients.append(record)
        return record

    async def _create_config(client_id, **limits):
        record = _Record(client_id=client_id, **limits)
        next(client for client in store.clients if client.id == client_id).rate_limit_config = record
        return record

    fake_client = SimpleNamespace(name=_Column("name"), id=_Column("id"), acreate=_create_client, where=lambda *predicates: _Query(store, predicates[0] if predicates else None))  # fmt: skip
    mocker.patch.object(clients, "Client", fake_client)
    mocker.patch.object(clients, "RateLimitConfig", SimpleNamespace(acreate=_create_config))

    @asynccontextmanager
    async def _transaction():
        yield

    mocker.patch.object(clients.db, "atransaction", _transaction)
    return store


@pytest.fixture
def redis(mocker):
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch("lib.cache.store.redis_client", fake_redis)
    return fake_redis


def _key_from(output: str) -> str:
    return next(line.split("API Key:")[1].strip() for line in output.splitlines() if "API Key:" in line)


@pytest.mark.asyncio
async def test_create_uses_defaults_and_overrides_and_prints_key_once(store, redis, capsys) -> None:
    await clients.create_client("Acme", requests_per_minute=10)

    client = store.clients[0]
    output = capsys.readouterr().out
    assert client.hashed_api_key == hash_api_key(_key_from(output))
    assert client.rate_limit_config.requests_per_minute == 10
    assert client.rate_limit_config.requests_per_day == constants.DEFAULT_RATE_LIMITS["requests_per_day"]
    assert "Created: Acme" in output


@pytest.mark.asyncio
async def test_create_rejects_duplicate_name(store, redis) -> None:
    await clients.create_client("Acme")

    with pytest.raises(SystemExit, match="already exists"):
        await clients.create_client("Acme")


@pytest.mark.asyncio
async def test_update_deactivate_evicts_cache_immediately(store, redis) -> None:
    await clients.create_client("Acme")
    hashed_api_key = store.clients[0].hashed_api_key
    await redis.set(client_cache_key(hashed_api_key), "cached")

    await clients.update_client("Acme", deactivate=True, requests_per_minute=5)

    assert store.clients[0].is_active is False
    assert store.clients[0].rate_limit_config.requests_per_minute == 5
    assert not await redis.exists(client_cache_key(hashed_api_key))


@pytest.mark.asyncio
async def test_update_rotate_key_evicts_old_key_and_prints_new_one(store, redis, capsys) -> None:
    await clients.create_client("Acme")
    old_hashed_api_key = store.clients[0].hashed_api_key
    await redis.set(client_cache_key(old_hashed_api_key), "cached")
    capsys.readouterr()

    await clients.update_client("Acme", rotate_key=True)

    new_key = _key_from(capsys.readouterr().out)
    assert store.clients[0].hashed_api_key == hash_api_key(new_key) != old_hashed_api_key
    assert not await redis.exists(client_cache_key(old_hashed_api_key))


@pytest.mark.asyncio
async def test_update_fails_loudly_when_eviction_fails(store, redis, mocker) -> None:
    await clients.create_client("Acme")
    mocker.patch.object(clients, "delete_cache", mocker.AsyncMock(side_effect=RedisError("down")))

    with pytest.raises(SystemExit, match="Rerun the same command"):
        await clients.update_client("Acme", deactivate=True)


@pytest.mark.asyncio
async def test_update_without_changes_is_rejected(store, redis) -> None:
    await clients.create_client("Acme")

    with pytest.raises(SystemExit, match="Nothing to update"):
        await clients.update_client("Acme")


@pytest.mark.asyncio
async def test_delete_removes_client_and_evicts_cache(store, redis) -> None:
    await clients.create_client("Acme")
    hashed_api_key = store.clients[0].hashed_api_key
    await redis.set(client_cache_key(hashed_api_key), "cached")

    await clients.delete_client("Acme")

    assert store.clients == []
    assert not await redis.exists(client_cache_key(hashed_api_key))


@pytest.mark.asyncio
async def test_unknown_client_is_reported(store, redis) -> None:
    with pytest.raises(SystemExit, match="not found"):
        await clients.get_client("Nobody")


@pytest.mark.asyncio
@pytest.mark.parametrize("name, error", [(None, "must be provided"), ("  ", "must be provided"), ("--help", "can't start with '-'"), ("-h", "can't start with '-'")])  # fmt: skip
async def test_create_rejects_missing_or_flag_like_name(store, redis, name, error) -> None:
    with pytest.raises(SystemExit, match=error):
        await clients.create_client(name)


@pytest.mark.parametrize("argv", [["clients.create", "--help"], ["clients.create", "-h"], ["clients.delete", "--help"]])
def test_help_flag_shows_help_instead_of_becoming_the_name(mocker, argv) -> None:
    from invoke import Program

    from tasks import ns

    create, delete = mocker.patch.object(clients, "create_client"), mocker.patch.object(clients, "delete_client")
    with pytest.raises(SystemExit) as raised:
        Program(namespace=ns).run(["invoke", *argv], exit=True)

    assert raised.value.code == 0
    create.assert_not_called()
    delete.assert_not_called()
