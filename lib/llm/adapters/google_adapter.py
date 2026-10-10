from typing import Any

from redis.asyncio import Redis

from .base_adapter import BaseAdapter

# specific to gemini-2.5-flash-lite: it rejects penalties ("Penalty is not enabled") but litellm still forwards them
# revisit if the google completion model changes
_COMPLETION_DROP_PARAMS = ["presence_penalty", "frequency_penalty"]


class GoogleAdapter(BaseAdapter):
    def __init__(self, *, redis: Redis, request: Any = None, provider_preference: str | None = None):
        super().__init__(provider_name="google", redis=redis, request=request, provider_preference=provider_preference)
        api_key = self._api_key()
        if self._completion_model:
            self._completion_router = self._shared_router("completion", self._completion_model, api_key, additional_drop_params=_COMPLETION_DROP_PARAMS)  # fmt: skip
        if self._embedding_model:
            self._embedding_router = self._shared_router("embedding", self._embedding_model, api_key)
