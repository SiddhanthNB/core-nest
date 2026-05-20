from __future__ import annotations

from types import SimpleNamespace

import fakeredis.aioredis
import pytest
from litellm import JSONSchemaValidationError

from app.api.services._helpers import _validate_json_response_payload
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
    def __init__(self, *, redis, request=None, provider_preference=None):
        super().__init__(
            provider_name="groq",
            redis=redis,
            request=request,
            provider_preference=provider_preference,
        )


async def _redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _request(provider_pref: str | None = None, timeout: str | None = None):
    return SimpleNamespace(
        headers={"X-LLM-Timeout": timeout} if timeout is not None else {},
        state=SimpleNamespace(
            request_id="12345678-1234-1234-1234-123456789abc",
            audit_context={"request_meta": {"provider_pref": provider_pref}},
        ),
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

    assert adapter._attempt_timeout_seconds() == 15


@pytest.mark.asyncio
async def test_base_adapter_uses_longer_timeout_for_forced_provider() -> None:
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=_request(), provider_preference="groq")

    assert adapter._attempt_timeout_seconds() == 30


@pytest.mark.asyncio
async def test_base_adapter_honors_timeout_header_override() -> None:
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=_request(timeout="45"))

    assert adapter._attempt_timeout_seconds() == 45


@pytest.mark.asyncio
async def test_base_adapter_clamps_timeout_header_override() -> None:
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=_request(timeout="120"))

    assert adapter._attempt_timeout_seconds() == 60


@pytest.mark.asyncio
async def test_base_adapter_ignores_invalid_timeout_header_override() -> None:
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=_request(timeout="invalid"))

    assert adapter._attempt_timeout_seconds() == 15


@pytest.mark.asyncio
async def test_base_adapter_retries_same_provider_on_invalid_json_response(mocker) -> None:
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=_request())
    adapter._completion_router = SimpleNamespace(
        acompletion=mocker.AsyncMock(
            return_value={"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]}
        )
    )

    with pytest.raises(JSONSchemaValidationError):
        await adapter.acompletion(
            messages=[{"role": "user", "content": "hello"}],
            request_params={"response_format": {"type": "json_object"}},
            response_validator=lambda payload: _validate_json_response_payload(
                payload,
                provider=adapter._provider_name,
                model=adapter._completion_model,
                response_format={"type": "json_object"},
            ),
        )

    assert adapter._completion_router.acompletion.await_count == 3
