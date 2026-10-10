from __future__ import annotations

import json
import re
import time
from typing import Any

from app.config import constants
from app.config.redis import redis_client
from app.config.tracing import tracer
from lib.llm.adapters import get_adapter

_MAX_REASON_LENGTH = 160
_USER_ID_PATTERN = re.compile(r',?\s*"user_id"\s*:\s*"[^"]*"')


def _model_for(provider: str, kind: str) -> str | None:
    return constants.PROVIDERS.get(provider, {}).get("models", {}).get(kind)


def _attempts_for(adapter: Any) -> int:
    return int(getattr(adapter, "_attempt_number", 0) or 0)


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


def _short_error(exc: Exception) -> str:
    text = _USER_ID_PATTERN.sub("", str(exc))
    reason = _provider_error_message(text) or text
    reason = " ".join(reason.split())
    if len(reason) > _MAX_REASON_LENGTH:
        reason = reason[: _MAX_REASON_LENGTH - 3] + "..."
    status_code = getattr(exc, "status_code", None)
    if status_code:
        return f"{type(exc).__name__} {status_code}: {reason}"
    return f"{type(exc).__name__}: {reason}"


def _failure_result(provider: str, started: float, exc: Exception, *, model: str | None = None, attempts: int = 0) -> dict[str, Any]:  # fmt: skip
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "provider": provider,
        "status": "failure",
        "latency_ms": latency_ms,
        "model": model,
        "attempts": attempts,
        "error": _short_error(exc),
    }


async def _check_completion(provider: str) -> dict[str, Any]:
    started = time.perf_counter()
    model = _model_for(provider, "completion")
    adapter = None
    try:
        adapter = get_adapter(provider, redis=redis_client)
        result = await adapter.acompletion(
            messages=[
                {"role": "system", "content": "You are a concise health-check responder."},
                {"role": "user", "content": f"Reply with exactly: pong from ({provider})."},
            ],
            request_params={"temperature": 0, "stream": False},
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": provider,
            "status": "success",
            "latency_ms": latency_ms,
            "model": model,
            "attempts": _attempts_for(adapter),
            "result": result.model_dump(exclude_none=True) if hasattr(result, "model_dump") else result,
        }
    except Exception as exc:
        return _failure_result(provider, started, exc, model=model, attempts=_attempts_for(adapter))


async def _check_embedding(provider: str) -> dict[str, Any]:
    started = time.perf_counter()
    model = _model_for(provider, "embedding")
    adapter = None
    try:
        adapter = get_adapter(provider, redis=redis_client)
        await adapter.aembedding(input_data=["ping", "pong"], request_params={})
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": provider,
            "status": "success",
            "latency_ms": latency_ms,
            "model": model,
            "attempts": _attempts_for(adapter),
        }
    except Exception as exc:
        return _failure_result(provider, started, exc, model=model, attempts=_attempts_for(adapter))


def _format_latency(latency_ms: int) -> str:
    if latency_ms >= 1000:
        return f"{latency_ms / 1000:.1f}s"
    return f"{latency_ms}ms"


def _format_details(item: dict[str, Any]) -> str:
    if item["status"] == "success":
        parts = ["ok", _format_latency(item.get("latency_ms", 0))]
    else:
        parts = [item.get("error", "unknown error")]
    if item.get("model"):
        parts.append(f"`{item['model']}`")
    attempts = item.get("attempts", 0)
    if attempts:
        parts.append(f"{attempts} attempt{'s' if attempts != 1 else ''}")
    return " · ".join(parts).replace("|", "\\|")


def _format_section(title: str, results: list[dict[str, Any]]) -> list[str]:
    if not results:
        return []

    lines = [f"### {title}", ""]
    lines.append("| Provider | Status | Details |")
    lines.append("| --- | --- | --- |")
    for item in results:
        status_icon = "Success" if item["status"] == "success" else "Failure"
        lines.append(f"| {item['provider']} | {status_icon} | {_format_details(item)} |")
    lines.append("")
    return lines


def _format_summary(results: dict[str, list[dict[str, Any]]]) -> str:
    lines = ["## Provider Health Check", ""]
    lines.extend(_format_section("Completions", results.get("completions", [])))
    lines.extend(_format_section("Embeddings", results.get("embeddings", [])))
    lines.extend(_format_section("Fatal Errors", results.get("fatal_errors", [])))
    return "\n".join(lines)


def _write_summary(results: dict[str, list[dict[str, Any]]]) -> None:
    content = _format_summary(results)
    summary_path = constants.GITHUB_STEP_SUMMARY
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(content + "\n")
    else:
        print(content)


async def _run_checks(providers: tuple[str, ...], check: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for provider in providers:
        started = time.perf_counter()
        with tracer.start_as_current_span(f"{check.__name__.removeprefix('_check_')} health check {provider}", attributes={"gen_ai.provider.name": provider}) as span:  # fmt: skip
            try:
                results.append(await check(provider))
            except Exception as exc:
                results.append(_failure_result(provider, started, exc))
            span.set_attribute("outcome", "succeeded" if results[-1]["status"] == "success" else "failed")
    return results


async def provider_health_check(write_summary: bool = True):
    results = {
        "completions": await _run_checks(constants.COMPLETION_PROVIDERS, _check_completion),
        "embeddings": await _run_checks(constants.EMBEDDING_PROVIDERS, _check_embedding),
    }

    if write_summary:
        _write_summary(results)

    any_failures = any(item["status"] == "failure" for section in results.values() for item in section)
    return results, any_failures
