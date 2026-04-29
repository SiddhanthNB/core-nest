from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
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
