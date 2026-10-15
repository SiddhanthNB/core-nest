from __future__ import annotations

from functools import partial
from types import SimpleNamespace

import fakeredis.aioredis
import httpx
import litellm
import pytest
import respx
from fastapi import HTTPException
from litellm import AuthenticationError, BadRequestError
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from tenacity import AsyncRetrying

from app.api.services.base import BaseService
from app.config.tracing import TRACER_NAME
from lib.llm.adapters import get_adapter

# end-to-end through Router -> litellm -> httpx; only the provider HTTP endpoints are mocked
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
_MESSAGES = [{"role": "user", "content": "hello"}]


def _chat_body(content: str, *, model: str) -> dict:
    return {"id": "chatcmpl-test", "object": "chat.completion", "created": 1, "model": model, "service_tier": "on_demand", "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}  # fmt: skip


def _error_body(message: str) -> dict:
    return {"error": {"message": message, "type": "test_error"}}


@pytest.fixture(autouse=True)
def _httpx_transport(monkeypatch):
    # litellm defaults to its aiohttp transport, which respx cannot intercept; tests switch to httpx only
    monkeypatch.setattr(litellm, "disable_aiohttp_transport", True)
    monkeypatch.setattr("lib.llm.adapters.base_adapter._ROUTERS", {})
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key")
    litellm.in_memory_llm_clients_cache.flush_cache()
    yield
    litellm.in_memory_llm_clients_cache.flush_cache()


@pytest.fixture
def sleeps(mocker) -> list[float]:
    recorded: list[float] = []

    async def _sleep(seconds: float) -> None:
        recorded.append(seconds)

    mocker.patch("lib.llm.adapters.base_adapter.AsyncRetrying", partial(AsyncRetrying, sleep=_sleep))
    return recorded


@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def provider_api():
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


def _request():
    return SimpleNamespace(headers={}, state=SimpleNamespace(audit_context={"request_meta": {}}))


@pytest.mark.asyncio
async def test_adapter_completion_success_over_http(redis, provider_api) -> None:
    route = provider_api.post(_GROQ_URL).mock(return_value=httpx.Response(200, json=_chat_body("hi there", model="openai/gpt-oss-20b")))  # fmt: skip
    adapter = get_adapter("groq", redis=redis, request=_request())

    result = await adapter.acompletion(messages=_MESSAGES, request_params={})

    assert result.choices[0].message.content == "hi there"
    assert route.call_count == 1
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer test-groq-key"
    assert b'"hello"' in sent.content


def _rate_limited_then_ok():
    return [httpx.Response(429, headers={"Retry-After": "2"}, json=_error_body("slow down")), httpx.Response(200, json=_chat_body("after retry", model="openai/gpt-oss-20b"))]  # fmt: skip


@pytest.mark.asyncio
async def test_adapter_retries_429_then_succeeds(redis, provider_api, sleeps) -> None:
    route = provider_api.post(_GROQ_URL).mock(side_effect=_rate_limited_then_ok())
    adapter = get_adapter("groq", redis=redis, request=_request())

    result = await adapter.acompletion(messages=_MESSAGES, request_params={})

    assert result.choices[0].message.content == "after retry"
    assert route.call_count == 2
    assert len(sleeps) == 1
    assert not await redis.exists("core-nest:circuit:groq:failures")


@pytest.mark.asyncio
async def test_adapter_429_waits_for_retry_after_header(redis, provider_api, sleeps) -> None:
    provider_api.post(_GROQ_URL).mock(side_effect=_rate_limited_then_ok())
    adapter = get_adapter("groq", redis=redis, request=_request())

    await adapter.acompletion(messages=_MESSAGES, request_params={})

    assert sleeps == [2.0]


@pytest.mark.asyncio
async def test_adapter_400_does_not_retry_or_open_circuit(redis, provider_api, sleeps) -> None:
    route = provider_api.post(_GROQ_URL).mock(return_value=httpx.Response(400, json=_error_body("bad param")))
    adapter = get_adapter("groq", redis=redis, request=_request())

    for _ in range(5):
        with pytest.raises(BadRequestError):
            await adapter.acompletion(messages=_MESSAGES, request_params={})

    assert route.call_count == 5
    assert sleeps == []
    assert not await adapter.is_circuit_open()
    assert not await redis.exists("core-nest:circuit:groq:failures")


@pytest.mark.asyncio
async def test_adapter_attempt_warning_includes_provider_message(redis, provider_api, sleeps, caplog) -> None:
    provider_api.post(_GROQ_URL).mock(return_value=httpx.Response(400, json=_error_body("Failed to generate JSON")))
    adapter = get_adapter("groq", redis=redis, request=_request())

    with pytest.raises(BadRequestError):
        await adapter.acompletion(messages=_MESSAGES, request_params={})

    warnings = [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]
    assert warnings == ["[attempt: 1] provider 'groq' attempt failed: BadRequestError 400: Failed to generate JSON"]


@pytest.mark.asyncio
async def test_service_falls_back_to_next_provider_on_5xx(mocker, redis, provider_api, sleeps) -> None:
    mocker.patch("app.api.services.base.redis_client", redis)
    mocker.patch("app.api.services._helpers.constants.COMPLETION_PROVIDERS", ("groq", "mistral"))
    groq = provider_api.post(_GROQ_URL).mock(return_value=httpx.Response(503, json=_error_body("overloaded")))
    mistral = provider_api.post(_MISTRAL_URL).mock(return_value=httpx.Response(200, json=_chat_body("from mistral", model="ministral-8b-2410")))  # fmt: skip
    request = _request()

    payload = await BaseService()._fetch_completion(messages=_MESSAGES, request_params={}, provider_preference=None, request=request)  # fmt: skip

    assert payload["choices"][0]["message"]["content"] == "from mistral"
    assert groq.call_count == 3
    assert mistral.call_count == 1
    assert len(sleeps) == 2
    attempts = request.state.audit_context["response_meta"]["provider_attempts"]
    assert [(attempt["provider"], attempt["status"]) for attempt in attempts] == [("groq", "failed"), ("mistral", "succeeded")]  # fmt: skip
    assert attempts[0]["error"] == "ServiceUnavailableError"
    assert await redis.get("core-nest:circuit:groq:failures") == "1"
    assert not await redis.exists("core-nest:circuit:mistral:failures")


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_status, provider_headers, expected_status, expected_retry_after", [(429, {"Retry-After": "7"}, 429, "7"), (429, {}, 429, None), (503, {}, 503, None)])  # fmt: skip
async def test_requested_provider_failure_maps_to_client_status(mocker, redis, provider_api, sleeps, provider_status, provider_headers, expected_status, expected_retry_after) -> None:  # fmt: skip
    mocker.patch("app.api.services.base.redis_client", redis)
    provider_api.post(_GROQ_URL).mock(return_value=httpx.Response(provider_status, headers=provider_headers, json=_error_body("busy")))  # fmt: skip

    with pytest.raises(HTTPException) as raised:
        await BaseService()._fetch_completion(messages=_MESSAGES, request_params={}, provider_preference="groq", request=_request())  # fmt: skip

    assert raised.value.status_code == expected_status
    assert (raised.value.headers or {}).get("Retry-After") == expected_retry_after


@pytest.mark.asyncio
async def test_adapter_401_counts_toward_circuit_without_retrying(redis, provider_api, sleeps) -> None:
    route = provider_api.post(_GROQ_URL).mock(return_value=httpx.Response(401, json=_error_body("invalid api key")))
    adapter = get_adapter("groq", redis=redis, request=_request())

    with pytest.raises(AuthenticationError):
        await adapter.acompletion(messages=_MESSAGES, request_params={})

    assert route.call_count == 1
    assert sleeps == []
    assert await redis.get("core-nest:circuit:groq:failures") == "1"


@pytest.mark.asyncio
async def test_service_fallback_records_retry_spans_under_provider_spans(mocker, redis, provider_api, sleeps) -> None:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    test_tracer = tracer_provider.get_tracer(TRACER_NAME)
    mocker.patch("app.api.services.base.tracer", test_tracer)
    mocker.patch("lib.llm.adapters.base_adapter.tracer", test_tracer)
    mocker.patch("app.api.services.base.redis_client", redis)
    mocker.patch("app.api.services._helpers.constants.COMPLETION_PROVIDERS", ("groq", "mistral"))
    provider_api.post(_GROQ_URL).mock(return_value=httpx.Response(503, json=_error_body("overloaded")))
    provider_api.post(_MISTRAL_URL).mock(return_value=httpx.Response(200, json=_chat_body("from mistral", model="ministral-8b-2410")))  # fmt: skip

    await BaseService()._fetch_completion(messages=_MESSAGES, request_params={}, provider_preference=None, request=_request())  # fmt: skip

    spans = exporter.get_finished_spans()
    by_name = {span.name: span for span in spans}
    groq_span = next(span for span in spans if span.name.startswith("chat ") and span.attributes["gen_ai.provider.name"] == "groq")  # fmt: skip
    mistral_span = next(span for span in spans if span.name.startswith("chat ") and span.attributes["gen_ai.provider.name"] == "mistral")  # fmt: skip
    groq_attempts = [by_name[f"attempt {n} groq"] for n in (1, 2, 3)]
    mistral_attempt = by_name["attempt 1 mistral"]

    assert {span.parent.span_id for span in groq_attempts} == {groq_span.context.span_id}
    assert len({span.context.span_id for span in groq_attempts}) == 3
    assert [span.attributes["retry.attempt"] for span in groq_attempts] == [1, 2, 3]
    assert {(span.attributes["outcome"], span.attributes["error.type"]) for span in groq_attempts} == {("failed", "ServiceUnavailableError")}  # fmt: skip
    assert {span.status.status_code for span in groq_attempts} == {StatusCode.ERROR}
    assert mistral_attempt.parent.span_id == mistral_span.context.span_id
    assert mistral_attempt.attributes["outcome"] == "succeeded"
    assert mistral_attempt.attributes["gen_ai.request.model"] == mistral_span.attributes["gen_ai.request.model"]
