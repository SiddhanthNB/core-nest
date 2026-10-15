import asyncio

from invoke.collection import Collection
from invoke.tasks import task

from lib.utils import clients

_LIMIT_HELP = {
    "per_minute": "Requests per minute",
    "per_hour": "Requests per hour",
    "per_day": "Requests per day",
    "concurrent": "Concurrent requests",
}


def _limits(per_minute, per_hour, per_day, concurrent) -> dict[str, int | None]:
    values = {"requests_per_minute": per_minute, "requests_per_hour": per_hour, "requests_per_day": per_day, "concurrent_requests_limit": concurrent}  # fmt: skip
    return {field: int(value) if value is not None else None for field, value in values.items()}


@task(help={"name": "Client name", **_LIMIT_HELP})
def create(ctx, name, per_minute=None, per_hour=None, per_day=None, concurrent=None):
    """
    Create a client with rate limits (defaults for any limit not given). Prints the API key once.
    """
    asyncio.run(clients.create_client(name, **_limits(per_minute, per_hour, per_day, concurrent)))


@task(help={"name": "Client name"})
def get(ctx, name):
    """
    Show a client's status and rate limits. The API key cannot be shown; use update --rotate-key.
    """
    asyncio.run(clients.get_client(name))


@task(help={"name": "Client name", "activate": "Activate the client", "deactivate": "Deactivate the client", "rotate_key": "Issue a new API key (printed once); the old one stops working", **_LIMIT_HELP})  # fmt: skip
def update(ctx, name, per_minute=None, per_hour=None, per_day=None, concurrent=None, activate=False, deactivate=False, rotate_key=False):  # fmt: skip
    """
    Change a client's rate limits, status or API key. Takes effect immediately.
    """
    asyncio.run(clients.update_client(name, activate=activate, deactivate=deactivate, rotate_key=rotate_key, **_limits(per_minute, per_hour, per_day, concurrent)))  # fmt: skip


@task(help={"name": "Client name"})
def delete(ctx, name):
    """
    Delete a client and its rate limits. Takes effect immediately; audit logs are kept.
    """
    asyncio.run(clients.delete_client(name))


@task(name="list")
def list_(ctx):
    """
    List all clients with status and rate limits.
    """
    asyncio.run(clients.list_clients())


clients_ns = Collection("clients")
for _task in (create, get, update, delete, list_):
    clients_ns.add_task(_task)
