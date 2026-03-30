from __future__ import annotations

from typing import Any

from duo_orm import Database

from app.config import constants

_ENGINE_KWARGS: dict[str, Any] = {
    "pool_size": 5,
    "pool_recycle": 3600,
    "max_overflow": 10,
    "pool_pre_ping": True,
    "pool_timeout": 30,
    "connect_args": {
        "application_name": constants.PROJECT_NAME,
        "prepare_threshold": None,
    },
}

db = Database(constants.SUPABASE_DB_URL, engine_kwargs=_ENGINE_KWARGS)
