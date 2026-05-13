from invoke.collection import Collection
from invoke.tasks import task


@task()
def lint(ctx):
    """
    Run code-quality checks with Ruff.
    """
    ctx.run("uv run ruff check .", pty=True)


@task()
def format_code(ctx):
    """
    Format the codebase with Ruff.
    """
    ctx.run("uv run ruff format .", pty=True)


dev_tasks_ns = Collection("dev-tasks")
dev_tasks_ns.add_task(lint, "lint")
dev_tasks_ns.add_task(format_code, "format")
