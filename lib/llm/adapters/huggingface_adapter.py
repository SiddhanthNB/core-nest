from typing import Any

from redis.asyncio import Redis

from .base_adapter import BaseAdapter


class HuggingfaceAdapter(BaseAdapter):
    def __init__(self, *, redis: Redis, request: Any = None, provider_preference: str | None = None):
        super().__init__(
            provider_name="huggingface",
            redis=redis,
            request=request,
            provider_preference=provider_preference,
        )
        api_key = self._api_key()
        if self._completion_model:
            self._completion_router = self._shared_router("completion", self._completion_model, api_key)
