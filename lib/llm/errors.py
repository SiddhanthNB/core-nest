from __future__ import annotations

import json
import re

_MAX_REASON_LENGTH = 160
_USER_ID_PATTERN = re.compile(r',?\s*"user_id"\s*:\s*"[^"]*"')


def _provider_error_message(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, str):
        return error
    if not isinstance(error, dict):
        return None
    message = error.get("message")
    raw = (error.get("metadata") or {}).get("raw")
    if isinstance(raw, str) and (not message or message == "Provider returned error"):
        return raw
    return message if isinstance(message, str) else None


def short_error(exc: Exception) -> str:
    text = _USER_ID_PATTERN.sub("", str(exc))
    reason = _provider_error_message(text) or text
    reason = " ".join(reason.split())
    if len(reason) > _MAX_REASON_LENGTH:
        reason = reason[: _MAX_REASON_LENGTH - 3] + "..."
    status_code = getattr(exc, "status_code", None)
    if status_code:
        return f"{type(exc).__name__} {status_code}: {reason}"
    return f"{type(exc).__name__}: {reason}"


def retry_after(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    headers = getattr(exc, "litellm_response_headers", None) or getattr(response, "headers", None)
    return (headers.get("Retry-After") or headers.get("retry-after")) if headers else None
