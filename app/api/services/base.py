from __future__ import annotations

import asyncio
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
from opentelemetry.trace import Span, StatusCode

from app.config import constants
from app.config.logger import logger
from app.config.redis import redis_client
from app.config.tracing import tracer
from lib.llm.adapters import get_adapter

from ._helpers import (
    _deadline_exceeded,
    _expects_json_response,
    _litellm_request_error,
    _ordered_completion_providers,
    _payload_mapping,
    _provider_attempts,
    _provider_failed_error,
    _remaining_seconds,
    _response_meta,
    _set_response_meta,
    _start_request_deadline,
    _validate_json_response_payload,
)

_SUPPORTED_COMPLETION_PROVIDERS = set(constants.COMPLETION_PROVIDERS)
_SUPPORTED_EMBEDDING_PROVIDERS = set(constants.EMBEDDING_PROVIDERS)
_LITELLM_REQUEST_ERRORS = (BadRequestError, InvalidRequestError, UnsupportedParamsError, UnprocessableEntityError)


def _provider_attempt_span(operation: str, *, provider: str, model: str | None):
    attributes = {"gen_ai.operation.name": operation, "gen_ai.provider.name": provider, "gen_ai.request.model": model or "-"}  # fmt: skip
    return tracer.start_as_current_span(f"{operation} {model or provider}", attributes=attributes)


def _set_attempt_outcome(span: Span, outcome: str, *, error_type: str | None = None) -> None:
    span.set_attribute("outcome", outcome)
    if error_type is not None:
        span.set_attribute("error.type", error_type)
    if outcome == "failed":
        span.set_status(StatusCode.ERROR)
    elif outcome == "succeeded":
        span.set_status(StatusCode.OK)


def _deadline_exceeded_error(request: Any, provider_attempts: list[dict[str, Any]]) -> HTTPException:
    _set_response_meta(request, _response_meta(provider_attempts, payload={}))
    return HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Request deadline exceeded")


def _provider_preference_value(request: Any = None, provider_preference: str | None = None) -> str | None:
    if provider_preference is not None:
        return provider_preference
    audit_context = getattr(getattr(request, "state", None), "audit_context", {})
    request_meta = audit_context.get("request_meta", {})
    return request_meta.get("provider_pref") or None


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

        deadline = _start_request_deadline(request)
        provider_attempts = _provider_attempts(request)
        hard_deadline = asyncio.timeout(_remaining_seconds(deadline))
        try:
            async with hard_deadline:
                return await self._fetch_completion_with_fallback(messages=messages, request_params=request_params, provider_preference=provider_preference, request=request, deadline=deadline)  # fmt: skip
        except TimeoutError as exc:
            if not hard_deadline.expired():
                raise
            logger.warning("Request deadline exceeded")
            raise _deadline_exceeded_error(request, provider_attempts) from exc

    async def _fetch_completion_with_fallback(self, *, messages: list[dict[str, Any]], request_params: Mapping[str, Any], provider_preference: str | None, request: Any, deadline: float) -> dict[str, Any]:  # fmt: skip
        providers = await _ordered_completion_providers(provider_preference, redis_client=redis_client, request=request)
        provider_attempts = _provider_attempts(request)
        last_error: Exception | None = None
        provider_preference_value = _provider_preference_value(request, provider_preference)
        if provider_preference:
            logger.debug(f"Requested provider candidate '{provider_preference_value}' resolved")
        else:
            logger.debug(f"Resolved provider candidates: {' -> '.join(providers)}")

        for index, provider_name in enumerate(providers):
            if _deadline_exceeded(deadline):
                logger.warning(f"Request deadline exceeded before provider '{provider_name}'")
                raise _deadline_exceeded_error(request, provider_attempts) from last_error
            adapter = get_adapter(
                provider_name,
                redis=redis_client,
                request=request,
                provider_preference=provider_preference,
            )
            resolved_provider = adapter._provider_name
            model = adapter._completion_model

            with _provider_attempt_span("chat", provider=resolved_provider, model=model) as span:
                if await adapter.is_circuit_open():
                    provider_attempts.append(
                        {"provider": resolved_provider, "model": model, "status": "skipped", "reason": "circuit_open"}
                    )
                    _set_attempt_outcome(span, "skipped", error_type="CircuitOpen")
                    if provider_preference:
                        logger.warning(f"Skipping requested provider '{resolved_provider}' because circuit is open")
                    else:
                        logger.warning(f"Skipping provider '{resolved_provider}' because circuit is open")
                    if provider_preference:
                        _set_response_meta(request, _response_meta(provider_attempts, payload={}))
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Provider '{resolved_provider}' circuit is open",
                        )
                    continue

                try:
                    payload = await adapter.acompletion(
                        messages=messages,
                        request_params=request_params,
                        response_validator=(
                            lambda payload: _validate_json_response_payload(
                                payload,
                                provider=resolved_provider,
                                model=model,
                                response_format=request_params.get("response_format"),
                            )
                        )
                        if _expects_json_response(request_params)
                        else None,
                    )
                except asyncio.CancelledError:
                    # hard request deadline cancelled the in-flight provider call
                    provider_attempts.append(
                        {"provider": resolved_provider, "model": model, "status": "failed", "error": "TimeoutError"}
                    )
                    _set_attempt_outcome(span, "failed", error_type="TimeoutError")
                    raise
                except Exception as exc:
                    provider_attempts.append(
                        {"provider": resolved_provider, "model": model, "status": "failed", "error": type(exc).__name__}
                    )
                    _set_attempt_outcome(span, "failed", error_type=type(exc).__name__)
                    last_error = exc
                    if isinstance(exc, JSONSchemaValidationError):
                        if provider_preference:
                            logger.warning(f"Requested provider '{resolved_provider}' returned invalid JSON")
                        else:
                            logger.warning(f"Provider '{resolved_provider}' returned invalid JSON")
                    elif provider_preference:
                        logger.warning(f"Requested provider '{resolved_provider}' failed with {type(exc).__name__}")
                    else:
                        logger.warning(f"Provider '{resolved_provider}' failed with {type(exc).__name__}")
                    if _deadline_exceeded(deadline) and not isinstance(exc, (HTTPException, *_LITELLM_REQUEST_ERRORS)):
                        logger.warning("Request deadline exceeded")
                        raise _deadline_exceeded_error(request, provider_attempts) from exc
                    if provider_preference:
                        _set_response_meta(request, _response_meta(provider_attempts, payload={}))
                        if isinstance(exc, HTTPException):
                            raise
                        if isinstance(exc, JSONSchemaValidationError):
                            raise HTTPException(
                                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail=f"Provider '{resolved_provider}' returned invalid JSON",
                            ) from exc
                        if isinstance(exc, _LITELLM_REQUEST_ERRORS):
                            raise _litellm_request_error(
                                exc,
                                provider=resolved_provider,
                                model=model,
                                request_type="chat_completion",
                            ) from exc
                        raise _provider_failed_error(exc, provider=resolved_provider) from exc
                    next_provider = providers[index + 1] if index + 1 < len(providers) else None
                    if next_provider:
                        logger.debug(
                            f"Falling back from provider '{resolved_provider}' to provider '{next_provider}' "
                            f"after {type(exc).__name__}"
                        )
                    continue

                payload = _payload_mapping(payload)
                provider_attempts.append({"provider": resolved_provider, "model": model, "status": "succeeded"})
                _set_attempt_outcome(span, "succeeded")
                if provider_preference:
                    logger.debug(f"Requested provider '{resolved_provider}' succeeded")
                else:
                    logger.debug(f"Provider '{resolved_provider}' succeeded")
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

        deadline = _start_request_deadline(request)
        provider_attempts = _provider_attempts(request)
        adapter = get_adapter(
            provider_preference,
            redis=redis_client,
            request=request,
            provider_preference=provider_preference,
        )
        resolved_provider = adapter._provider_name
        provider_preference_value = _provider_preference_value(request, provider_preference)
        logger.debug(f"Requested provider candidate '{provider_preference_value}' resolved")
        with _provider_attempt_span("embeddings", provider=resolved_provider, model=adapter._embedding_model) as span:
            if await adapter.is_circuit_open():
                provider_attempts.append(
                    {
                        "provider": resolved_provider,
                        "model": adapter._embedding_model,
                        "status": "skipped",
                        "reason": "circuit_open",
                    }
                )
                _set_attempt_outcome(span, "skipped", error_type="CircuitOpen")
                logger.warning(f"Skipping requested provider '{resolved_provider}' because circuit is open")
                _set_response_meta(request, _response_meta(provider_attempts, payload={}))
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Provider '{resolved_provider}' circuit is open",
                )

            hard_deadline = asyncio.timeout(_remaining_seconds(deadline))
            try:
                async with hard_deadline:
                    payload = await adapter.aembedding(input_data=input_data, request_params=request_params)
            except Exception as exc:
                provider_attempts.append(
                    {
                        "provider": resolved_provider,
                        "model": adapter._embedding_model,
                        "status": "failed",
                        "error": type(exc).__name__,
                    }
                )
                _set_attempt_outcome(span, "failed", error_type=type(exc).__name__)
                logger.warning(f"Requested provider '{resolved_provider}' failed with {type(exc).__name__}")
                if hard_deadline.expired() or (_deadline_exceeded(deadline) and not isinstance(exc, (HTTPException, *_LITELLM_REQUEST_ERRORS))):  # fmt: skip
                    logger.warning("Request deadline exceeded")
                    raise _deadline_exceeded_error(request, provider_attempts) from exc
                _set_response_meta(request, _response_meta(provider_attempts, payload={}))
                if isinstance(exc, HTTPException):
                    raise
                if isinstance(exc, _LITELLM_REQUEST_ERRORS):
                    raise _litellm_request_error(
                        exc,
                        provider=resolved_provider,
                        model=adapter._embedding_model,
                        request_type="embeddings",
                    ) from exc
                raise _provider_failed_error(exc, provider=resolved_provider) from exc

            payload = _payload_mapping(payload)
            provider_attempts.append(
                {"provider": resolved_provider, "model": adapter._embedding_model, "status": "succeeded"}
            )
            _set_attempt_outcome(span, "succeeded")
            logger.debug(f"Requested provider '{resolved_provider}' succeeded")
            _set_response_meta(request, _response_meta(provider_attempts, payload=payload))
            return payload
