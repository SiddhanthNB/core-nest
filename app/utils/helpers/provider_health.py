import os
import time
from types import SimpleNamespace
from typing import Dict, List, Tuple

from app.adapters import *

_ADAPTERS: Dict[str, type] = {
    "google": GoogleAdapter,
    "groq": GroqAdapter,
    "openrouter": OpenRouterAdapter,
    "minstral": MinstralAdapter,
    "cerebras": CerebrasAdapter,
}

_EMBEDDING_ADAPTERS: Dict[str, type] = {
    "google": GoogleAdapter,
    "minstral": MinstralAdapter,
}


def _build_params(provider: str) -> SimpleNamespace:
    system_prompt = "You are a concise health-check responder."
    user_prompt = (
        f"Reply with exactly: pong from ({provider}). "
        f"Example response: pong from ({provider}). No extra text."
    )
    return SimpleNamespace(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        structured_output=False,
        provider=provider,
    )


async def _check_completion(provider: str, adapter_cls) -> Dict:
    adapter = adapter_cls()
    params = _build_params(provider)
    started = time.perf_counter()
    try:
        result = await adapter.generate_response(params)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": provider,
            "status": "success",
            "latency_ms": latency_ms,
            "result": result,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": provider,
            "status": "failure",
            "latency_ms": latency_ms,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _check_embedding(provider: str, adapter_cls) -> Dict:
    adapter = adapter_cls()
    started = time.perf_counter()
    try:
        # Minimal payload to reduce cost while confirming availability.
        await adapter.generate_embeddings(["ping", "pong"])
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


def _format_section(title: str, results: List[Dict]) -> List[str]:
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


def _format_summary(results: Dict[str, List[Dict]]) -> str:
    lines: List[str] = []
    lines.append("## Provider Health Check")
    lines.append("")
    lines.extend(_format_section("Completions", results.get("completions", [])))
    lines.extend(_format_section("Embeddings", results.get("embeddings", [])))
    return "\n".join(lines)


def _write_summary(results: List[Dict]) -> None:
    content = _format_summary(results)
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    else:
        print(content)


async def run_provider_health_check(write_summary: bool = True) -> Tuple[Dict[str, List[Dict]], bool]:
    """
    Run completion health checks across configured providers.
    Returns (results, any_failures).
    """
    results: Dict[str, List[Dict]] = {"completions": [], "embeddings": []}

    for provider, adapter_cls in _ADAPTERS.items():
        results["completions"].append(await _check_completion(provider, adapter_cls))

    for provider, adapter_cls in _EMBEDDING_ADAPTERS.items():
        results["embeddings"].append(await _check_embedding(provider, adapter_cls))

    if write_summary:
        _write_summary(results)

    any_failures = any(item["status"] != "success" for item in results["completions"]) or any(
        item["status"] != "success" for item in results["embeddings"]
    )
    return results, any_failures
