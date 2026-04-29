import uvicorn

from app.api.core.startup_checks import ensure_no_pending_migrations
from app.config import constants


def run() -> None:
    ensure_no_pending_migrations()

    local_env = constants.APP_ENV.lower() == "development"
    uvicorn_conf = {
        "factory": True,
        "host": "0.0.0.0",
        "port": constants.APP_PORT,
        "reload": local_env,
        "workers": None if local_env else constants.WEB_CONCURRENCY,
    }
    uvicorn.run("app.api.core.factory:create_app", **uvicorn_conf)
