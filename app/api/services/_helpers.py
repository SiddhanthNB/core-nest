from __future__ import annotations

import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from litellm import JSONSchemaValidationError, UnsupportedParamsError, get_supported_openai_params
from redis.exceptions import RedisError

from app.config import constants
from app.config.logger import logger

_COMPLETION_ROUND_ROBIN_KEY_PREFIX = "llm:routing:completion:rr_counter"
_COMPLETION_ROUND_ROBIN_TTL_SECONDS = 36 * 60 * 60
_REQUEST_DEADLINE_SECONDS = 90


def _provider_attempts(request: Any) -> list[dict[str, Any]]:
    if not request:
        return []
    audit_context = getattr(request.state, "audit_context", {})
    response_meta = audit_context.setdefault("response_meta", {})
    provider_attempts = response_meta.setdefault("provider_attempts", [])
    request.state.audit_context = audit_context
    return provider_attempts


def _start_request_deadline(request: Any) -> float:
    deadline = time.monotonic() + _REQUEST_DEADLINE_SECONDS
    state = getattr(request, "state", None)
    if state is not None:
        state.llm_deadline = deadline
    return deadline


def _deadline_exceeded(deadline: float) -> bool:
    return time.monotonic() >= deadline


def _remaining_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _payload_mapping(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    if hasattr(payload, "model_dump"):
        normalized = payload.model_dump(exclude_none=True)
        return normalized if isinstance(normalized, Mapping) else {}
    normalized = jsonable_encoder(payload, exclude_none=True)
    return normalized if isinstance(normalized, Mapping) else {}


def _response_meta(provider_attempts: list[dict[str, Any]], *, payload: Any) -> dict[str, Any]:
    payload_mapping = _payload_mapping(payload)
    response_meta = {
        "provider_attempts": provider_attempts,
        "attempt_count": len([attempt for attempt in provider_attempts if attempt.get("status") != "skipped"]),
    }
    choices = payload_mapping.get("choices") or []
    if choices:
        response_meta["finish_reason"] = choices[0].get("finish_reason")
    if payload_mapping.get("usage") is not None:
        response_meta["usage"] = jsonable_encoder(payload_mapping["usage"], exclude_none=True)
    return response_meta


def _set_response_meta(request: Any, response_meta: dict[str, Any]) -> None:
    if not request:
        return
    audit_context = getattr(request.state, "audit_context", {})
    audit_context["response_meta"] = response_meta
    request.state.audit_context = audit_context


def _litellm_request_error(exc: Exception, *, provider: str, model: str, request_type: str) -> HTTPException:
    if isinstance(exc, UnsupportedParamsError):
        supported = get_supported_openai_params(
            model=model,
            custom_llm_provider=provider,
            request_type=request_type,
        )
        detail = f"Provider '{provider}' does not support one or more request params."
        if supported:
            detail = f"{detail} Supported params: {', '.join(sorted(supported))}"
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    status_code = int(getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST) or status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status_code, detail=str(exc))


async def _ordered_completion_providers(provider_preference: str | None, *, redis_client: Any, request: Any = None) -> list[str]:  # fmt: skip
    if provider_preference:
        return [provider_preference]

    providers = list(constants.COMPLETION_PROVIDERS)
    if len(providers) <= 1:
        return providers

    round_robin_key = _completion_round_robin_key()
    try:
        counter = int(await redis_client.incr(round_robin_key))
        if counter == 1:
            await redis_client.expire(round_robin_key, _COMPLETION_ROUND_ROBIN_TTL_SECONDS)
    except (RedisError, AttributeError, TypeError, ValueError) as exc:
        logger.warning(
            f"Failed to read round-robin ordering from Redis with {type(exc).__name__}. "
            "Falling back to static provider ordering."
        )
        return providers

    start_index = (counter - 1) % len(providers)
    logger.debug(f"Round-robin used with key {round_robin_key}")
    return providers[start_index:] + providers[:start_index]


def _completion_round_robin_key(now: datetime | None = None) -> str:
    current_time = now or datetime.now(UTC)
    return f"{_COMPLETION_ROUND_ROBIN_KEY_PREFIX}:{current_time.strftime('%Y-%m-%d')}"


def _expects_json_response(request_params: Mapping[str, Any]) -> bool:
    response_format = request_params.get("response_format")
    return isinstance(response_format, Mapping) and response_format.get("type") in {"json_object", "json_schema"}


def _extract_response_content(payload: Any) -> str | None:
    payload_mapping = _payload_mapping(payload)
    choices = payload_mapping.get("choices") or []
    if not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        return None
    message = first_choice.get("message") or {}
    if isinstance(message, Mapping):
        content = message.get("content")
        return content if isinstance(content, str) else None
    content = getattr(message, "content", None)
    return content if isinstance(content, str) else None


def _validate_json_response_payload(payload: Any, *, provider: str, model: str, response_format: Any) -> None:  # fmt: skip
    content = _extract_response_content(payload)
    if not content or not content.strip():
        raise JSONSchemaValidationError(
            model=model,
            llm_provider=provider,
            raw_response=content or "",
            schema=json.dumps(response_format),
        )
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        raise JSONSchemaValidationError(
            model=model,
            llm_provider=provider,
            raw_response=content,
            schema=json.dumps(response_format),
        ) from exc
