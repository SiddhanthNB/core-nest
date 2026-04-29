from typing import Any

from redis.asyncio import Redis

from .base_adapter import BaseAdapter
from .cerebras_adapter import CerebrasAdapter
from .google_adapter import GoogleAdapter
from .groq_adapter import GroqAdapter
from .huggingface_adapter import HuggingfaceAdapter
from .mistral_adapter import MistralAdapter
from .openai_adapter import OpenAIAdapter
from .openrouter_adapter import OpenRouterAdapter

_ADAPTERS = {
    "cerebras": CerebrasAdapter,
    "google": GoogleAdapter,
    "groq": GroqAdapter,
    "huggingface": HuggingfaceAdapter,
    "mistral": MistralAdapter,
    "openai": OpenAIAdapter,
    "openrouter": OpenRouterAdapter,
}


def get_adapter(provider_name: str, *, redis: Redis, request: Any = None) -> BaseAdapter:
    adapter_class = _ADAPTERS[provider_name]
    return adapter_class(redis=redis, request=request)


__all__ = [
    "BaseAdapter",
    "CerebrasAdapter",
    "GoogleAdapter",
    "GroqAdapter",
    "HuggingfaceAdapter",
    "MistralAdapter",
    "OpenAIAdapter",
    "OpenRouterAdapter",
    "get_adapter",
]
