from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.core.factory import create_app
from app.db.schemas.clients import Client as ClientSchema


def _cached_client_json() -> str:
    now = datetime.now(timezone.utc)
    client = SimpleNamespace(
        id=uuid4(),
        name="Integration Client",
        is_active=True,
        created_at=now,
        updated_at=now,
        rate_limit_config=SimpleNamespace(
            id=1,
            client_id=uuid4(),
            requests_per_minute=10,
            requests_per_hour=100,
            requests_per_day=1000,
            concurrent_requests_limit=None,
            created_at=now,
            updated_at=now,
        ),
    )
    return ClientSchema.Read.model_validate(client).model_dump_json()


def _fake_completion_adapter(*, provider: str, model: str, payload: dict, error: Exception | None = None):
    async def _acompletion(*, messages, request_params):
        if error is not None:
            raise error
        return payload

    return SimpleNamespace(
        _provider_name=provider,
        _completion_model=model,
        is_circuit_open=lambda: _false(),
        acompletion=_acompletion,
    )


def _fake_embedding_adapter(*, provider: str, model: str, error: Exception | None = None):
    async def _aembedding(*, input_data, request_params):
        if error is not None:
            raise error
        return {"object": "list", "data": [{"embedding": [0.1, 0.2], "index": 0}], "model": model}

    return SimpleNamespace(
        _provider_name=provider,
        _embedding_model=model,
        is_circuit_open=lambda: _false(),
        aembedding=_aembedding,
    )


async def _false() -> bool:
    return False


@pytest.mark.asyncio
async def test_completions_request_flow_cache_hit_persists_audit_row(mocker) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch("app.api.deps.auth.get_cache", new=mocker.AsyncMock(return_value=_cached_client_json()))
    touch_cache = mocker.patch("app.api.deps.auth.touch_cache", new=mocker.AsyncMock())
    mocker.patch("app.api.deps.rate_limit.redis_client", fake_redis)
    mocker.patch("app.api.services.base_service.redis_client", fake_redis)
    mocker.patch("app.api.core.middleware.constants.APP_ENV", "production")
    acreate = mocker.patch("app.api.core.middleware.AuditLog.acreate", new=mocker.AsyncMock())
    mocker.patch(
        "app.api.services.base_service.get_adapter",
        return_value=_fake_completion_adapter(
            provider="mistral",
            model="mistral/ministral-8b-2410",
            payload={
                "id": "cmpl_1",
                "object": "chat.completion",
                "model": "mistral/ministral-8b-2410",
                "choices": [{"finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
            },
        ),
    )

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/completions",
            headers={"Authorization": "Bearer secret-key", "X-LLM-Provider": "mistral"},
            json={"messages": [{"role": "user", "content": "hello"}], "temperature": 0.2},
        )

    assert response.status_code == 200
    assert response.json()["object"] == "chat.completion"
    touch_cache.assert_awaited_once()
    kwargs = acreate.await_args.kwargs
    assert kwargs["success"] is True
    assert kwargs["provider"] == "mistral"
    assert kwargs["model"] == "mistral/ministral-8b-2410"
    assert kwargs["request_meta"] == {"provider_pref": "mistral", "temperature": 0.2, "message_count": 1}
    assert kwargs["response_meta"] == {
        "provider_attempts": [{"provider": "mistral", "model": "mistral/ministral-8b-2410", "status": "succeeded"}],
        "attempt_count": 1,
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }


@pytest.mark.asyncio
async def test_completions_fallback_progression_persists_attempt_stack(mocker) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch("app.api.deps.auth.get_cache", new=mocker.AsyncMock(return_value=_cached_client_json()))
    mocker.patch("app.api.deps.auth.touch_cache", new=mocker.AsyncMock())
    mocker.patch("app.api.deps.rate_limit.redis_client", fake_redis)
    mocker.patch("app.api.services.base_service.redis_client", fake_redis)
    mocker.patch("app.api.core.middleware.constants.APP_ENV", "production")
    acreate = mocker.patch("app.api.core.middleware.AuditLog.acreate", new=mocker.AsyncMock())
    mocker.patch(
        "app.api.services.base_service.get_adapter",
        side_effect=[
            _fake_completion_adapter(
                provider="openai",
                model="gpt-4o-mini",
                payload={},
                error=RuntimeError("boom"),
            ),
            _fake_completion_adapter(
                provider="google",
                model="google-2.5-flash-lite",
                payload={
                    "id": "cmpl_2",
                    "object": "chat.completion",
                    "model": "google-2.5-flash-lite",
                    "choices": [{"finish_reason": "stop"}],
                },
            ),
        ],
    )

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/completions",
            headers={"Authorization": "Bearer secret-key"},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 200
    kwargs = acreate.await_args.kwargs
    assert kwargs["provider"] == "google"
    assert kwargs["model"] == "google-2.5-flash-lite"
    assert kwargs["response_meta"] == {
        "provider_attempts": [
            {"provider": "openai", "model": "gpt-4o-mini", "status": "failed", "error": "RuntimeError"},
            {"provider": "google", "model": "google-2.5-flash-lite", "status": "succeeded"},
        ],
        "attempt_count": 2,
        "finish_reason": "stop",
    }


@pytest.mark.asyncio
async def test_auth_failure_does_not_create_audit_row(mocker) -> None:
    mocker.patch("app.api.core.middleware.constants.APP_ENV", "production")
    acreate = mocker.patch("app.api.core.middleware.AuditLog.acreate", new=mocker.AsyncMock())

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/completions", json={"messages": [{"role": "user", "content": "hello"}]})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing Authorization header"}
    acreate.assert_not_called()


@pytest.mark.asyncio
async def test_embeddings_without_forced_provider_do_not_cross_fallback(mocker) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch("app.api.deps.auth.get_cache", new=mocker.AsyncMock(return_value=_cached_client_json()))
    mocker.patch("app.api.deps.auth.touch_cache", new=mocker.AsyncMock())
    mocker.patch("app.api.deps.rate_limit.redis_client", fake_redis)
    mocker.patch("app.api.services.base_service.redis_client", fake_redis)
    mocker.patch("app.api.core.middleware.constants.APP_ENV", "production")
    acreate = mocker.patch("app.api.core.middleware.AuditLog.acreate", new=mocker.AsyncMock())
    get_adapter = mocker.patch(
        "app.api.services.base_service.get_adapter",
        return_value=_fake_embedding_adapter(provider="google", model="google-embedding-001"),
    )

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/embeddings",
            headers={"Authorization": "Bearer secret-key"},
            json={"input": ["hello"]},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "X-LLM-Provider header is required for embeddings"}
    get_adapter.assert_not_called()
    kwargs = acreate.await_args.kwargs
    assert kwargs["success"] is False
    assert kwargs["provider"] is None
    assert kwargs["model"] is None
    assert kwargs["request_meta"] == {"provider_pref": None, "input_count": 1}
    assert kwargs["response_meta"] == {"provider_attempts": [], "attempt_count": 0}


@pytest.mark.asyncio
async def test_embeddings_reject_provider_without_embedding_support(mocker) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    mocker.patch("app.api.deps.auth.get_cache", new=mocker.AsyncMock(return_value=_cached_client_json()))
    mocker.patch("app.api.deps.auth.touch_cache", new=mocker.AsyncMock())
    mocker.patch("app.api.deps.rate_limit.redis_client", fake_redis)
    mocker.patch("app.api.services.base_service.redis_client", fake_redis)
    mocker.patch("app.api.core.middleware.constants.APP_ENV", "production")
    acreate = mocker.patch("app.api.core.middleware.AuditLog.acreate", new=mocker.AsyncMock())
    get_adapter = mocker.patch("app.api.services.base_service.get_adapter")

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/embeddings",
            headers={"Authorization": "Bearer secret-key", "X-LLM-Provider": "groq"},
            json={"input": ["hello"]},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Unsupported embedding provider 'groq'"}
    get_adapter.assert_not_called()
    kwargs = acreate.await_args.kwargs
    assert kwargs["success"] is False
    assert kwargs["provider"] is None
    assert kwargs["model"] is None
