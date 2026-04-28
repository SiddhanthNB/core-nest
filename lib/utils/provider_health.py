from __future__ import annotations

import os
import time
from typing import Any

from app.config import constants
from lib.llm.adapters import BaseAdapter, get_adapter


async def _check_completion(provider: str, adapter: BaseAdapter) -> dict[str, Any]:
    started = time.perf_counter()
    try:
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
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": provider,
            "status": "failure",
            "latency_ms": latency_ms,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _check_embedding(provider: str, adapter: BaseAdapter) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        await adapter.aembedding(
            input_data=["ping", "pong"],
            request_params={},
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": provider,
            "status": "success",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": provider,
            "status": "failure",
            "latency_ms": latency_ms,
            "error": f"{type(exc).__name__}: {exc}",
        }


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
            if len(details) > 200:
                details = details[:200] + "...(truncated)"
        lines.append(f"| {item['provider']} | {status_icon} | {details} |")
    lines.append("")
    return lines


def _format_summary(results: dict[str, list[dict[str, Any]]]) -> str:
    lines: list[str] = []
    lines.append("## Provider Health Check")
    lines.append("")
    lines.extend(_format_section("Completions", results.get("completions", [])))
    lines.extend(_format_section("Embeddings", results.get("embeddings", [])))
    return "\n".join(lines)


def _write_summary(results: dict[str, list[dict[str, Any]]]) -> None:
    content = _format_summary(results)
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(content + "\n")
    else:
        print(content)


async def run_provider_health_check(write_summary: bool = True):
    results: dict[str, list[dict[str, Any]]] = {"completions": [], "embeddings": []}

    for provider in constants.PROVIDERS:
        adapter = get_adapter(provider)
        if adapter.has_capability("chat"):
            results["completions"].append(await _check_completion(provider, adapter))
        if adapter.has_capability("embedding"):
            results["embeddings"].append(await _check_embedding(provider, adapter))

    if write_summary:
        _write_summary(results)

    any_failures = any(
        item["status"] == "failure"
        for section in results.values()
        for item in section
    )
    return results, any_failures
