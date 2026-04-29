from __future__ import annotations

import os
import time
from typing import Any

from app.config import constants
from app.config.redis import redis_client
from lib.llm.adapters import get_adapter


def _failure_result(provider: str, started: float, exc: Exception) -> dict[str, Any]:
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "provider": provider,
        "status": "failure",
        "latency_ms": latency_ms,
        "error": f"{type(exc).__name__}: {exc}",
    }


async def _check_completion(provider: str) -> dict[str, Any]:
    started = time.perf_counter()
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
            "result": result.model_dump(exclude_none=True) if hasattr(result, "model_dump") else result,
        }
    except Exception as exc:
        return _failure_result(provider, started, exc)


async def _check_embedding(provider: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        adapter = get_adapter(provider, redis=redis_client)
        await adapter.aembedding(input_data=["ping", "pong"], request_params={})
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": provider,
            "status": "success",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        return _failure_result(provider, started, exc)


def _format_section(title: str, results: list[dict[str, Any]]) -> list[str]:
    if not results:
        return []

    lines = [f"### {title}", ""]
    lines.append("| Provider | Status | Details |")
    lines.append("| --- | --- | --- |")
    for item in results:
        status_icon = "Success" if item["status"] == "success" else "Failure"
        if item["status"] == "success":
            details = "ok"
        else:
            raw = item.get("error", "unknown error")
            details = raw.replace("\n", " ").replace("\r", " ")
        lines.append(f"| {item['provider']} | {status_icon} | {details} |")
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
        try:
            results.append(await check(provider))
        except Exception as exc:
            results.append(_failure_result(provider, started, exc))
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
