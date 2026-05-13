from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, status
from litellm import (
    BadRequestError,
    InvalidRequestError,
    JSONSchemaValidationError,
    UnprocessableEntityError,
    UnsupportedParamsError,
)

from app.config import constants
from app.config.redis import redis_client
from lib.llm.adapters import get_adapter

from ._helpers import (
    _expects_json_response,
    _litellm_request_error,
    _ordered_completion_providers,
    _provider_attempts,
    _response_meta,
    _set_response_meta,
    _validate_json_response_payload,
)

_SUPPORTED_COMPLETION_PROVIDERS = set(constants.COMPLETION_PROVIDERS)
_SUPPORTED_EMBEDDING_PROVIDERS = set(constants.EMBEDDING_PROVIDERS)
_LITELLM_REQUEST_ERRORS = (BadRequestError, InvalidRequestError, UnsupportedParamsError, UnprocessableEntityError)


class BaseService:
    def _get_system_prompt(self, prompt_type: str, **kwargs) -> str:
        system_prompts_path = constants.PROMPTS_DIR / "system_prompts"
        return (system_prompts_path / f"{prompt_type}.txt").read_text().strip().format(**kwargs)

    def _message(self, role: str, content: str) -> dict[str, str]:
        return {"role": role, "content": content}

    def _system_messages(self, *, app_system_prompt: str) -> list[dict[str, str]]:
        return [self._message("system", app_system_prompt)]

    async def _fetch_completion(self, *, messages: list[dict[str, Any]], request_params: Mapping[str, Any], provider_preference: str | None, request: Any = None) -> dict[str, Any]:  # fmt: skip
        if provider_preference and provider_preference not in _SUPPORTED_COMPLETION_PROVIDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported provider '{provider_preference}'"
            )

        providers = await _ordered_completion_providers(provider_preference, redis_client=redis_client, request=request)
        provider_attempts = _provider_attempts(request)
        last_error: Exception | None = None

        for provider_name in providers:
            adapter = get_adapter(provider_name, redis=redis_client, request=request)
            resolved_provider = adapter._provider_name
            model = adapter._completion_model

            if await adapter.is_circuit_open():
                provider_attempts.append(
                    {"provider": resolved_provider, "model": model, "status": "skipped", "reason": "circuit_open"}
                )
                if provider_preference:
                    _set_response_meta(request, _response_meta(provider_attempts, payload={}))
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Provider '{resolved_provider}' circuit is open",
                    )
                continue

            try:
                payload = await adapter.acompletion(messages=messages, request_params=request_params)
            except Exception as exc:
                provider_attempts.append(
                    {"provider": resolved_provider, "model": model, "status": "failed", "error": type(exc).__name__}
                )
                last_error = exc
                if provider_preference:
                    _set_response_meta(request, _response_meta(provider_attempts, payload={}))
                    if isinstance(exc, HTTPException):
                        raise
                    if isinstance(exc, _LITELLM_REQUEST_ERRORS):
                        raise _litellm_request_error(
                            exc,
                            provider=resolved_provider,
                            model=model,
                            request_type="chat_completion",
                        ) from exc
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Provider '{resolved_provider}' failed",
                    ) from exc
                continue

            try:
                if _expects_json_response(request_params):
                    _validate_json_response_payload(
                        payload,
                        provider=resolved_provider,
                        model=model,
                        response_format=request_params.get("response_format"),
                    )
            except JSONSchemaValidationError as exc:
                provider_attempts.append(
                    {"provider": resolved_provider, "model": model, "status": "failed", "error": type(exc).__name__}
                )
                last_error = exc
                if provider_preference:
                    _set_response_meta(request, _response_meta(provider_attempts, payload={}))
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Provider '{resolved_provider}' returned invalid JSON",
                    ) from exc
                continue

            provider_attempts.append({"provider": resolved_provider, "model": model, "status": "succeeded"})
            _set_response_meta(request, _response_meta(provider_attempts, payload=payload))
            return payload

        _set_response_meta(request, _response_meta(provider_attempts, payload={}))
        if last_error is not None:
            if isinstance(last_error, _LITELLM_REQUEST_ERRORS):
                last_attempt = next(
                    (attempt for attempt in reversed(provider_attempts) if attempt.get("status") == "failed"), None
                )
                raise _litellm_request_error(
                    last_error,
                    provider=(last_attempt or {}).get("provider", "unknown"),
                    model=(last_attempt or {}).get("model", "unknown"),
                    request_type="chat_completion",
                ) from last_error
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No provider could satisfy the request",
            ) from last_error
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No provider could satisfy the request",
        )

    async def _fetch_embedding(self, *, input_data: str | list[str], request_params: Mapping[str, Any], provider_preference: str | None, request: Any = None) -> dict[str, Any]:  # fmt: skip
        if not provider_preference:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-LLM-Provider header is required for embeddings",
            )
        if provider_preference not in _SUPPORTED_EMBEDDING_PROVIDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported embedding provider '{provider_preference}'",
            )

        provider_attempts = _provider_attempts(request)
        adapter = get_adapter(provider_preference, redis=redis_client, request=request)
        resolved_provider = adapter._provider_name
        model = adapter._embedding_model

        if await adapter.is_circuit_open():
            provider_attempts.append(
                {"provider": resolved_provider, "model": model, "status": "skipped", "reason": "circuit_open"}
            )
            _set_response_meta(request, _response_meta(provider_attempts, payload={}))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Provider '{resolved_provider}' circuit is open",
            )

        try:
            payload = await adapter.aembedding(input_data=input_data, request_params=request_params)
        except Exception as exc:
            provider_attempts.append(
                {"provider": resolved_provider, "model": model, "status": "failed", "error": type(exc).__name__}
            )
            _set_response_meta(request, _response_meta(provider_attempts, payload={}))
            if isinstance(exc, HTTPException):
                raise
            if isinstance(exc, _LITELLM_REQUEST_ERRORS):
                raise _litellm_request_error(
                    exc,
                    provider=resolved_provider,
                    model=model,
                    request_type="embeddings",
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Provider '{resolved_provider}' failed",
            ) from exc

        provider_attempts.append({"provider": resolved_provider, "model": model, "status": "succeeded"})
        _set_response_meta(request, _response_meta(provider_attempts, payload=payload))
        return payload
