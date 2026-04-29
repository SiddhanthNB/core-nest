from __future__ import annotations

import fakeredis.aioredis
import pytest

from lib.llm.adapters.cerebras_adapter import CerebrasAdapter
from lib.llm.adapters.groq_adapter import GroqAdapter
from lib.llm.adapters.huggingface_adapter import HuggingfaceAdapter
from lib.llm.adapters.openrouter_adapter import OpenRouterAdapter


class _Router:
    def __init__(self, *, model_list, num_retries, set_verbose):
        self.model_list = model_list
        self.num_retries = num_retries
        self.set_verbose = set_verbose


async def _redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_huggingface_adapter_remains_completion_only(monkeypatch) -> None:
    monkeypatch.setenv("HUGGINGFACE_API_KEY", "test-key")
    monkeypatch.setattr("lib.llm.adapters.huggingface_adapter.Router", _Router)

    adapter = HuggingfaceAdapter(redis=await _redis())

    assert adapter._completion_router is not None
    assert adapter._embedding_router is None


@pytest.mark.asyncio
async def test_openrouter_adapter_builds_embedding_router(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("lib.llm.adapters.openrouter_adapter.Router", _Router)

    adapter = OpenRouterAdapter(redis=await _redis())

    assert adapter._completion_router is not None
    assert adapter._embedding_router is not None


@pytest.mark.asyncio
async def test_groq_and_cerebras_remain_completion_only(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("CEREBRAS_API_KEY", "test-key")
    monkeypatch.setattr("lib.llm.adapters.groq_adapter.Router", _Router)
    monkeypatch.setattr("lib.llm.adapters.cerebras_adapter.Router", _Router)

    groq_adapter = GroqAdapter(redis=await _redis())
    cerebras_adapter = CerebrasAdapter(redis=await _redis())

    assert groq_adapter._completion_router is not None
    assert groq_adapter._embedding_router is None
    assert cerebras_adapter._completion_router is not None
    assert cerebras_adapter._embedding_router is None
