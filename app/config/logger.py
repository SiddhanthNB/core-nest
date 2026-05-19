from __future__ import annotations

import logging
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.config import constants


def _log_file_path(timestamp: str) -> Path:
    return constants.REPO_ROOT / "logs" / f"{constants.PROJECT_NAME}.{timestamp}.log"


def _rotated_log_file_name(default_name: str) -> str:
    return str(_log_file_path(default_name.rsplit(".", 1)[-1]))


def _configure_logger() -> logging.Logger:
    log_level = logging.INFO if constants.APP_ENV.lower() == "production" else logging.DEBUG

    formatter = logging.Formatter(
        f"[%(asctime)s] [%(levelname)s] [{constants.PROJECT_NAME}] [pid: %(process)d] : %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setFormatter(formatter)

    logs_dir = constants.REPO_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)

    file_handler = TimedRotatingFileHandler(
        filename=str(_log_file_path(datetime.now().strftime("%Y-%m-%d"))),
        when="midnight",
        interval=1,
        utc=True,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.namer = _rotated_log_file_name
    file_handler.setFormatter(formatter)

    _root_logger = logging.getLogger()
    _root_logger.handlers.clear()
    _root_logger.setLevel(logging.WARNING)
    _root_logger.addHandler(console_handler)

    configured_logger = logging.getLogger(constants.PROJECT_NAME)
    configured_logger.handlers.clear()
    configured_logger.setLevel(log_level)
    configured_logger.addHandler(file_handler)
    configured_logger.propagate = True

    return configured_logger


logger = _configure_logger()
