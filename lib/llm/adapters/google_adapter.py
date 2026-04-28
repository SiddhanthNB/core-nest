from typing import Any

from litellm import Router
from redis.asyncio import Redis

from .base_adapter import BaseAdapter


class GoogleAdapter(BaseAdapter):
    def __init__(self, *, redis: Redis, request: Any = None):
        super().__init__(provider_name="gemini", redis=redis, request=request)
        api_key = self._api_key()
        if self._completion_model:
            self._completion_router = Router(
                model_list=[{"model_name": self._completion_model, "litellm_params": {"model": self._completion_model, "api_key": api_key}}],
                num_retries=0,
                set_verbose=False,
            )
        if self._embedding_model:
            self._embedding_router = Router(
                model_list=[{"model_name": self._embedding_model, "litellm_params": {"model": self._embedding_model, "api_key": api_key}}],
                num_retries=0,
                set_verbose=False,
            )
