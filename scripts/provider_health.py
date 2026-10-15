# /// script
# requires-python = ">=3.12"
# dependencies = ["requests==2.33.1", "pyyaml==6.0.2"]
# ///
"""
Smoke-test the deployed CoreNest API as an external client, once per enabled provider.
Standalone on purpose: no app imports, only CORE_NEST_API_KEY (and optionally CORE_NEST_URL) required.
Writes Markdown to $GITHUB_STEP_SUMMARY when set (stdout otherwise) and exits non-zero on any failure.
"""

import os
import sys
import time
from pathlib import Path

import requests
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_PROVIDERS = yaml.safe_load((_ROOT / "app/config/llm_providers.yaml").read_text())["providers"]
_ALIAS_PREFIX = "core-nest/"
_PING_TIMEOUT = 90  # free Render instances take ~1 min to wake
_CALL_TIMEOUT = 100  # service deadline is 90s


def _enabled(kind: str) -> list[str]:
    return [name for name, config in _PROVIDERS.items() if config.get("enabled", True) and config.get("models", {}).get(kind)]  # fmt: skip


def _error(response: requests.Response) -> str:
    try:
        return response.json()["error"]["message"]
    except Exception:
        return response.text[:200] or response.reason


def _check(session: requests.Session, base_url: str, path: str, body: dict) -> dict:
    started = time.perf_counter()
    row = {"model": body["model"]}
    try:
        response = session.post(f"{base_url}{path}", json=body, timeout=_CALL_TIMEOUT)
        row |= {"ok": response.ok, "status": response.status_code, "backend": response.headers.get("X-LLM-Backend"), "request_id": response.headers.get("X-Request-ID")}  # fmt: skip
        if not response.ok:
            row["error"] = _error(response)
    except requests.RequestException as exc:
        row |= {"ok": False, "status": None, "error": f"{type(exc).__name__}: {exc}"}
    row["latency_ms"] = int((time.perf_counter() - started) * 1000)
    return row


def _completion(model: str) -> dict:
    return {"model": model, "messages": [{"role": "user", "content": "Reply with exactly: pong"}]}


def _embedding(model: str) -> dict:
    return {"model": model, "input": ["ping", "pong"]}


def _section(title: str, rows: list[dict]) -> list[str]:
    lines = [f"### {title}", "", "| Model | Status | Latency | Backend | Details |", "| --- | --- | --- | --- | --- |"]
    for row in rows:
        status = f"{'Success' if row['ok'] else 'Failure'} ({row['status'] or 'no response'})"
        details = row.get("error") or f"request `{row.get('request_id')}`"
        cells = [f"`{row['model']}`", status, f"{row['latency_ms']}ms", f"`{row.get('backend') or '-'}`", details]
        lines.append("| " + " | ".join(str(cell).replace("|", "\\|").replace("\n", " ") for cell in cells) + " |")
    return lines + [""]


def _write_summary(lines: list[str]) -> None:
    content = "\n".join(["## Provider Health Check", "", *lines]) + "\n"
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(content)
    print(content)


def main() -> int:
    base_url = os.getenv("CORE_NEST_URL", "https://core-nest.onrender.com").rstrip("/")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {os.environ['CORE_NEST_API_KEY']}"

    try:
        requests.get(f"{base_url}/ping", timeout=_PING_TIMEOUT).raise_for_status()
    except requests.RequestException as exc:
        _write_summary([f"**Fatal:** `{base_url}/ping` failed: {type(exc).__name__}: {exc}"])
        return 1

    sections = {
        "Completions": [_check(session, base_url, "/v1/chat/completions", _completion(f"{_ALIAS_PREFIX}{name}")) for name in _enabled("completion")],  # fmt: skip
        "Embeddings": [_check(session, base_url, "/v1/embeddings", _embedding(f"{_ALIAS_PREFIX}{name}")) for name in _enabled("embedding")],  # fmt: skip
        "Auto Routing": [_check(session, base_url, "/v1/chat/completions", _completion(f"{_ALIAS_PREFIX}auto"))],
    }
    _write_summary([line for title, rows in sections.items() for line in _section(title, rows)])
    return 0 if all(row["ok"] for rows in sections.values() for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
