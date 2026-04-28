from __future__ import annotations

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
    UnsupportedParamsError,
    get_supported_openai_params,
)
from redis.asyncio import Redis
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.config import constants
from app.config.logger import logger

_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SECONDS = 60
_CIRCUIT_FAILURE_TTL_SECONDS = 600
_DEFAULT_RETRY_WAIT = wait_exponential_jitter(initial=0.2, max=0.8, jitter=0.02)


RETRYABLE_PROVIDER_EXCEPTIONS = (
    APIConnectionError,
    APIError,
    BadGatewayError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
)

NON_RETRYABLE_PROVIDER_EXCEPTIONS = (UnsupportedParamsError,)


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

    def _supports_completion(self) -> bool:
        return self._completion_router is not None and self._completion_model is not None

    def _supports_embedding(self) -> bool:
        return self._embedding_router is not None and self._embedding_model is not None

    def validate_params(self, capability: str, request_params: Mapping[str, Any]) -> None:
        if capability == "completion":
            if not self._supports_completion():
                raise RuntimeError(f"Provider '{self._provider_name}' does not support completion")
            model = self._completion_model
            request_type = "chat_completion"
        elif capability == "embedding":
            if not self._supports_embedding():
                raise RuntimeError(f"Provider '{self._provider_name}' does not support embedding")
            model = self._embedding_model
            request_type = "embeddings"
        else:
            raise ValueError(f"Unsupported capability '{capability}'")
        supported = get_supported_openai_params(
            model=model,
            custom_llm_provider=self._provider_config.get("provider", self._provider_name),
            request_type=request_type,
        )
        if not supported:
            return
        requested = [key for key, value in request_params.items() if value is not None and key not in {"messages", "input"}]
        unsupported = [key for key in requested if key not in supported]
        if unsupported:
            raise UnsupportedParamsError(
                message=f"Provider '{self._provider_name}' does not support params: {', '.join(unsupported)}",
                llm_provider=self._provider_config.get("provider", self._provider_name),
                model=model,
            )

    async def is_circuit_open(self) -> bool:
        return bool(await self.redis.exists(f"circuit:{self._provider_name}:open"))

    async def acompletion(self, *, messages: list[dict[str, Any]], request_params: Mapping[str, Any]) -> Any:
        if not self._supports_completion():
            raise RuntimeError(f"Provider '{self._provider_name}' does not support completion")
        return await self._execute(lambda: self._completion_router.acompletion(model=self._completion_model, messages=messages, **request_params))

    async def aembedding(self, *, input_data: str | list[str], request_params: Mapping[str, Any]) -> Any:
        if not self._supports_embedding():
            raise RuntimeError(f"Provider '{self._provider_name}' does not support embedding")
        return await self._execute(lambda: self._embedding_router.aembedding(model=self._embedding_model, input=input_data, **request_params))

    async def _execute(self, operation: Any) -> Any:
        try:
            result = await self._call_with_retry(operation)
        except Exception as exc:
            if isinstance(exc, RETRYABLE_PROVIDER_EXCEPTIONS):
                self._logger(event="retry_exhausted", provider=self._provider_name, error_type=type(exc).__name__).warning("Retry policy exhausted for provider")
            opened = await self._record_failure()
            self._logger(event="provider_attempt_failed", provider=self._provider_name, error_type=type(exc).__name__).warning("Provider attempt failed")
            if opened:
                self._logger(event="circuit_opened", provider=self._provider_name).warning("Provider circuit opened after repeated failures")
            raise
        had_state = await self._reset_circuit()
        if had_state:
            self._logger(event="circuit_reset", provider=self._provider_name).info("Provider circuit state reset after success")
        return result

    async def _call_with_retry(self, operation: Any) -> Any:
        async for attempt in AsyncRetrying(stop=stop_after_attempt(3), wait=self._wait_for_retry, retry=retry_if_exception_type(RETRYABLE_PROVIDER_EXCEPTIONS), reraise=True, before_sleep=self._before_retry_sleep()):
            with attempt:
                return await operation()

    def _api_key(self) -> str:
        api_key_env = self._provider_config.get("api_key_env", None)
        if not api_key_env:
            raise RuntimeError(f"API key environment variable not configured for provider '{self._provider_name}',. Expected 'api_key_env' in provider config.")
        api_key = os.getenv(api_key_env, None)
        if not api_key:
            raise RuntimeError(f"Missing API key for provider '{self._provider_name}'. Expected env var '{api_key_env}'.")
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

    def _before_retry_sleep(self):
        def _log(retry_state: Any) -> None:
            exc = retry_state.outcome.exception() if retry_state.outcome else None
            self._logger(event="retry_scheduled", provider=self._provider_name, attempt=retry_state.attempt_number, error_type=type(exc).__name__ if exc else None).warning("Retry scheduled for provider attempt")
        return _log

    def _logger(self, **extra: Any):
        bound: dict[str, Any] = {}
        state = getattr(self.request, "state", None)
        request_id = getattr(state, "request_id", None)
        if request_id:
            bound["request_id"] = request_id
        bound.update({key: value for key, value in extra.items() if value is not None})
        return logger.bind(**bound)
