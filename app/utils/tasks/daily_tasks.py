import asyncio
from invoke.tasks import task
from invoke.collection import Collection
from app.utils.helpers.provider_health import run_provider_health_check


@task()
def provider_health_check(ctx):
    """
    Run provider completion health checks against all configured adapters.
    Writes Markdown results to $GITHUB_STEP_SUMMARY when available and exits non-zero on failure.
    """
    try:
        _, any_failures = asyncio.run(run_provider_health_check(write_summary=True))
    except Exception as exc:
        print(f"Provider health check failed: {exc}")
        raise SystemExit(1)
    if any_failures:
        raise SystemExit(1)

daily_tasks_ns = Collection('daily-tasks')
daily_tasks_ns.add_task(provider_health_check, 'provider-health-check')
