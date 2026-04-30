from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.config.logger import logger


def _success_response(*, payload: Any, request: Request) -> JSONResponse:
    response = JSONResponse(
        content=jsonable_encoder(payload),
        status_code=status.HTTP_200_OK,
    )

    state = getattr(request, "state", None)
    audit_context = getattr(state, "audit_context", {}) if state is not None else {}
    response_meta = audit_context.get("response_meta", {})
    provider_attempts = response_meta.get("provider_attempts", [])
    final_attempt = next(
        (attempt for attempt in reversed(provider_attempts) if attempt.get("status") == "succeeded"),
        None,
    )

    if final_attempt is None:
        return response

    provider = final_attempt.get("provider")
    model = final_attempt.get("model")
    if provider:
        response.headers["X-LLM-Provider"] = provider
    if model:
        response.headers["X-LLM-Model"] = model

    return response


def _error_response(exc: Exception) -> JSONResponse:
    logger.error(f"Error: {str(exc)}", exc_info=True)
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
        return JSONResponse(content=detail, status_code=exc.status_code)
    return JSONResponse(
        content={"detail": "Internal Server Error"},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
