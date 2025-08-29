import json
import hashlib
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.db_session import get_db_session
from app.config.redis import get_cache, set_cache, touch_cache
from app.db.models import Client
from app.api.schemas.client_schemas import ClientOut

CACHE_TTL = 300

async def get_current_client(request: Request, db_session: AsyncSession = Depends(get_db_session)) -> ClientOut:
    """
    FastAPI dependency to authenticate a client via API key.
    Implements a sliding-window read-through caching strategy using Redis.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing Authorization header")

    api_key = auth_header.split(" ")[1]
    hashed_key = hashlib.sha256(api_key.encode()).hexdigest()

    cache_key = f"client:{hashed_key}"

    cached_client_json = await get_cache(cache_key)
    if cached_client_json:
        await touch_cache(cache_key, ttl=CACHE_TTL)
        client_data = json.loads(cached_client_json)
        return ClientOut(**client_data)

    results = await Client.fetch_records(db_session, filters={"hashed_api_key": hashed_key})
    client_record = results[0] if results else None

    if not client_record or not client_record.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive API Key")

    client_out = ClientOut.model_validate(client_record)
    await set_cache(cache_key, client_out.model_dump_json(), ttl=CACHE_TTL)

    return client_out
