from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opentelemetry.sdk.trace import TracerProvider
from starlette.requests import Request

from app.api.core.middleware import _APILoggerMiddleware


def _request(body: dict, *, path: str = "/completions", headers: dict[str, str] | None = None) -> Request:
    payload = json.dumps(body).encode()
    header_items = [(b"content-type", b"application/json")]
    for key, value in (headers or {}).items():
        header_items.append((key.lower().encode(), value.encode()))

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": header_items,
    }
    return Request(scope, receive=receive)


@pytest.mark.asyncio
async def test_middleware_persists_sanitized_audit_payload(mocker) -> None:
    middleware = _APILoggerMiddleware(FastAPI())
    request = _request(
        {
            "messages": [
                {"role": "system", "content": "secret system prompt"},
                {"role": "user", "content": "hello"},
            ],
            "temperature": 0.7,
            "stream": False,
            "tools": [{"type": "function"}],
        },
        headers={"X-LLM-Provider": "google"},
    )
    request.state.client = SimpleNamespace(id="f1f1454c-dfbe-47bf-ae23-b4cbf91cf4f1")
    acreate = mocker.patch("app.api.core.middleware.AuditLog.acreate", new=mocker.AsyncMock())
    mocker.patch("app.api.core.middleware.constants.APP_ENV", "production")

    async def call_next(req: Request):
        req.state.audit_context["response_meta"].update(
            {
                "provider_attempts": [
                    {"provider": "openai", "model": "gpt-4o-mini", "status": "failed", "error": "RateLimitError"},
                    {"provider": "google", "model": "google-2.5-flash-lite", "status": "succeeded"},
                ],
                "attempt_count": 2,
            }
        )
        return JSONResponse(content={"id": "cmpl_1"}, status_code=200)

    response = await middleware.dispatch(request, call_next)
    await response.background()

    acreate.assert_awaited_once()
    kwargs = acreate.await_args.kwargs
    assert kwargs["path"] == "/completions"
    assert kwargs["method"] == "POST"
    assert str(kwargs["client_id"]) == "f1f1454c-dfbe-47bf-ae23-b4cbf91cf4f1"
    assert str(kwargs["request_id"])
    assert kwargs["success"] is True
    assert kwargs["status_code"] == 200
    assert kwargs["request_meta"] == {
        "provider_pref": "google",
        "stream": False,
        "temperature": 0.7,
        "message_count": 2,
        "tool_count": 1,
    }
    assert "messages" not in kwargs["request_meta"]
    assert kwargs["response_meta"]["provider_attempts"][0]["provider"] == "openai"
    assert kwargs["provider"] == "google"
    assert kwargs["model"] == "google-2.5-flash-lite"
    assert kwargs["process_time_ms"] >= 0


@pytest.mark.asyncio
async def test_middleware_skips_audit_row_for_401(mocker) -> None:
    middleware = _APILoggerMiddleware(FastAPI())
    request = _request({"messages": [{"role": "user", "content": "hello"}]})
    acreate = mocker.patch("app.api.core.middleware.AuditLog.acreate", new=mocker.AsyncMock())
    mocker.patch("app.api.core.middleware.constants.APP_ENV", "production")

    async def call_next(_: Request):
        return JSONResponse(content={"detail": "Invalid API key"}, status_code=401)

    response = await middleware.dispatch(request, call_next)
    await response.background()

    acreate.assert_not_called()


@pytest.mark.asyncio
async def test_middleware_persists_error_as_string(mocker) -> None:
    middleware = _APILoggerMiddleware(FastAPI())
    request = _request({"messages": [{"role": "user", "content": "hello"}]})
    acreate = mocker.patch("app.api.core.middleware.AuditLog.acreate", new=mocker.AsyncMock())
    mocker.patch("app.api.core.middleware.constants.APP_ENV", "production")

    async def call_next(req: Request):
        req.state.audit_context["response_meta"]["provider_attempts"] = [
            {"provider": "groq", "model": "llama", "status": "failed", "error": "RateLimitError"},
        ]
        return JSONResponse(content={"detail": "upstream failed"}, status_code=502)

    response = await middleware.dispatch(request, call_next)
    await response.background()

    assert acreate.await_args.kwargs["error"] == "RateLimitError"
    assert acreate.await_args.kwargs["success"] is False


@pytest.mark.asyncio
async def test_middleware_error_is_none_on_success(mocker) -> None:
    middleware = _APILoggerMiddleware(FastAPI())
    request = _request({"messages": [{"role": "user", "content": "hello"}]})
    acreate = mocker.patch("app.api.core.middleware.AuditLog.acreate", new=mocker.AsyncMock())
    mocker.patch("app.api.core.middleware.constants.APP_ENV", "production")

    async def call_next(_: Request):
        return JSONResponse(content={"id": "cmpl_1"}, status_code=200)

    response = await middleware.dispatch(request, call_next)
    await response.background()

    assert acreate.await_args.kwargs["error"] is None


@pytest.mark.asyncio
async def test_middleware_derives_request_id_from_active_trace(mocker) -> None:
    middleware = _APILoggerMiddleware(FastAPI())
    request = _request({})

    async def call_next(req: Request):
        return JSONResponse(content={}, status_code=200)

    with TracerProvider().get_tracer("test").start_as_current_span("POST /completions") as span:
        await middleware.dispatch(request, call_next)

    assert request.state.request_id == str(uuid.UUID(int=span.get_span_context().trace_id))
    assert request.state.audit_context["request_id"] == request.state.request_id


@pytest.mark.asyncio
async def test_middleware_falls_back_to_uuid4_without_active_trace(mocker) -> None:
    middleware = _APILoggerMiddleware(FastAPI())
    request = _request({})

    async def call_next(req: Request):
        return JSONResponse(content={}, status_code=200)

    await middleware.dispatch(request, call_next)

    assert uuid.UUID(request.state.request_id).version == 4


@pytest.mark.asyncio
async def test_middleware_returns_request_id_header_on_success() -> None:
    middleware = _APILoggerMiddleware(FastAPI())
    request = _request({})

    async def call_next(_: Request):
        return JSONResponse(content={}, status_code=200)

    response = await middleware.dispatch(request, call_next)

    assert response.headers["X-Request-ID"] == request.state.request_id


@pytest.mark.asyncio
async def test_middleware_returns_request_id_header_on_unhandled_error() -> None:
    middleware = _APILoggerMiddleware(FastAPI())
    request = _request({})

    async def call_next(_: Request):
        raise RuntimeError("boom")

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == request.state.request_id


@pytest.mark.asyncio
async def test_cors_exposes_request_id_header() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.api.core.middleware import register_middleware

    app = FastAPI()
    register_middleware(app)

    @app.get("/ping")
    async def _ping():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/ping", headers={"Origin": "https://example.com"})

    assert response.headers["access-control-expose-headers"] == "X-Request-ID"
    assert response.headers["X-Request-ID"]


@pytest.mark.asyncio
@pytest.mark.parametrize("level, expected", [("INFO", []), ("DEBUG", ["[method: GET] [path: /ping] Request started"])])
async def test_ping_logs_only_at_debug(caplog, level, expected) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.api.core.middleware import register_middleware
    from app.config.tracing import instrument_app

    app = FastAPI()
    register_middleware(app)
    instrument_app(app)

    @app.get("/ping")
    async def _ping():
        return "pong"

    caplog.set_level(level, logger="core-nest")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/ping")

    assert response.status_code == 200
    assert [record.getMessage() for record in caplog.records if "Request started" in record.getMessage() or "/ping" in record.getMessage()] == expected  # fmt: skip


@pytest.mark.asyncio
async def test_http_exception_headers_reach_client() -> None:
    from fastapi import HTTPException
    from httpx import ASGITransport, AsyncClient

    from app.api.core._helpers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/limited")
    async def _limited():
        raise HTTPException(status_code=429, detail="Too many requests", headers={"Retry-After": "30"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/limited")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json()["error"]["message"] == "Too many requests"


@pytest.mark.asyncio
@pytest.mark.parametrize("size, expected_status", [(10, 200), (3 * 1024 * 1024, 413)])
async def test_oversized_body_is_rejected_before_reading(size, expected_status) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.api.core.middleware import register_middleware

    app = FastAPI()
    register_middleware(app)

    @app.post("/echo")
    async def _echo():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/echo", content=b"x" * size)

    assert response.status_code == expected_status
    assert response.headers["X-Request-ID"]
    if expected_status == 413:
        assert response.json()["error"]["code"] == "payload_too_large"
