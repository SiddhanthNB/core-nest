from __future__ import annotations

import os
import time
from collections.abc import Mapping
from typing import Any

from litellm import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadGatewayError,
    InternalServerError,
    JSONSchemaValidationError,
    PermissionDeniedError,
    RateLimitError,
    Router,
    ServiceUnavailableError,
    Timeout,
)
from opentelemetry.trace import StatusCode
from redis.asyncio import Redis
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, stop_any, wait_exponential_jitter

from app.config import constants
from app.config.logger import logger
from app.config.tracing import tracer

_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SECONDS = 60
_CIRCUIT_FAILURE_TTL_SECONDS = 600
_DEFAULT_RETRY_WAIT = wait_exponential_jitter(initial=1, max=2, jitter=0.025)
_DEFAULT_TIMEOUT_SECONDS = 15
_FORCED_PROVIDER_TIMEOUT_SECONDS = 30
_MAX_TIMEOUT_SECONDS = 60
_MAX_RETRY_AFTER_SECONDS = 10


_RETRYABLE_PROVIDER_EXCEPTIONS = (
    APIConnectionError,
    APIError,
    BadGatewayError,
    InternalServerError,
    JSONSchemaValidationError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

# auth failures count toward the circuit but are never retried
_CIRCUIT_FAILURE_EXCEPTIONS = (*_RETRYABLE_PROVIDER_EXCEPTIONS, AuthenticationError, PermissionDeniedError)

# process-level routers, keyed by (provider, kind, model, api_key)
_ROUTERS: dict[tuple[str, str, str, str], Router] = {}


class BaseAdapter:
    def __init__(self, *, provider_name: str, redis: Redis, request: Any = None, provider_preference: str | None = None):  # fmt: skip
        if not provider_name:
            raise ValueError("provider_name is required")
        if redis is None:
            raise ValueError("redis is required")
        self._provider_name = provider_name
        self._provider_config = dict(constants.PROVIDERS[self._provider_name])
        self._models = self._provider_config.get("models", {})
        self.redis = redis
        self.request = request
        self._forced_provider_preference = provider_preference
        self._completion_model: str | None = self._models.get("completion", None)
        self._embedding_model: str | None = self._models.get("embedding", None)
        self._completion_router = None
        self._embedding_router = None
        self._attempt_number = 0

    def _provider_preference(self) -> str | None:
        if self._forced_provider_preference is not None:
            return self._forced_provider_preference
        audit_context = getattr(getattr(self.request, "state", None), "audit_context", {})
        request_meta = audit_context.get("request_meta", {})
        return request_meta.get("provider_pref") or None

    def _shared_router(self, kind: str, model: str, api_key: str, *, additional_drop_params: list[str] | None = None) -> Router:  # fmt: skip
        key = (self._provider_name, kind, model, api_key)
        if key not in _ROUTERS:
            litellm_params = {"model": model, "api_key": api_key, "drop_params": True}
            if additional_drop_params:
                litellm_params["additional_drop_params"] = additional_drop_params
            model_list = [{"model_name": model, "litellm_params": litellm_params}]
            _ROUTERS[key] = Router(model_list=model_list, num_retries=0, disable_cooldowns=True, set_verbose=False)
        return _ROUTERS[key]

    def _provider_label(self) -> str:
        if self._provider_preference() is not None:
            return f"requested provider '{self._provider_name}'"
        return f"provider '{self._provider_name}'"

    def _supports_completion(self) -> bool:
        return self._completion_router is not None and self._completion_model is not None

    def _supports_embedding(self) -> bool:
        return self._embedding_router is not None and self._embedding_model is not None

    async def is_circuit_open(self) -> bool:
        return bool(await self.redis.exists(f"circuit:{self._provider_name}:open"))

    async def acompletion(self, *, messages: list[dict[str, Any]], request_params: Mapping[str, Any], response_validator: Any | None = None) -> Any:  # fmt: skip
        if not self._supports_completion():
            raise RuntimeError(f"Provider '{self._provider_name}' does not support completion")
        return await self._execute(
            lambda: self._completion_router.acompletion(
                model=self._completion_model,
                messages=messages,
                timeout=self._request_timeout_seconds(),
                **request_params,
            ),
            model=self._completion_model,
            response_validator=response_validator,
        )

    async def aembedding(self, *, input_data: str | list[str], request_params: Mapping[str, Any]) -> Any:
        if not self._supports_embedding():
            raise RuntimeError(f"Provider '{self._provider_name}' does not support embedding")
        return await self._execute(
            lambda: self._embedding_router.aembedding(
                model=self._embedding_model,
                input=input_data,
                timeout=self._request_timeout_seconds(),
                **request_params,
            ),
            model=self._embedding_model,
        )

    async def _execute(self, operation: Any, *, model: str | None, response_validator: Any | None = None) -> Any:
        try:
            result = await self._call_with_retry(operation, model=model, response_validator=response_validator)
        except Exception as exc:
            if isinstance(exc, _RETRYABLE_PROVIDER_EXCEPTIONS) and self._attempt_number:
                logger.warning(
                    f"[attempt: {self._attempt_number}] {self._provider_label()} attempts exhausted "
                    f"after {type(exc).__name__}"
                )
            opened = await self._record_failure() if isinstance(exc, _CIRCUIT_FAILURE_EXCEPTIONS) else False
            if opened:
                logger.warning(f"{self._provider_label()} circuit opened after repeated failures")
            raise
        had_state = await self._reset_circuit()
        if had_state:
            logger.info(f"{self._provider_label()} circuit reset after success")
        return result

    async def _call_with_retry(self, operation: Any, *, model: str | None, response_validator: Any | None = None) -> Any:  # fmt: skip
        retry_config = {
            "stop": stop_any(stop_after_attempt(3), self._deadline_stop),
            "wait": self._wait_for_retry,
            "retry": retry_if_exception_type(_RETRYABLE_PROVIDER_EXCEPTIONS),
            "reraise": True,
        }
        async for attempt in AsyncRetrying(**retry_config):
            attempt_number = attempt.retry_state.attempt_number
            with attempt, self._retry_attempt_span(attempt_number, model=model) as span:
                self._attempt_number = attempt_number
                logger.debug(f"[attempt: {attempt_number}] Starting provider attempt with {self._provider_label()}")
                try:
                    result = await operation()
                    if response_validator is not None:
                        response_validator(result)
                except Exception as exc:
                    logger.warning(f"[attempt: {attempt_number}] {self._provider_label()} attempt failed with {type(exc).__name__}")  # fmt: skip
                    span.set_attribute("outcome", "failed")
                    span.set_attribute("error.type", type(exc).__name__)
                    span.set_status(StatusCode.ERROR)
                    raise
                span.set_attribute("outcome", "succeeded")
                span.set_status(StatusCode.OK)
                return result

    def _retry_attempt_span(self, attempt_number: int, *, model: str | None):
        attributes = {"gen_ai.provider.name": self._provider_name, "gen_ai.request.model": model or "-", "retry.attempt": attempt_number}  # fmt: skip
        return tracer.start_as_current_span(f"attempt {attempt_number} {self._provider_name}", attributes=attributes, record_exception=False, set_status_on_exception=False)  # fmt: skip

    def _api_key(self) -> str:
        api_key_env = self._provider_config.get("api_key_env", None)
        if not api_key_env:
            raise RuntimeError(
                f"API key environment variable not configured for provider '{self._provider_name}',. Expected 'api_key_env' in provider config."
            )
        api_key = os.getenv(api_key_env, None)
        if not api_key:
            raise RuntimeError(
                f"Missing API key for provider '{self._provider_name}'. Expected env var '{api_key_env}'."
            )
        return api_key

    async def _record_failure(self) -> bool:
        failure_key = f"circuit:{self._provider_name}:failures"
        failures = int(await self.redis.incr(failure_key))
        await self.redis.expire(failure_key, _CIRCUIT_FAILURE_TTL_SECONDS)
        if failures >= _CIRCUIT_FAILURE_THRESHOLD:
            await self.redis.set(f"circuit:{self._provider_name}:open", "open", ex=_CIRCUIT_COOLDOWN_SECONDS)
            await self.redis.delete(failure_key)
            return True
        return False

    async def _reset_circuit(self) -> bool:
        failure_key = f"circuit:{self._provider_name}:failures"
        open_key = f"circuit:{self._provider_name}:open"
        had_state = bool(await self.redis.exists(failure_key) or await self.redis.exists(open_key))
        await self.redis.delete(failure_key, open_key)
        return had_state

    def _wait_for_retry(self, retry_state: Any) -> float:
        wait = self._retry_wait_seconds(retry_state)
        remaining = self._remaining_seconds()
        return wait if remaining is None else max(0.0, min(wait, remaining))

    def _retry_wait_seconds(self, retry_state: Any) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if exc is not None:
            response = getattr(exc, "response", None)
            headers = getattr(exc, "litellm_response_headers", None) or getattr(response, "headers", None)
            retry_after = (headers.get("Retry-After") or headers.get("retry-after")) if headers else None
            if retry_after is not None:
                try:
                    return max(0.0, min(float(retry_after), _MAX_RETRY_AFTER_SECONDS))
                except (TypeError, ValueError):
                    pass
        return _DEFAULT_RETRY_WAIT(retry_state)

    def _remaining_seconds(self) -> float | None:
        deadline = getattr(getattr(self.request, "state", None), "llm_deadline", None)
        if deadline is None:
            return None
        return deadline - time.monotonic()

    def _deadline_stop(self, retry_state: Any) -> bool:
        # tenacity computes upcoming_sleep before evaluating stop
        remaining = self._remaining_seconds()
        return remaining is not None and remaining <= retry_state.upcoming_sleep

    def _timeout_override_seconds(self) -> int | None:
        headers = getattr(self.request, "headers", None)
        if headers is None:
            return None
        timeout_value = headers.get("X-LLM-Timeout")
        if timeout_value is None:
            return None
        try:
            timeout_seconds = int(float(timeout_value))
        except (TypeError, ValueError):
            return None
        if timeout_seconds <= 0:
            return None
        return min(timeout_seconds, _MAX_TIMEOUT_SECONDS)

    def _attempt_timeout_seconds(self) -> int:
        timeout_override = self._timeout_override_seconds()
        if timeout_override is not None:
            return timeout_override
        if self._provider_preference() is not None:
            return _FORCED_PROVIDER_TIMEOUT_SECONDS
        return _DEFAULT_TIMEOUT_SECONDS

    def _request_timeout_seconds(self) -> float:
        timeout_seconds = self._attempt_timeout_seconds()
        remaining = self._remaining_seconds()
        return timeout_seconds if remaining is None else max(0.0, min(timeout_seconds, remaining))

