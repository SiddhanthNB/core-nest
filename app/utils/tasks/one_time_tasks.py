import asyncio
from invoke.tasks import task
from invoke.collection import Collection
from app.utils.helpers.create_client import create_client as _create_client_helper

@task()
def create_client(ctx, name: str):
    """
    Create a new API client and generate an API key.
    Usage: inv create-client --name "Client Name"
    """
    asyncio.run(_create_client_helper(name))

one_time_tasks_ns = Collection('one-time-tasks')
one_time_tasks_ns.add_task(create_client, 'create-client')
