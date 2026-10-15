from invoke.collection import Collection

from app.config.tracing import configure_tracing
from lib.tasks.client_tasks import clients_ns
from lib.tasks.daily_tasks import daily_tasks_ns
from lib.tasks.dev_tasks import dev_tasks_ns

configure_tracing()

ns = Collection()
ns.add_collection(clients_ns)
ns.add_collection(daily_tasks_ns)
ns.add_collection(dev_tasks_ns)
ns.configure({"run": {"echo": True}})
