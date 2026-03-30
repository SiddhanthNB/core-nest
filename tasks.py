from invoke.collection import Collection
from lib.tasks.daily_tasks import daily_tasks_ns
from lib.tasks.one_time_tasks import one_time_tasks_ns

ns = Collection()
ns.add_collection(one_time_tasks_ns)
ns.add_collection(daily_tasks_ns)
ns.configure({'run': {'echo': True}})
