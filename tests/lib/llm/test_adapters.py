from __future__ import annotations

from types import SimpleNamespace

import fakeredis.aioredis
import pytest
from litellm import Timeout

from lib.llm.adapters.base_adapter import BaseAdapter
from lib.llm.adapters.cerebras_adapter import CerebrasAdapter
from lib.llm.adapters.groq_adapter import GroqAdapter
from lib.llm.adapters.huggingface_adapter import HuggingfaceAdapter
from lib.llm.adapters.openrouter_adapter import OpenRouterAdapter


class _Router:
    def __init__(self, *, model_list, set_verbose, **kwargs):
        self.model_list = model_list
        self.set_verbose = set_verbose
        self.kwargs = kwargs


class _BaseAdapterUnderTest(BaseAdapter):
    def __init__(self, *, redis, request=None):
        super().__init__(provider_name="groq", redis=redis, request=request)


async def _redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _request(provider_pref: str | None = None):
    return SimpleNamespace(
        state=SimpleNamespace(
            request_id="12345678-1234-1234-1234-123456789abc",
            audit_context={"request_meta": {"provider_pref": provider_pref}},
        )
    )


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


@pytest.mark.asyncio
async def test_base_adapter_uses_shorter_timeout_for_automatic_provider() -> None:
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=_request())

    assert adapter._attempt_timeout_seconds() == 5


@pytest.mark.asyncio
async def test_base_adapter_uses_longer_timeout_for_forced_provider() -> None:
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=_request("groq"))

    assert adapter._attempt_timeout_seconds() == 10


@pytest.mark.asyncio
async def test_base_adapter_raises_litellm_timeout_on_operation_timeout() -> None:
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=_request())

    async def _operation():
        await __import__("asyncio").sleep(0)

    async def _timeout(coro, *args, **kwargs):
        coro.close()
        raise TimeoutError

    import lib.llm.adapters.base_adapter as base_adapter_module

    original_wait_for = base_adapter_module.asyncio.wait_for
    base_adapter_module.asyncio.wait_for = _timeout
    try:
        with pytest.raises(Timeout) as exc_info:
            await adapter._call_with_retry(_operation, model="groq/llama-3.1-8b-instant")
        assert exc_info.value.status_code == 408
        assert exc_info.value.llm_provider == "groq"
    finally:
        base_adapter_module.asyncio.wait_for = original_wait_for
