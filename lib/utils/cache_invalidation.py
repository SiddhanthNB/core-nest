import asyncio

from lib.cache.store import delete_cache


def flush_client_cache(mapper, connection, target):
    hashed_key = target.hashed_api_key
    if hashed_key:
        asyncio.run(delete_cache(f"client:{hashed_key}"))
