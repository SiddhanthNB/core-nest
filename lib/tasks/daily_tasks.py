import asyncio
from invoke.tasks import task
from invoke.collection import Collection
from lib.utils.audit_cleanup import cleanup_audit_logs
from lib.utils.provider_health import _write_summary, provider_health_check


@task()
def provider_health_check_task(ctx):
    """
    Run provider health checks against all configured providers.
    Writes Markdown results to $GITHUB_STEP_SUMMARY when available and exits non-zero on failure.
    """
    try:
        _, any_failures = asyncio.run(provider_health_check(write_summary=True))
    except Exception as exc:
        _write_summary(
            {
                "completions": [],
                "embeddings": [],
                "fatal_errors": [
                    {
                        "provider": "provider_health_check",
                        "status": "failure",
                        "latency_ms": 0,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                ],
            }
        )
        print(f"Provider health check failed: {exc}")
        raise SystemExit(1)
    if any_failures:
        raise SystemExit(1)


@task()
def cleanup_audit_logs_task(ctx, retention_days: int = 60):
    """
    Delete audit rows older than the configured retention window.
    """
    deleted = asyncio.run(cleanup_audit_logs(retention_days=retention_days))
    print(f"Deleted {deleted} audit log rows older than {retention_days} days")


daily_tasks_ns = Collection('daily-tasks')
daily_tasks_ns.add_task(provider_health_check_task, 'provider-health-check')
daily_tasks_ns.add_task(cleanup_audit_logs_task, 'cleanup-audit-logs')
