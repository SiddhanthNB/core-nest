from invoke.collection import Collection
from app.utils.tasks.one_time_tasks import one_time_tasks_ns
from app.utils.tasks.daily_tasks import daily_tasks_ns

ns = Collection()
ns.add_collection(one_time_tasks_ns)
ns.add_collection(daily_tasks_ns)
ns.configure({'run': {'echo': True}})
