from __future__ import annotations

import secrets
from typing import Any

from redis.exceptions import RedisError

from app.api.deps.auth import client_cache_key, hash_api_key
from app.config import constants
from app.db import db
from app.db.models.clients import Client
from app.db.models.rate_limit_configs import RateLimitConfig
from lib.cache.store import delete_cache

# these tasks are the only write path for clients: every change evicts the auth cache, so it applies immediately


async def create_client(name: str, **limits: int | None) -> None:
    name = _clean_name(name)
    if await Client.where(Client.name == name).aexec():
        raise SystemExit(f"Client '{name}' already exists.")

    api_key = secrets.token_urlsafe(32)
    config = {field: limits.get(field) or default for field, default in constants.DEFAULT_RATE_LIMITS.items()}
    async with db.atransaction():
        client = await Client.acreate(name=name, hashed_api_key=hash_api_key(api_key))
        await RateLimitConfig.acreate(client_id=client.id, **config)

    _print_client("Created", await _load_client(name), api_key=api_key)


async def get_client(name: str) -> None:
    _print_client("Client", await _load_client(name))


async def update_client(name: str, *, activate: bool = False, deactivate: bool = False, rotate_key: bool = False, **limits: int | None) -> None:  # fmt: skip
    if activate and deactivate:
        raise SystemExit("Use either --activate or --deactivate, not both.")
    client = await _load_client(name)
    old_hashed_api_key = client.hashed_api_key
    limit_changes = {field: value for field, value in limits.items() if value is not None}

    fields: dict[str, Any] = {}
    if activate or deactivate:
        fields["is_active"] = activate
    api_key = None
    if rotate_key:
        api_key = secrets.token_urlsafe(32)
        fields["hashed_api_key"] = hash_api_key(api_key)
    if not fields and not limit_changes:
        raise SystemExit("Nothing to update.")

    async with db.atransaction():
        if fields:
            await client.aupdate(**fields)
        if limit_changes and client.rate_limit_config:
            await client.rate_limit_config.aupdate(**limit_changes)
        elif limit_changes:
            await RateLimitConfig.acreate(client_id=client.id, **{**constants.DEFAULT_RATE_LIMITS, **limit_changes})

    await _evict(old_hashed_api_key)
    _print_client("Updated", await _load_client(client.name), api_key=api_key)


async def delete_client(name: str) -> None:
    client = await _load_client(name)
    # the rate-limit config row goes with it (ON DELETE CASCADE)
    await Client.where(Client.id == client.id).adelete()
    await _evict(client.hashed_api_key)
    _print_client("Deleted", client)


async def list_clients() -> None:
    clients = await Client.where().order_by("created_at").aexec()
    if not clients:
        print("No clients.")
        return
    for client in clients:
        status = "active" if client.is_active else "inactive"
        print(f"{client.name:<30} {status:<9} {_limits_line(client.rate_limit_config):<45} created {client.created_at:%Y-%m-%d}")  # fmt: skip


def _clean_name(name: str) -> str:
    if not name or not name.strip():
        raise SystemExit("Client name must be provided.")
    if name.strip().startswith("-"):
        raise SystemExit("Client name can't start with '-'.")
    return name.strip()


async def _load_client(name: str) -> Any:
    name = _clean_name(name)
    clients = await Client.where(Client.name == name).aexec()
    if not clients:
        raise SystemExit(f"Client '{name}' not found.")
    if len(clients) > 1:
        raise SystemExit(f"Multiple clients named '{name}'; fix the duplicates in the database first.")
    return clients[0]


async def _evict(hashed_api_key: str) -> None:
    try:
        await delete_cache(client_cache_key(hashed_api_key))
    except RedisError as exc:
        # the cache TTL is sliding, so a missed eviction would keep the old state alive; never fail silently
        raise SystemExit(f"Database updated, but evicting the auth cache failed ({type(exc).__name__}). Rerun the same command.") from exc  # fmt: skip


def _limits_line(config: Any) -> str:
    limits = {field: getattr(config, field) for field in constants.DEFAULT_RATE_LIMITS} if config else constants.DEFAULT_RATE_LIMITS  # fmt: skip
    line = f"{limits['requests_per_minute']}/min · {limits['requests_per_hour']}/hour · {limits['requests_per_day']}/day · {limits['concurrent_requests_limit']} concurrent"  # fmt: skip
    return line if config else f"{line} (defaults)"


def _print_client(action: str, client: Any, *, api_key: str | None = None) -> None:
    print("=" * 50)
    print(f"{action}: {client.name}")
    print(f"  ID:      {client.id}")
    print(f"  Status:  {'active' if client.is_active else 'inactive'}")
    print(f"  Limits:  {_limits_line(client.rate_limit_config)}")
    print(f"  Created: {client.created_at:%Y-%m-%d %H:%M}")
    if api_key:
        print(f"  API Key: {api_key}")
        print("  Store this key now. It will not be shown again.")
    print("=" * 50)
