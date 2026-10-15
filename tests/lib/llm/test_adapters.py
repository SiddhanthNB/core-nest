from __future__ import annotations

import time
from types import SimpleNamespace

import fakeredis.aioredis
import httpx
import pytest
from litellm import (
    AuthenticationError,
    BadRequestError,
    JSONSchemaValidationError,
    PermissionDeniedError,
    RateLimitError,
    ServiceUnavailableError,
)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from app.api.services._helpers import _validate_json_response_payload
from app.config.tracing import TRACER_NAME
from lib.llm.adapters import get_adapter
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


@pytest.fixture(autouse=True)
def _isolated_router_cache(monkeypatch) -> None:
    monkeypatch.setattr("lib.llm.adapters.base_adapter._ROUTERS", {})


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
    monkeypatch.setattr("lib.llm.adapters.base_adapter.Router", _Router)

    adapter = HuggingfaceAdapter(redis=await _redis())

    assert adapter._completion_router is not None
    assert adapter._embedding_router is None


@pytest.mark.asyncio
async def test_openrouter_adapter_builds_embedding_router(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("lib.llm.adapters.base_adapter.Router", _Router)

    adapter = OpenRouterAdapter(redis=await _redis())

    assert adapter._completion_router is not None
    assert adapter._embedding_router is not None


@pytest.mark.asyncio
async def test_groq_and_cerebras_remain_completion_only(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("CEREBRAS_API_KEY", "test-key")
    monkeypatch.setattr("lib.llm.adapters.base_adapter.Router", _Router)

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
    mocker.patch.object(adapter, "_wait_for_retry", return_value=0)

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


def _bad_request_error() -> BadRequestError:
    return BadRequestError(message="bad param", model="groq/test", llm_provider="groq")


@pytest.mark.asyncio
async def test_base_adapter_client_error_does_not_open_circuit(mocker) -> None:
    redis = await _redis()
    adapter = _BaseAdapterUnderTest(redis=redis, request=_request())
    adapter._completion_router = SimpleNamespace(acompletion=mocker.AsyncMock(side_effect=_bad_request_error()))

    for _ in range(5):
        with pytest.raises(BadRequestError):
            await adapter.acompletion(messages=[{"role": "user", "content": "hello"}], request_params={})

    assert adapter._completion_router.acompletion.await_count == 5
    assert not await adapter.is_circuit_open()
    assert not await redis.exists(f"core-nest:circuit:{adapter._provider_name}:failures")


@pytest.mark.asyncio
async def test_base_adapter_provider_error_opens_circuit(mocker) -> None:
    redis = await _redis()
    adapter = _BaseAdapterUnderTest(redis=redis, request=_request())
    error = ServiceUnavailableError(message="down", model="groq/test", llm_provider="groq")
    adapter._completion_router = SimpleNamespace(acompletion=mocker.AsyncMock(side_effect=error))
    mocker.patch.object(adapter, "_wait_for_retry", return_value=0)

    for _ in range(3):
        with pytest.raises(ServiceUnavailableError):
            await adapter.acompletion(messages=[{"role": "user", "content": "hello"}], request_params={})

    assert await adapter.is_circuit_open()


@pytest.mark.asyncio
async def test_get_adapter_reuses_router_across_requests(monkeypatch, mocker) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    router = mocker.patch("lib.llm.adapters.base_adapter.Router", side_effect=_Router)
    redis = await _redis()

    first = get_adapter("google", redis=redis, request=_request())
    second = get_adapter("google", redis=redis, request=_request())

    assert first is not second
    assert first._completion_router is second._completion_router
    assert first._embedding_router is second._embedding_router
    assert first._completion_router is not first._embedding_router
    assert router.call_count == 2


@pytest.mark.asyncio
async def test_router_drops_unsupported_params(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("lib.llm.adapters.base_adapter.Router", _Router)

    adapter = OpenRouterAdapter(redis=await _redis())

    for router in (adapter._completion_router, adapter._embedding_router):
        assert [model["litellm_params"]["drop_params"] for model in router.model_list] == [True]
        assert router.kwargs["num_retries"] == 0
        assert router.kwargs["disable_cooldowns"] is True
        assert "additional_drop_params" not in router.model_list[0]["litellm_params"]


@pytest.mark.asyncio
async def test_google_completion_router_drops_penalties(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("lib.llm.adapters.base_adapter.Router", _Router)

    adapter = get_adapter("google", redis=await _redis())

    assert adapter._completion_router.model_list[0]["litellm_params"]["additional_drop_params"] == ["presence_penalty", "frequency_penalty"]  # fmt: skip
    assert "additional_drop_params" not in adapter._embedding_router.model_list[0]["litellm_params"]


def _retry_state(exc: Exception, *, attempt_number: int = 1):
    return SimpleNamespace(outcome=SimpleNamespace(exception=lambda: exc), attempt_number=attempt_number, upcoming_sleep=0.0)  # fmt: skip


def _rate_limit_error(retry_after: str) -> RateLimitError:
    response = SimpleNamespace(headers={"Retry-After": retry_after})
    error = RateLimitError(message="slow down", model="groq/test", llm_provider="groq")
    error.response = response
    return error


@pytest.mark.asyncio
async def test_base_adapter_caps_retry_after() -> None:
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=_request())

    assert adapter._wait_for_retry(_retry_state(_rate_limit_error("3"))) == 3
    assert adapter._wait_for_retry(_retry_state(_rate_limit_error("120"))) == 10


@pytest.mark.asyncio
async def test_base_adapter_shrinks_timeout_and_wait_to_request_deadline() -> None:
    request = _request(provider_pref="groq")
    request.state.llm_deadline = time.monotonic() + 5
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=request, provider_preference="groq")

    assert 4 < adapter._request_timeout_seconds() <= 5
    assert 4 < adapter._wait_for_retry(_retry_state(_rate_limit_error("8"))) <= 5


@pytest.mark.asyncio
async def test_base_adapter_passes_remaining_deadline_as_attempt_timeout(mocker) -> None:
    request = _request()
    request.state.llm_deadline = time.monotonic() + 5
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=request)
    adapter._completion_router = SimpleNamespace(acompletion=mocker.AsyncMock(return_value={"choices": []}))

    await adapter.acompletion(messages=[{"role": "user", "content": "hello"}], request_params={})

    assert 4 < adapter._completion_router.acompletion.await_args.kwargs["timeout"] <= 5


@pytest.mark.asyncio
async def test_base_adapter_stops_retrying_when_deadline_exhausted(mocker) -> None:
    request = _request()
    request.state.llm_deadline = time.monotonic() + 0.05
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=request)
    adapter._completion_router = SimpleNamespace(acompletion=mocker.AsyncMock(side_effect=_rate_limit_error("8")))

    with pytest.raises(RateLimitError):
        await adapter.acompletion(messages=[{"role": "user", "content": "hello"}], request_params={})

    assert adapter._completion_router.acompletion.await_count == 1


@pytest.mark.asyncio
async def test_base_adapter_without_deadline_keeps_attempt_timeout() -> None:
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=_request())

    assert adapter._request_timeout_seconds() == 15


def _http_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        AuthenticationError(message="bad key", llm_provider="groq", model="groq/test"),
        PermissionDeniedError(
            message="forbidden", llm_provider="groq", model="groq/test", response=_http_response(403)
        ),
    ],
)
async def test_base_adapter_auth_error_opens_circuit_without_retry(mocker, error) -> None:
    redis = await _redis()
    adapter = _BaseAdapterUnderTest(redis=redis, request=_request())
    adapter._completion_router = SimpleNamespace(acompletion=mocker.AsyncMock(side_effect=error))
    wait = mocker.patch.object(adapter, "_wait_for_retry", return_value=0)

    for _ in range(3):
        with pytest.raises(type(error)):
            await adapter.acompletion(messages=[{"role": "user", "content": "hello"}], request_params={})

    assert adapter._completion_router.acompletion.await_count == 3
    wait.assert_not_called()
    assert await adapter.is_circuit_open()


@pytest.mark.asyncio
async def test_base_adapter_runs_each_retry_in_its_own_span(mocker) -> None:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    test_tracer = tracer_provider.get_tracer(TRACER_NAME)
    mocker.patch("lib.llm.adapters.base_adapter.tracer", test_tracer)
    adapter = _BaseAdapterUnderTest(redis=await _redis(), request=_request())
    active_span_ids: list[int] = []
    error = ServiceUnavailableError(message="down", model="groq/test", llm_provider="groq")

    async def _acompletion(**kwargs):
        active_span_ids.append(trace.get_current_span().get_span_context().span_id)
        if len(active_span_ids) < 3:
            raise error
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

    adapter._completion_router = SimpleNamespace(acompletion=_acompletion)
    mocker.patch.object(adapter, "_wait_for_retry", return_value=0)
    warning_span_ids: list[int] = []
    mocker.patch("lib.llm.adapters.base_adapter.logger.warning", side_effect=lambda *args, **kwargs: warning_span_ids.append(trace.get_current_span().get_span_context().span_id))  # fmt: skip

    with test_tracer.start_as_current_span("chat groq/test") as provider_span:
        await adapter.acompletion(messages=[{"role": "user", "content": "hello"}], request_params={})

    attempts = [span for span in exporter.get_finished_spans() if span.name.startswith("attempt ")]
    assert [span.name for span in attempts] == ["attempt 1 groq", "attempt 2 groq", "attempt 3 groq"]
    assert active_span_ids == [span.context.span_id for span in attempts]
    assert warning_span_ids == [span.context.span_id for span in attempts[:2]]
    assert {span.parent.span_id for span in attempts} == {provider_span.get_span_context().span_id}
    expected = [(1, "failed", "ServiceUnavailableError"), (2, "failed", "ServiceUnavailableError"), (3, "succeeded", None)]  # fmt: skip
    assert [(span.attributes["retry.attempt"], span.attributes["outcome"], span.attributes.get("error.type")) for span in attempts] == expected  # fmt: skip
    assert {(span.attributes["gen_ai.provider.name"], span.attributes["gen_ai.request.model"]) for span in attempts} == {("groq", adapter._completion_model)}  # fmt: skip
    assert [span.status.status_code for span in attempts] == [StatusCode.ERROR, StatusCode.ERROR, StatusCode.OK]


@pytest.mark.asyncio
async def test_reset_circuit_is_one_command_and_reports_prior_state(mocker) -> None:
    redis = await _redis()
    adapter = _BaseAdapterUnderTest(redis=redis, request=_request())
    exists = mocker.spy(redis, "exists")

    assert await adapter._reset_circuit() is False
    await redis.set(adapter._circuit_key("failures"), "2")
    assert await adapter._reset_circuit() is True

    assert exists.call_count == 0
    assert not await redis.exists(adapter._circuit_key("failures"))
