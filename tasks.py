from invoke.collection import Collection

from app.config.tracing import configure_tracing
from lib.tasks.daily_tasks import daily_tasks_ns
from lib.tasks.dev_tasks import dev_tasks_ns
from lib.tasks.one_time_tasks import one_time_tasks_ns

configure_tracing()

ns = Collection()
ns.add_collection(one_time_tasks_ns)
ns.add_collection(daily_tasks_ns)
ns.add_collection(dev_tasks_ns)
ns.configure({"run": {"echo": True}})
