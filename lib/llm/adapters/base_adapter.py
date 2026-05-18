from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from typing import Any

from litellm import (
    APIConnectionError,
    APIError,
    BadGatewayError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from redis.asyncio import Redis
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.config import constants
from app.config.logger import logger

_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SECONDS = 60
_CIRCUIT_FAILURE_TTL_SECONDS = 600
_DEFAULT_RETRY_WAIT = wait_exponential_jitter(initial=1, max=2, jitter=0.025)
_DEFAULT_TIMEOUT_SECONDS = 5
_FORCED_PROVIDER_TIMEOUT_SECONDS = 10


_RETRYABLE_PROVIDER_EXCEPTIONS = (
    APIConnectionError,
    APIError,
    BadGatewayError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)


class BaseAdapter:
    def __init__(self, *, provider_name: str, redis: Redis, request: Any = None):
        if not provider_name:
            raise ValueError("provider_name is required")
        if redis is None:
            raise ValueError("redis is required")
        self._provider_name = provider_name
        self._provider_config = dict(constants.PROVIDERS[self._provider_name])
        self._models = self._provider_config.get("models", {})
        self.redis = redis
        self.request = request
        self._completion_model: str | None = self._models.get("completion", None)
        self._embedding_model: str | None = self._models.get("embedding", None)
        self._completion_router = None
        self._embedding_router = None
        self._attempt_number = 0

    def _provider_preference(self) -> str | None:
        audit_context = getattr(getattr(self.request, "state", None), "audit_context", {})
        request_meta = audit_context.get("request_meta", {})
        return request_meta.get("provider_pref") or None

    def _supports_completion(self) -> bool:
        return self._completion_router is not None and self._completion_model is not None

    def _supports_embedding(self) -> bool:
        return self._embedding_router is not None and self._embedding_model is not None

    async def is_circuit_open(self) -> bool:
        return bool(await self.redis.exists(f"circuit:{self._provider_name}:open"))

    async def acompletion(self, *, messages: list[dict[str, Any]], request_params: Mapping[str, Any]) -> Any:
        if not self._supports_completion():
            raise RuntimeError(f"Provider '{self._provider_name}' does not support completion")
        return await self._execute(
            lambda: self._completion_router.acompletion(
                model=self._completion_model, messages=messages, **request_params
            ),
            model=self._completion_model,
        )

    async def aembedding(self, *, input_data: str | list[str], request_params: Mapping[str, Any]) -> Any:
        if not self._supports_embedding():
            raise RuntimeError(f"Provider '{self._provider_name}' does not support embedding")
        return await self._execute(
            lambda: self._embedding_router.aembedding(model=self._embedding_model, input=input_data, **request_params),
            model=self._embedding_model,
        )

    async def _execute(self, operation: Any, *, model: str | None) -> Any:
        try:
            result = await self._call_with_retry(operation, model=model)
        except Exception as exc:
            state = getattr(self.request, "state", None)
            request_id = getattr(state, "request_id", None)
            request_prefix = f"[request_id: {str(request_id)[:8]}] " if request_id else ""
            provider_preference = self._provider_preference()
            if isinstance(exc, _RETRYABLE_PROVIDER_EXCEPTIONS) and self._attempt_number:
                provider_phrase = (
                    f"requested provider '{self._provider_name}'"
                    if provider_preference is not None
                    else f"provider '{self._provider_name}'"
                )
                logger.warning(
                    f"{request_prefix}[attempt: {self._attempt_number}] {provider_phrase} attempts exhausted "
                    f"after {type(exc).__name__}"
                )
            opened = await self._record_failure()
            if opened:
                provider_phrase = (
                    f"requested provider '{self._provider_name}'"
                    if provider_preference is not None
                    else f"provider '{self._provider_name}'"
                )
                logger.warning(f"{request_prefix}{provider_phrase} circuit opened after repeated failures")
            raise
        had_state = await self._reset_circuit()
        if had_state:
            state = getattr(self.request, "state", None)
            request_id = getattr(state, "request_id", None)
            request_prefix = f"[request_id: {str(request_id)[:8]}] " if request_id else ""
            provider_preference = self._provider_preference()
            provider_phrase = (
                f"requested provider '{self._provider_name}'"
                if provider_preference is not None
                else f"provider '{self._provider_name}'"
            )
            logger.info(f"{request_prefix}{provider_phrase} circuit reset after success")
        return result

    async def _call_with_retry(self, operation: Any, *, model: str | None) -> Any:
        retry_config = {
            "stop": stop_after_attempt(3),
            "before": self._before_attempt(),
            "wait": self._wait_for_retry,
            "retry": retry_if_exception_type(_RETRYABLE_PROVIDER_EXCEPTIONS),
            "reraise": True,
            "before_sleep": self._before_retry_sleep(),
        }
        async for attempt in AsyncRetrying(**retry_config):
            with attempt:
                try:
                    return await asyncio.wait_for(operation(), timeout=self._attempt_timeout_seconds())
                except TimeoutError as exc:
                    raise Timeout(
                        message=f"Provider '{self._provider_name}' timed out after {self._attempt_timeout_seconds()} seconds",
                        model=model or self._provider_name,
                        llm_provider=self._provider_name,
                    ) from exc

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
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if exc is not None:
            response = getattr(exc, "response", None)
            headers = getattr(response, "headers", None)
            retry_after = headers.get("Retry-After") if headers else None
            if retry_after is not None:
                try:
                    return float(retry_after)
                except (TypeError, ValueError):
                    pass
        return _DEFAULT_RETRY_WAIT(retry_state)

    def _attempt_timeout_seconds(self) -> int:
        if self._provider_preference() is not None:
            return _FORCED_PROVIDER_TIMEOUT_SECONDS
        return _DEFAULT_TIMEOUT_SECONDS

    def _before_retry_sleep(self):
        def _log(retry_state: Any) -> None:
            exc = retry_state.outcome.exception() if retry_state.outcome else None
            state = getattr(self.request, "state", None)
            request_id = getattr(state, "request_id", None)
            request_prefix = f"[request_id: {str(request_id)[:8]}] " if request_id else ""
            provider_preference = self._provider_preference()
            provider_phrase = (
                f"requested provider '{self._provider_name}'"
                if provider_preference is not None
                else f"provider '{self._provider_name}'"
            )
            logger.warning(
                f"{request_prefix}[attempt: {retry_state.attempt_number}] {provider_phrase} "
                f"attempt failed with {type(exc).__name__ if exc else 'UnknownError'}"
            )

        return _log

    def _before_attempt(self):
        def _log(retry_state: Any) -> None:
            self._attempt_number = retry_state.attempt_number
            state = getattr(self.request, "state", None)
            request_id = getattr(state, "request_id", None)
            request_prefix = f"[request_id: {str(request_id)[:8]}] " if request_id else ""
            provider_preference = self._provider_preference()
            provider_phrase = (
                f"requested provider '{self._provider_name}'"
                if provider_preference is not None
                else f"provider '{self._provider_name}'"
            )
            logger.debug(
                f"{request_prefix}[attempt: {retry_state.attempt_number}] "
                f"Starting provider attempt with {provider_phrase}"
            )

        return _log
