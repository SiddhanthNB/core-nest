from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.config import constants

_CHAT_MODEL_ALIAS_PREFIX = f"{constants.PROJECT_NAME}/"
_CHAT_AUTO_MODEL_ALIAS = f"{_CHAT_MODEL_ALIAS_PREFIX}auto"


def _completion_model_alias_map() -> dict[str, str | None]:
    aliases = {_CHAT_AUTO_MODEL_ALIAS: None}
    aliases.update({f"{_CHAT_MODEL_ALIAS_PREFIX}{provider}": provider for provider in constants.COMPLETION_PROVIDERS})
    return aliases


def _embedding_model_alias_map() -> dict[str, str]:
    return {f"{_CHAT_MODEL_ALIAS_PREFIX}{provider}": provider for provider in constants.EMBEDDING_PROVIDERS}


def resolve_completion_model(model: str | None) -> tuple[str, str | None]:
    resolved_model = model or _CHAT_AUTO_MODEL_ALIAS
    provider_preference = _completion_model_alias_map().get(resolved_model)
    if resolved_model not in _completion_model_alias_map():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported model '{resolved_model}'",
        )
    return resolved_model, provider_preference


def resolve_embedding_model(model: str | None, *, legacy_provider_preference: str | None = None) -> tuple[str | None, str | None]:  # fmt: skip
    if model is None:
        return None, legacy_provider_preference

    provider_preference = _embedding_model_alias_map().get(model)
    if provider_preference is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported model '{model}'",
        )
    return model, provider_preference


def _success_response(*, payload: Any, request: Request, public_model: str | None = None) -> JSONResponse:
    content = jsonable_encoder(payload)
    if public_model and isinstance(content, dict):
        content["model"] = public_model
    response = JSONResponse(
        content=content,
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
