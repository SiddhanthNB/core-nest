from __future__ import annotations

import pytest

from lib.utils.provider_health import provider_health_check


@pytest.mark.asyncio
async def test_provider_health_check_uses_policy_provider_sets(mocker) -> None:
    mocker.patch("lib.utils.provider_health.constants.COMPLETION_PROVIDERS", ("mistral", "google"))
    mocker.patch("lib.utils.provider_health.constants.EMBEDDING_PROVIDERS", ("google", "openrouter"))
    check_completion = mocker.patch(
        "lib.utils.provider_health._check_completion",
        side_effect=[
            {"provider": "mistral", "status": "success", "latency_ms": 1, "result": {}},
            {"provider": "google", "status": "failure", "latency_ms": 2, "error": "boom"},
        ],
    )
    check_embedding = mocker.patch(
        "lib.utils.provider_health._check_embedding",
        side_effect=[
            {"provider": "google", "status": "success", "latency_ms": 3},
            {"provider": "openrouter", "status": "success", "latency_ms": 4},
        ],
    )
    write_summary = mocker.patch("lib.utils.provider_health._write_summary")

    results, any_failures = await provider_health_check(write_summary=True)

    assert [item["provider"] for item in results["completions"]] == ["mistral", "google"]
    assert [item["provider"] for item in results["embeddings"]] == ["google", "openrouter"]
    assert any_failures is True
    assert check_completion.await_count == 2
    assert check_embedding.await_count == 2
    write_summary.assert_called_once_with(results)


@pytest.mark.asyncio
async def test_provider_health_check_records_unexpected_check_exceptions(mocker) -> None:
    mocker.patch("lib.utils.provider_health.constants.COMPLETION_PROVIDERS", ("openrouter",))
    mocker.patch("lib.utils.provider_health.constants.EMBEDDING_PROVIDERS", ())
    mocker.patch("lib.utils.provider_health._check_completion", side_effect=RuntimeError("boom"))
    write_summary = mocker.patch("lib.utils.provider_health._write_summary")

    results, any_failures = await provider_health_check(write_summary=True)

    assert results["completions"][0]["provider"] == "openrouter"
    assert results["completions"][0]["status"] == "failure"
    assert "RuntimeError: boom" in results["completions"][0]["error"]
    assert any_failures is True
    write_summary.assert_called_once_with(results)
