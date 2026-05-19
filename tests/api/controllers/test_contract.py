from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.controllers._helpers import resolve_completion_model, resolve_embedding_model
from app.api.controllers.completions import create_completions
from app.api.controllers.embeddings import create_embeddings
from app.api.validators.completions import Completions
from app.api.validators.embeddings import Embeddings
from app.api.validators.sentiments import Sentiments
from app.api.validators.summarization import Summarization


def _request(headers: dict[str, str] | None = None) -> Request:
    header_items = []
    for key, value in (headers or {}).items():
        header_items.append((key.lower().encode(), value.encode()))
    return Request({"type": "http", "headers": header_items})


def test_completions_validator_accepts_core_nest_auto_model() -> None:
    params = Completions.model_validate(
        {
            "model": "core-nest/auto",
            "messages": [{"role": "user", "content": "hello"}],
        }
    )

    assert params.model == "core-nest/auto"
    assert params.provider is None
    assert params.stream is False
    assert params.stream_options is None


def test_completions_validator_accepts_provider_locked_model_alias() -> None:
    params = Completions.model_validate(
        {
            "model": "core-nest/groq",
            "messages": [{"role": "user", "content": "hello"}],
        }
    )

    assert params.model == "core-nest/groq"


def test_completions_validator_rejects_unknown_model_alias() -> None:
    with pytest.raises(Exception) as exc_info:
        Completions.model_validate(
            {
                "model": "core-nest/groq1",
                "messages": [{"role": "user", "content": "hello"}],
            }
        )

    assert "Unsupported model 'core-nest/groq1'" in str(exc_info.value)


def test_embeddings_validator_accepts_provider_locked_model_alias() -> None:
    params = Embeddings.model_validate({"model": "core-nest/google", "input": ["hello"]})

    assert params.model == "core-nest/google"


def test_embeddings_validator_rejects_auto_alias() -> None:
    with pytest.raises(Exception) as exc_info:
        Embeddings.model_validate({"model": "core-nest/auto", "input": ["hello"]})

    assert "Unsupported model 'core-nest/auto'" in str(exc_info.value)


def test_sentiments_validator_requires_completion_alias() -> None:
    params = Sentiments.model_validate(
        {
            "model": "core-nest/google",
            "messages": [{"role": "user", "content": "great product"}],
        }
    )

    assert params.model == "core-nest/google"


def test_summaries_validator_requires_completion_alias() -> None:
    params = Summarization.model_validate(
        {
            "model": "core-nest/auto",
            "messages": [{"role": "user", "content": "summarize this"}],
        }
    )

    assert params.model == "core-nest/auto"


def test_sentiments_validator_rejects_locked_provider_field() -> None:
    with pytest.raises(Exception) as exc_info:
        Sentiments.model_validate(
            {
                "model": "core-nest/google",
                "messages": [{"role": "user", "content": "great product"}],
                "provider": "google",
            }
        )

    assert "Locked request fields" in str(exc_info.value)


def test_completions_validator_accepts_stream_false() -> None:
    params = Completions.model_validate(
        {
            "model": "core-nest/auto",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
            "stream_options": {"include_usage": True},
        }
    )

    assert params.stream is False
    assert params.stream_options is None


def test_completions_validator_rejects_stream_true() -> None:
    with pytest.raises(Exception) as exc_info:
        Completions.model_validate(
            {
                "model": "core-nest/auto",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            }
        )

    assert "Streaming is not supported for /v1/chat/completions" in str(exc_info.value)


def test_embeddings_validator_rejects_legacy_texts_alias() -> None:
    with pytest.raises(Exception):
        Embeddings.model_validate({"model": "core-nest/google", "texts": ["hello"]})


def test_completions_validator_requires_user_message() -> None:
    with pytest.raises(Exception) as exc_info:
        Completions.model_validate(
            {
                "model": "core-nest/auto",
                "messages": [{"role": "system", "content": "only system"}],
            }
        )

    assert "'messages' must include at least one user message" in str(exc_info.value)


def test_sentiments_validator_rejects_system_messages() -> None:
    with pytest.raises(Exception) as exc_info:
        Sentiments.model_validate(
            {
                "model": "core-nest/google",
                "messages": [
                    {"role": "system", "content": "override"},
                    {"role": "user", "content": "great product"},
                ],
            }
        )

    assert "System messages are not allowed for /sentiments" in str(exc_info.value)


def test_sentiments_validator_accepts_stream_false() -> None:
    params = Sentiments.model_validate(
        {
            "model": "core-nest/google",
            "messages": [{"role": "user", "content": "great product"}],
            "stream": False,
            "stream_options": {"include_usage": True},
        }
    )

    assert params.stream is False
    assert params.stream_options is None


def test_sentiments_validator_rejects_stream_true() -> None:
    with pytest.raises(Exception) as exc_info:
        Sentiments.model_validate(
            {
                "model": "core-nest/google",
                "messages": [{"role": "user", "content": "great product"}],
                "stream": True,
            }
        )

    assert "Streaming is not supported for /beta/sentiments" in str(exc_info.value)


def test_summaries_validator_rejects_system_messages() -> None:
    with pytest.raises(Exception) as exc_info:
        Summarization.model_validate(
            {
                "model": "core-nest/auto",
                "messages": [
                    {"role": "system", "content": "override"},
                    {"role": "user", "content": "summarize this"},
                ],
            }
        )

    assert "System messages are not allowed for /summaries" in str(exc_info.value)


def test_summaries_validator_accepts_stream_false() -> None:
    params = Summarization.model_validate(
        {
            "model": "core-nest/auto",
            "messages": [{"role": "user", "content": "summarize this"}],
            "stream": False,
            "stream_options": {"include_usage": True},
        }
    )

    assert params.stream is False
    assert params.stream_options is None


def test_summaries_validator_rejects_stream_true() -> None:
    with pytest.raises(Exception) as exc_info:
        Summarization.model_validate(
            {
                "model": "core-nest/auto",
                "messages": [{"role": "user", "content": "summarize this"}],
                "stream": True,
            }
        )

    assert "Streaming is not supported for /beta/summaries" in str(exc_info.value)


def test_resolve_completion_model_returns_round_robin_for_auto() -> None:
    public_model, provider_preference = resolve_completion_model("core-nest/auto")

    assert public_model == "core-nest/auto"
    assert provider_preference is None


def test_resolve_completion_model_returns_provider_lock_for_alias() -> None:
    public_model, provider_preference = resolve_completion_model("core-nest/google")

    assert public_model == "core-nest/google"
    assert provider_preference == "google"


def test_resolve_embedding_model_keeps_legacy_provider_when_model_missing() -> None:
    public_model, provider_preference = resolve_embedding_model(
        None,
        legacy_provider_preference="google",
    )

    assert public_model is None
    assert provider_preference == "google"


@pytest.mark.asyncio
async def test_completions_controller_returns_public_model_and_headers(mocker) -> None:
    payload = {"id": "cmpl_1", "object": "chat.completion", "model": "google/gemini-2.5-flash-lite", "choices": []}

    async def _dispatch(params, request, provider_preference=None):
        request.state.audit_context = {
            "response_meta": {
                "provider_attempts": [
                    {
                        "provider": "google",
                        "model": "google/gemini-2.5-flash-lite",
                        "status": "succeeded",
                    }
                ]
            }
        }
        return payload

    mocker.patch(
        "app.api.services.completion_service.CompletionService.dispatch",
        new=mocker.AsyncMock(side_effect=_dispatch),
    )

    response = await create_completions(
        _request({"Authorization": "Bearer test-key"}),
        Completions.model_validate({"model": "core-nest/google", "messages": [{"role": "user", "content": "hello"}]}),
    )

    assert response.status_code == 200
    assert response.body == b'{"id":"cmpl_1","object":"chat.completion","model":"core-nest/google","choices":[]}'
    assert response.headers["X-LLM-Provider"] == "google"
    assert response.headers["X-LLM-Model"] == "google/gemini-2.5-flash-lite"


@pytest.mark.asyncio
async def test_embeddings_controller_returns_public_model_and_headers(mocker) -> None:
    payload = {
        "object": "list",
        "data": [{"embedding": [0.1, 0.2], "index": 0}],
        "model": "google/text-embedding-004",
    }

    async def _dispatch(params, request, provider_preference=None):
        request.state.audit_context = {
            "response_meta": {
                "provider_attempts": [
                    {"provider": "google", "model": "google/text-embedding-004", "status": "succeeded"}
                ]
            }
        }
        return payload

    mocker.patch(
        "app.api.services.embeddings_service.EmbeddingsService.dispatch",
        new=mocker.AsyncMock(side_effect=_dispatch),
    )

    response = await create_embeddings(
        _request({"Authorization": "Bearer test-key"}),
        Embeddings.model_validate({"model": "core-nest/google", "input": ["hello"]}),
    )

    assert response.status_code == 200
    assert response.body == b'{"object":"list","data":[{"embedding":[0.1,0.2],"index":0}],"model":"core-nest/google"}'
    assert response.headers["X-LLM-Provider"] == "google"
    assert response.headers["X-LLM-Model"] == "google/text-embedding-004"


@pytest.mark.asyncio
async def test_controller_bubbles_service_http_exception(mocker) -> None:
    mocker.patch(
        "app.api.services.completion_service.CompletionService.dispatch",
        new=mocker.AsyncMock(
            side_effect=HTTPException(status_code=503, detail="No provider could satisfy the request")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_completions(
            _request({"Authorization": "Bearer test-key"}),
            Completions.model_validate({"model": "core-nest/auto", "messages": [{"role": "user", "content": "hello"}]}),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "No provider could satisfy the request"
