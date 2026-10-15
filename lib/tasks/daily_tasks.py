import asyncio

from invoke.collection import Collection
from invoke.tasks import task

from lib.utils.audit_cleanup import cleanup_audit_logs


@task()
def cleanup_audit_logs_task(ctx, retention_days: int = 60):
    """
    Delete audit rows older than the configured retention window.
    """
    deleted = asyncio.run(cleanup_audit_logs(retention_days=retention_days))
    print(f"Deleted {deleted} audit log rows older than {retention_days} days")


daily_tasks_ns = Collection("daily-tasks")
daily_tasks_ns.add_task(cleanup_audit_logs_task, "cleanup-audit-logs")
