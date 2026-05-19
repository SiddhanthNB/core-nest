import uvicorn

from app.api.core._helpers import ensure_no_pending_migrations
from app.config import constants


def run() -> None:
    ensure_no_pending_migrations()

    uvicorn_config = {
        "factory": True,
        "host": "0.0.0.0",
        "port": constants.APP_PORT,
        "access_log": False,
        "log_config": None,
        "log_level": "warning",
    }

    if constants.APP_ENV.lower() == "development":
        uvicorn_config["reload"] = True
        uvicorn_config["workers"] = 1
    else:
        uvicorn_config["reload"] = False
        uvicorn_config["workers"] = constants.WEB_CONCURRENCY

    uvicorn.run("app.api.core.factory:create_app", **uvicorn_config)
