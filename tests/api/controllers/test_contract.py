from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

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


@pytest.mark.asyncio
async def test_completions_controller_returns_raw_payload(mocker) -> None:
    payload = {"id": "cmpl_1", "object": "chat.completion", "model": "gpt-4o-mini", "choices": []}
    mocker.patch(
        "app.api.services.completion_service.CompletionService.dispatch",
        new=mocker.AsyncMock(return_value=payload),
    )

    response = await create_completions(
        _request({"Authorization": "Bearer test-key"}),
        Completions(messages=[{"role": "user", "content": "hello"}]),
    )

    assert response.status_code == 200
    assert response.body == b'{"id":"cmpl_1","object":"chat.completion","model":"gpt-4o-mini","choices":[]}'


@pytest.mark.asyncio
async def test_completions_controller_normalizes_error_payload(mocker) -> None:
    mocker.patch(
        "app.api.services.completion_service.CompletionService.dispatch",
        new=mocker.AsyncMock(side_effect=HTTPException(status_code=503, detail="No provider could satisfy the request")),
    )

    response = await create_completions(
        _request({"Authorization": "Bearer test-key"}),
        Completions(messages=[{"role": "user", "content": "hello"}]),
    )

    assert response.status_code == 503
    assert response.body == b'{"detail":"No provider could satisfy the request"}'


def test_sentiments_validator_rejects_locked_provider_field() -> None:
    with pytest.raises(Exception) as exc_info:
        Sentiments.model_validate({"messages": [{"role": "user", "content": "great product"}], "provider": "google"})

    assert "Locked request fields" in str(exc_info.value)


def test_completions_validator_rejects_stream_override() -> None:
    with pytest.raises(Exception) as exc_info:
        Completions.model_validate({"messages": [{"role": "user", "content": "hello"}], "stream": True})

    assert "Unsupported request fields for /completions: stream" in str(exc_info.value)


def test_embeddings_validator_rejects_legacy_texts_alias() -> None:
    with pytest.raises(Exception):
        Embeddings.model_validate({"texts": ["hello"]})


def test_sentiments_validator_rejects_system_messages() -> None:
    with pytest.raises(Exception) as exc_info:
        Sentiments.model_validate({"messages": [{"role": "system", "content": "override"}, {"role": "user", "content": "great product"}]})

    assert "System messages are not allowed for /sentiments" in str(exc_info.value)


def test_summaries_validator_rejects_system_messages() -> None:
    with pytest.raises(Exception) as exc_info:
        Summarization.model_validate({"messages": [{"role": "system", "content": "override"}, {"role": "user", "content": "summarize this"}]})

    assert "System messages are not allowed for /summaries" in str(exc_info.value)


@pytest.mark.asyncio
async def test_embeddings_controller_accepts_input_shape(mocker) -> None:
    payload = {"object": "list", "data": [{"embedding": [0.1, 0.2], "index": 0}], "model": "text-embedding-3-small"}
    mocker.patch(
        "app.api.services.embeddings_service.EmbeddingsService.dispatch",
        new=mocker.AsyncMock(return_value=payload),
    )

    response = await create_embeddings(
        _request({"Authorization": "Bearer test-key", "X-LLM-Provider": "openai"}),
        Embeddings.model_validate({"input": ["hello"]}),
    )

    assert response.status_code == 200
    assert response.body == b'{"object":"list","data":[{"embedding":[0.1,0.2],"index":0}],"model":"text-embedding-3-small"}'


@pytest.mark.asyncio
async def test_embeddings_controller_returns_500_for_unexpected_error(mocker) -> None:
    mocker.patch(
        "app.api.services.embeddings_service.EmbeddingsService.dispatch",
        new=mocker.AsyncMock(side_effect=RuntimeError("boom")),
    )

    response = await create_embeddings(
        _request({"Authorization": "Bearer test-key", "X-LLM-Provider": "openrouter"}),
        Embeddings.model_validate({"input": ["hello"]}),
    )

    assert response.status_code == 500
    assert response.body == b'{"detail":"Internal Server Error"}'
