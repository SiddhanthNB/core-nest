from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, status

from app.config import constants
from app.config.redis import redis_client
from lib.llm.adapters import get_adapter

_COMPLETION_PROVIDER_SEQUENCE = (
    "openai",
    "mistral",
    "gemini",
    "groq",
    "openrouter",
    "cerebras",
    "huggingface",
)
_SUPPORTED_PROVIDERS = set(constants.PROVIDERS) | {"google"}


class BaseService:
    def _get_prompts(self, prompt_type: str, **kwargs):
        base_path = constants.PROMPTS_DIR
        system_prompts_path = base_path / "system_prompts"
        user_prompts_path = base_path / "user_prompts"

        def _load_and_format(file_path, **format_kwargs):
            return file_path.read_text().strip().format(**format_kwargs)

        system_prompt = _load_and_format(system_prompts_path / f"{prompt_type}.txt", **kwargs)
        user_prompt = _load_and_format(user_prompts_path / f"{prompt_type}.txt", **kwargs)
        return {"system_prompt": system_prompt, "user_prompt": user_prompt}

    def _message(self, role: str, content: str) -> dict[str, str]:
        return {"role": role, "content": content}

    def _system_messages(self, *, app_system_prompt: str, user_system_prompt: str | None = None) -> list[dict[str, str]]:
        messages = [self._message("system", app_system_prompt)]
        if user_system_prompt:
            messages.append(self._message("system", user_system_prompt))
        return messages

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

    async def _fetch_completion(self, *, messages: list[dict[str, Any]], request_params: Mapping[str, Any], provider_preference: str | None, request: Any = None) -> dict[str, Any]:
        if provider_preference and provider_preference not in _SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported provider '{provider_preference}'")

        providers = [provider_preference] if provider_preference else list(_COMPLETION_PROVIDER_SEQUENCE)
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
                adapter.validate_params("completion", request_params)
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
                detail="provider_preference is required for embeddings",
            )
        if provider_preference not in _SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported provider '{provider_preference}'")

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
            adapter.validate_params("embedding", request_params)
            payload = await adapter.aembedding(input_data=input_data, request_params=request_params)
        except Exception as exc:
            provider_attempts.append(
                {"provider": resolved_provider, "model": model, "status": "failed", "error": type(exc).__name__}
            )
            self._set_response_meta(request, self._response_meta(provider_attempts, payload={}))
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Provider '{resolved_provider}' failed",
            ) from exc

        provider_attempts.append(
            {"provider": resolved_provider, "model": model, "status": "succeeded"}
        )
        self._set_response_meta(request, self._response_meta(provider_attempts, payload=payload))
        return payload

    def _completion_request_params(self, params: Any) -> dict[str, Any]:
        return {
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
            "top_p": params.top_p,
            "stream": False,
            "stop": params.stop,
            "tools": params.tools,
            "tool_choice": params.tool_choice,
            "response_format": params.response_format,
        }
