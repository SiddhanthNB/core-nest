from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, status
from litellm import BadRequestError, InvalidRequestError, UnsupportedParamsError, UnprocessableEntityError, get_supported_openai_params

from app.config import constants
from app.config.redis import redis_client
from lib.llm.adapters import get_adapter

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

    def _provider_attempts(self, request: Any) -> list[dict[str, Any]]:
        if not request:
            return []
        audit_context = getattr(request.state, "audit_context", {})
        response_meta = audit_context.setdefault("response_meta", {})
        provider_attempts = response_meta.setdefault("provider_attempts", [])
        request.state.audit_context = audit_context
        return provider_attempts

    def _response_meta(self, provider_attempts: list[dict[str, Any]], *, payload: dict[str, Any]) -> dict[str, Any]:
        response_meta = {
            "provider_attempts": provider_attempts,
            "attempt_count": len([attempt for attempt in provider_attempts if attempt.get("status") != "skipped"]),
        }
        choices = payload.get("choices") or []
        if choices:
            response_meta["finish_reason"] = choices[0].get("finish_reason")
        if payload.get("usage") is not None:
            response_meta["usage"] = payload["usage"]
        return response_meta

    def _set_response_meta(self, request: Any, response_meta: dict[str, Any]) -> None:
        if not request:
            return
        audit_context = getattr(request.state, "audit_context", {})
        audit_context["response_meta"] = response_meta
        request.state.audit_context = audit_context

    def _litellm_request_error(self, exc: Exception, *, provider: str, model: str, request_type: str) -> HTTPException:
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
        detail = str(exc)
        return HTTPException(status_code=status_code, detail=detail)

    async def _fetch_completion(self, *, messages: list[dict[str, Any]], request_params: Mapping[str, Any], provider_preference: str | None, request: Any = None) -> dict[str, Any]:
        if provider_preference and provider_preference not in _SUPPORTED_COMPLETION_PROVIDERS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported provider '{provider_preference}'")

        providers = [provider_preference] if provider_preference else list(constants.COMPLETION_PROVIDERS)
        provider_attempts = self._provider_attempts(request)
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
                    self._set_response_meta(request, self._response_meta(provider_attempts, payload={}))
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
                    self._set_response_meta(request, self._response_meta(provider_attempts, payload={}))
                    if isinstance(exc, HTTPException):
                        raise
                    if isinstance(exc, _LITELLM_REQUEST_ERRORS):
                        raise self._litellm_request_error(
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

            provider_attempts.append({"provider": resolved_provider, "model": model, "status": "succeeded"})
            self._set_response_meta(request, self._response_meta(provider_attempts, payload=payload))
            return payload

        self._set_response_meta(request, self._response_meta(provider_attempts, payload={}))
        if last_error is not None:
            if isinstance(last_error, _LITELLM_REQUEST_ERRORS):
                last_attempt = next((attempt for attempt in reversed(provider_attempts) if attempt.get("status") == "failed"), None)
                raise self._litellm_request_error(
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

    async def _fetch_embedding(self, *, input_data: str | list[str], request_params: Mapping[str, Any], provider_preference: str | None, request: Any = None) -> dict[str, Any]:
        if not provider_preference:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-LLM-Provider header is required for embeddings",
            )
        if provider_preference not in _SUPPORTED_EMBEDDING_PROVIDERS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported embedding provider '{provider_preference}'")

        provider_attempts = self._provider_attempts(request)
        adapter = get_adapter(provider_preference, redis=redis_client, request=request)
        resolved_provider = adapter._provider_name
        model = adapter._embedding_model

        if await adapter.is_circuit_open():
            provider_attempts.append(
                {"provider": resolved_provider, "model": model, "status": "skipped", "reason": "circuit_open"}
            )
            self._set_response_meta(request, self._response_meta(provider_attempts, payload={}))
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
            self._set_response_meta(request, self._response_meta(provider_attempts, payload={}))
            if isinstance(exc, HTTPException):
                raise
            if isinstance(exc, _LITELLM_REQUEST_ERRORS):
                raise self._litellm_request_error(
                    exc,
                    provider=resolved_provider,
                    model=model,
                    request_type="embeddings",
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Provider '{resolved_provider}' failed",
            ) from exc

        provider_attempts.append(
            {"provider": resolved_provider, "model": model, "status": "succeeded"}
        )
        self._set_response_meta(request, self._response_meta(provider_attempts, payload=payload))
        return payload
