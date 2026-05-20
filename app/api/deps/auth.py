import hashlib

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.config.logger import logger
from app.db.models import Client
from app.db.schemas.clients import Client as ClientSchema
from lib.cache.store import get_cache, set_cache, touch_cache

CACHE_TTL = 300


def _extract_api_key(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Authentication failed: invalid or missing Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Authorization header",
        )
    return auth_header.split(" ", 1)[1]


async def auth(request: Request) -> ClientSchema.Read:
    """
    Resolve the current client via API key.
    Uses cache-first lookup and eager-loads the rate-limit config on DB misses.
    """
    api_key = _extract_api_key(request)
    request_id = getattr(request.state, "request_id", None)
    request_id = request_id[:8] if request_id else None
    hashed_key = hashlib.sha256(api_key.encode()).hexdigest()
    cache_key = f"client:{hashed_key}"

    try:
        cached_client_json = await get_cache(cache_key)
    except RedisError as exc:
        logger.warning(f"[request_id: {request_id}] Client auth cache read failed with {type(exc).__name__}")
        cached_client_json = None
    if cached_client_json:
        logger.debug(f"[request_id: {request_id}] Client auth cache hit")
        try:
            await touch_cache(cache_key, ttl=CACHE_TTL)
        except RedisError as exc:
            logger.warning(f"[request_id: {request_id}] Client auth cache touch failed with {type(exc).__name__}")
        client_data = ClientSchema.Read.model_validate_json(cached_client_json)
        request.state.client = client_data
        return client_data

    logger.debug(f"[request_id: {request_id}] Client auth cache miss")
    client_records = await Client.where(Client.hashed_api_key == hashed_key).limit(1).aexec()
    client_record = client_records[0] if client_records else None

    if not client_record or not client_record.is_active:
        logger.warning("Authentication failed: invalid or inactive API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API Key",
        )

    client_out = ClientSchema.Read.model_validate(client_record)
    request.state.client = client_out
    try:
        await set_cache(cache_key, client_out.model_dump_json(), ttl=CACHE_TTL)
    except RedisError as exc:
        logger.warning(f"[request_id: {request_id}] Client auth cache write failed with {type(exc).__name__}")
    else:
        logger.debug(f"[request_id: {request_id}] Client auth cache write")
    return client_out
