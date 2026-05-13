from __future__ import annotations

from types import SimpleNamespace

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from litellm import UnsupportedParamsError
from litellm.types.utils import Usage
from redis.exceptions import RedisError

from app.api.services._helpers import _ordered_completion_providers, _response_meta
from app.api.services.completion_service import CompletionService
from app.api.services.embeddings_service import EmbeddingsService
from app.api.services.sentiment_service import SentimentService
from app.api.services.summarization_service import SummarizationService
from app.api.validators.completions import Completions
from app.api.validators.embeddings import Embeddings
from app.api.validators.sentiments import Sentiments
from app.api.validators.summarization import Summarization


def _request():
    return SimpleNamespace(state=SimpleNamespace(audit_context={}))


def _completion_adapter(*, provider: str, model: str, mocker, redis=None, payload=None):
    async def _is_circuit_open() -> bool:
        if redis is None:
            return False
        return bool(await redis.exists(f"circuit:{provider}:open"))

    async def _acompletion(*, messages, request_params):
        return payload or {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        }

    return type(
        "_Adapter",
        (),
        {
            "_provider_name": provider,
            "_completion_model": model,
            "is_circuit_open": staticmethod(mocker.AsyncMock(side_effect=_is_circuit_open)),
            "acompletion": staticmethod(mocker.AsyncMock(side_effect=_acompletion)),
        },
    )()


@pytest.mark.asyncio
async def test_sentiments_service_enforces_locked_execution_policy(mocker) -> None:
    service = SentimentService()
    mocker.patch.object(
        service,
        "_get_system_prompt",
        return_value="system sentiment prompt",
    )
    dispatch = mocker.patch.object(service, "_fetch_completion", new=mocker.AsyncMock(return_value={"ok": True}))

    result = await service.dispatch(
        Sentiments(messages=[{"role": "user", "content": "great product"}]),
        provider_preference="google",
    )

    assert result == {"ok": True}
    dispatch.assert_awaited_once_with(
        messages=[
            {"role": "system", "content": "system sentiment prompt"},
            {"role": "user", "content": "great product"},
        ],
        request_params={
            "temperature": 0,
            "tools": None,
            "tool_choice": None,
            "stream": False,
            "stream_options": None,
            "response_format": {"type": "json_object"},
        },
        provider_preference="google",
        request=None,
    )


@pytest.mark.asyncio
async def test_summarization_service_enforces_locked_execution_policy(mocker) -> None:
    service = SummarizationService()
    mocker.patch.object(
        service,
        "_get_system_prompt",
        return_value="system summary prompt",
    )
    dispatch = mocker.patch.object(service, "_fetch_completion", new=mocker.AsyncMock(return_value={"ok": True}))

    result = await service.dispatch(
        Summarization(messages=[{"role": "user", "content": "long text"}]),
        provider_preference="openai",
    )

    assert result == {"ok": True}
    dispatch.assert_awaited_once_with(
        messages=[
            {"role": "system", "content": "system summary prompt"},
            {"role": "user", "content": "long text"},
        ],
        request_params={
            "temperature": 0,
            "tools": None,
            "tool_choice": None,
            "stream": False,
            "stream_options": None,
            "response_format": None,
        },
        provider_preference="openai",
        request=None,
    )


@pytest.mark.asyncio
async def test_embeddings_service_keeps_embedding_specific_policy(mocker) -> None:
    service = EmbeddingsService()
    dispatch = mocker.patch.object(service, "_fetch_embedding", new=mocker.AsyncMock(return_value={"ok": True}))

    result = await service.dispatch(Embeddings.model_validate({"input": ["hello"]}), provider_preference="openai")

    assert result == {"ok": True}
    dispatch.assert_awaited_once_with(
        input_data=["hello"],
        request_params={},
        provider_preference="openai",
        request=None,
    )


def test_base_service_completion_request_params_force_stream_off() -> None:
    params = Completions(messages=[{"role": "user", "content": "hello"}], temperature=0.7, max_tokens=42, top_p=0.9)

    request_params = CompletionService()._request_params(params)

    assert request_params["stream"] is False
    assert request_params["stream_options"] is None


def test_completion_service_request_params_are_dumped_from_model_without_internal_fields() -> None:
    params = Completions(
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.7,
        max_tokens=42,
        response_format={"type": "json_object"},
    )

    request_params = CompletionService()._request_params(params)

    assert request_params == {
        "temperature": 0.7,
        "max_completion_tokens": None,
        "max_tokens": 42,
        "top_p": None,
        "n": None,
        "presence_penalty": None,
        "frequency_penalty": None,
        "stop": None,
        "functions": None,
        "function_call": None,
        "logit_bias": None,
        "user": None,
        "tools": None,
        "tool_choice": None,
        "response_format": {"type": "json_object"},
        "seed": None,
        "logprobs": None,
        "top_logprobs": None,
        "extra_headers": None,
        "stream": False,
        "stream_options": None,
    }
    assert "messages" not in request_params
    assert "model" not in request_params
    assert "provider" not in request_params


def test_sentiment_service_request_params_are_dumped_from_model_without_internal_fields() -> None:
    params = Sentiments(messages=[{"role": "user", "content": "great product"}])

    request_params = SentimentService()._request_params(params)

    assert request_params == {
        "temperature": 0,
        "tools": None,
        "tool_choice": None,
        "stream": False,
        "stream_options": None,
        "response_format": {"type": "json_object"},
    }
    assert "messages" not in request_params
    assert "model" not in request_params
    assert "provider" not in request_params


def test_summarization_service_request_params_are_dumped_from_model_without_internal_fields() -> None:
    params = Summarization(messages=[{"role": "user", "content": "long text"}])

    request_params = SummarizationService()._request_params(params)

    assert request_params == {
        "temperature": 0,
        "tools": None,
        "tool_choice": None,
        "stream": False,
        "stream_options": None,
        "response_format": None,
    }
    assert "messages" not in request_params
    assert "model" not in request_params
    assert "provider" not in request_params


def test_embeddings_service_request_params_dump_is_empty() -> None:
    params = Embeddings.model_validate({"input": ["hello"]})

    request_params = EmbeddingsService()._request_params(params)

    assert request_params == {}
    assert "input" not in request_params
    assert "model" not in request_params


def test_completions_validator_applies_api_managed_defaults() -> None:
    params = Completions(messages=[{"role": "user", "content": "hello"}])

    assert params.model is None
    assert params.provider is None
    assert params.stream is False
    assert params.stream_options is None


def test_summarization_validator_applies_api_managed_defaults() -> None:
    params = Summarization(messages=[{"role": "user", "content": "long text"}])

    assert params.model is None
    assert params.provider is None
    assert params.temperature == 0
    assert params.tools is None
    assert params.tool_choice is None
    assert params.stream is False
    assert params.stream_options is None
    assert params.response_format is None


def test_base_service_response_meta_normalizes_litellm_usage() -> None:
    response_meta = _response_meta(
        [{"provider": "mistral", "model": "mistral/ministral-8b-2410", "status": "succeeded"}],
        payload={
            "choices": [{"finish_reason": "stop"}],
            "usage": Usage(prompt_tokens=10, completion_tokens=4, total_tokens=14),
        },
    )

    assert response_meta == {
        "provider_attempts": [{"provider": "mistral", "model": "mistral/ministral-8b-2410", "status": "succeeded"}],
        "attempt_count": 1,
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }


@pytest.mark.asyncio
async def test_completion_service_falls_back_on_invalid_json_when_json_requested(mocker) -> None:
    service = CompletionService()
    request = _request()
    mocker.patch("app.api.services.base_service.redis_client", object())
    mocker.patch(
        "app.api.services.base_service.get_adapter",
        side_effect=[
            type(
                "_Adapter",
                (),
                {
                    "_provider_name": "mistral",
                    "_completion_model": "mistral/ministral-8b-2410",
                    "is_circuit_open": staticmethod(mocker.AsyncMock(return_value=False)),
                    "acompletion": staticmethod(
                        mocker.AsyncMock(
                            return_value={"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]}
                        )
                    ),
                },
            )(),
            type(
                "_Adapter",
                (),
                {
                    "_provider_name": "google",
                    "_completion_model": "gemini/gemini-2.5-flash-lite",
                    "is_circuit_open": staticmethod(mocker.AsyncMock(return_value=False)),
                    "acompletion": staticmethod(
                        mocker.AsyncMock(
                            return_value={
                                "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]
                            }
                        )
                    ),
                },
            )(),
        ],
    )

    result = await service.dispatch(
        Completions(
            messages=[{"role": "user", "content": "hello"}],
            response_format={"type": "json_object"},
        ),
        request=request,
    )

    assert result["choices"][0]["message"]["content"] == '{"ok": true}'
    assert request.state.audit_context["response_meta"] == {
        "provider_attempts": [
            {
                "provider": "mistral",
                "model": "mistral/ministral-8b-2410",
                "status": "failed",
                "error": "JSONSchemaValidationError",
            },
            {
                "provider": "google",
                "model": "gemini/gemini-2.5-flash-lite",
                "status": "succeeded",
            },
        ],
        "attempt_count": 2,
        "finish_reason": "stop",
    }


@pytest.mark.asyncio
async def test_sentiment_service_rejects_invalid_json_from_forced_provider(mocker) -> None:
    service = SentimentService()
    request = _request()
    mocker.patch.object(service, "_get_system_prompt", return_value="system sentiment prompt")
    mocker.patch("app.api.services.base_service.redis_client", object())
    mocker.patch(
        "app.api.services.base_service.get_adapter",
        return_value=type(
            "_Adapter",
            (),
            {
                "_provider_name": "google",
                "_completion_model": "gemini/gemini-2.5-flash-lite",
                "is_circuit_open": staticmethod(mocker.AsyncMock(return_value=False)),
                "acompletion": staticmethod(
                    mocker.AsyncMock(
                        return_value={"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]}
                    )
                ),
            },
        )(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.dispatch(
            Sentiments(messages=[{"role": "user", "content": "great product"}]),
            provider_preference="google",
            request=request,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Provider 'google' returned invalid JSON"
    assert request.state.audit_context["response_meta"] == {
        "provider_attempts": [
            {
                "provider": "google",
                "model": "gemini/gemini-2.5-flash-lite",
                "status": "failed",
                "error": "JSONSchemaValidationError",
            }
        ],
        "attempt_count": 1,
    }


@pytest.mark.asyncio
async def test_completion_service_surfaces_litellm_param_errors(mocker) -> None:
    service = CompletionService()
    mocker.patch("app.api.services.base_service.redis_client", object())
    mocker.patch(
        "app.api.services._helpers.get_supported_openai_params",
        return_value=["messages", "temperature", "top_p"],
    )
    mocker.patch(
        "app.api.services.base_service.get_adapter",
        return_value=type(
            "_Adapter",
            (),
            {
                "_provider_name": "mistral",
                "_completion_model": "mistral/ministral-8b-2410",
                "is_circuit_open": staticmethod(mocker.AsyncMock(return_value=False)),
                "acompletion": staticmethod(
                    mocker.AsyncMock(
                        side_effect=UnsupportedParamsError(
                            message="unsupported params",
                            llm_provider="mistral",
                            model="mistral/ministral-8b-2410",
                        )
                    )
                ),
            },
        )(),
    )

    with pytest.raises(Exception) as exc_info:
        await service.dispatch(
            Completions(messages=[{"role": "user", "content": "hello"}]), provider_preference="mistral"
        )

    assert getattr(exc_info.value, "status_code", None) == 400
    assert "Supported params" in str(getattr(exc_info.value, "detail", exc_info.value))


@pytest.mark.asyncio
async def test_completion_service_forced_provider_circuit_open_records_skipped_attempt(mocker) -> None:
    service = CompletionService()
    request = _request()
    mocker.patch("app.api.services.base_service.redis_client", object())
    mocker.patch(
        "app.api.services.base_service.get_adapter",
        return_value=type(
            "_Adapter",
            (),
            {
                "_provider_name": "mistral",
                "_completion_model": "mistral/ministral-8b-2410",
                "is_circuit_open": staticmethod(mocker.AsyncMock(return_value=True)),
            },
        )(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.dispatch(
            Completions(messages=[{"role": "user", "content": "hello"}]),
            provider_preference="mistral",
            request=request,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Provider 'mistral' circuit is open"
    assert request.state.audit_context["response_meta"] == {
        "provider_attempts": [
            {
                "provider": "mistral",
                "model": "mistral/ministral-8b-2410",
                "status": "skipped",
                "reason": "circuit_open",
            }
        ],
        "attempt_count": 0,
    }


@pytest.mark.asyncio
async def test_completion_service_round_robin_rotates_start_provider_with_fakeredis(mocker) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch(
        "app.api.services._helpers.constants.COMPLETION_PROVIDERS", ("groq", "google", "openrouter", "mistral")
    )

    assert await _ordered_completion_providers(None, redis_client=fake_redis) == [
        "groq",
        "google",
        "openrouter",
        "mistral",
    ]
    assert await _ordered_completion_providers(None, redis_client=fake_redis) == [
        "google",
        "openrouter",
        "mistral",
        "groq",
    ]
    assert await _ordered_completion_providers(None, redis_client=fake_redis) == [
        "openrouter",
        "mistral",
        "groq",
        "google",
    ]


@pytest.mark.asyncio
async def test_completion_service_forced_provider_bypasses_round_robin_counter(mocker) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch(
        "app.api.services._helpers.constants.COMPLETION_PROVIDERS", ("groq", "google", "openrouter", "mistral")
    )

    assert await _ordered_completion_providers("google", redis_client=fake_redis) == ["google"]
    assert await fake_redis.get("llm:routing:completion:rr_counter") is None


@pytest.mark.asyncio
async def test_completion_service_round_robin_falls_back_to_static_order_when_redis_fails(mocker) -> None:
    mocker.patch(
        "app.api.services._helpers.constants.COMPLETION_PROVIDERS", ("groq", "google", "openrouter", "mistral")
    )

    assert await _ordered_completion_providers(
        None,
        redis_client=SimpleNamespace(incr=mocker.AsyncMock(side_effect=RedisError("boom"))),
    ) == ["groq", "google", "openrouter", "mistral"]


@pytest.mark.asyncio
async def test_completion_service_round_robin_respects_circuit_open_and_falls_forward(mocker) -> None:
    service = CompletionService()
    request = _request()
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await fake_redis.set("llm:routing:completion:rr_counter", "1")
    await fake_redis.set("circuit:google:open", "open")
    mocker.patch("app.api.services.base_service.redis_client", fake_redis)
    mocker.patch("app.api.services.base_service.constants.COMPLETION_PROVIDERS", ("mistral", "google", "openrouter"))

    def _get_adapter(provider_name, *, redis, request=None):
        adapters = {
            "google": _completion_adapter(
                provider="google",
                model="gemini/gemini-2.5-flash-lite",
                mocker=mocker,
                redis=redis,
            ),
            "openrouter": _completion_adapter(
                provider="openrouter",
                model="openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
                mocker=mocker,
                redis=redis,
                payload={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
            ),
            "mistral": _completion_adapter(
                provider="mistral",
                model="mistral/ministral-8b-2410",
                mocker=mocker,
                redis=redis,
            ),
        }
        return adapters[provider_name]

    mocker.patch("app.api.services.base_service.get_adapter", side_effect=_get_adapter)

    result = await service.dispatch(
        Completions(messages=[{"role": "user", "content": "hello"}]),
        request=request,
    )

    assert result["choices"][0]["finish_reason"] == "stop"
    assert request.state.audit_context["response_meta"] == {
        "provider_attempts": [
            {
                "provider": "google",
                "model": "gemini/gemini-2.5-flash-lite",
                "status": "skipped",
                "reason": "circuit_open",
            },
            {
                "provider": "openrouter",
                "model": "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
                "status": "succeeded",
            },
        ],
        "attempt_count": 1,
        "finish_reason": "stop",
    }


@pytest.mark.asyncio
async def test_embeddings_service_surfaces_litellm_param_errors(mocker) -> None:
    service = EmbeddingsService()
    request = _request()
    mocker.patch("app.api.services.base_service.redis_client", object())
    mocker.patch(
        "app.api.services._helpers.get_supported_openai_params",
        return_value=["dimensions", "encoding_format", "input"],
    )
    mocker.patch(
        "app.api.services.base_service.get_adapter",
        return_value=type(
            "_Adapter",
            (),
            {
                "_provider_name": "openrouter",
                "_embedding_model": "openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free",
                "is_circuit_open": staticmethod(mocker.AsyncMock(return_value=False)),
                "aembedding": staticmethod(
                    mocker.AsyncMock(
                        side_effect=UnsupportedParamsError(
                            message="unsupported params",
                            llm_provider="openrouter",
                            model="openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free",
                        )
                    )
                ),
            },
        )(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.dispatch(
            Embeddings.model_validate({"input": ["hello"]}),
            provider_preference="openrouter",
            request=request,
        )

    assert exc_info.value.status_code == 400
    assert "Supported params" in str(exc_info.value.detail)
    assert request.state.audit_context["response_meta"] == {
        "provider_attempts": [
            {
                "provider": "openrouter",
                "model": "openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free",
                "status": "failed",
                "error": "UnsupportedParamsError",
            }
        ],
        "attempt_count": 1,
    }
