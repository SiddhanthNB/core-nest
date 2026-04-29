from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from litellm import UnsupportedParamsError

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


@pytest.mark.asyncio
async def test_completion_service_surfaces_litellm_param_errors(mocker) -> None:
    service = CompletionService()
    mocker.patch("app.api.services.base_service.redis_client", object())
    mocker.patch(
        "app.api.services.base_service.get_supported_openai_params",
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
        await service.dispatch(Completions(messages=[{"role": "user", "content": "hello"}]), provider_preference="mistral")

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
async def test_embeddings_service_surfaces_litellm_param_errors(mocker) -> None:
    service = EmbeddingsService()
    request = _request()
    mocker.patch("app.api.services.base_service.redis_client", object())
    mocker.patch(
        "app.api.services.base_service.get_supported_openai_params",
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
