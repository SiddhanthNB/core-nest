from __future__ import annotations

import logging
import sys

from app.config import constants


def _configure_logger() -> logging.Logger:
    log_level = logging.INFO if constants.APP_ENV.lower() == "production" else logging.DEBUG

    formatter = logging.Formatter(
        f"[%(asctime)s] [%(levelname)s] [{constants.PROJECT_NAME}] : %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.__stdout__)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)
    root_logger.addHandler(handler)

    configured_logger = logging.getLogger(constants.PROJECT_NAME)
    configured_logger.handlers.clear()
    configured_logger.setLevel(log_level)
    configured_logger.propagate = True

    return configured_logger


logger = _configure_logger()
