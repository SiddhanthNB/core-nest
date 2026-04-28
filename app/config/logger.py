from __future__ import annotations

import sys
from typing import Any

from loguru import logger as _loguru_logger

from app.config import constants


class _LoggerAdapter:
    def __init__(self):
        self._logger = _configure_logger()

    def bind(self, **kwargs: Any):
        return self._logger.bind(**kwargs)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._log("debug", message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._log("info", message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._log("warning", message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._log("error", message, *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.opt(exception=True).error(message, *args, **kwargs)

    def _log(self, level: str, message: str, *args: Any, **kwargs: Any) -> None:
        exc_info = kwargs.pop("exc_info", False)
        bound_logger = self._logger
        if exc_info:
            bound_logger = bound_logger.opt(exception=True)
        getattr(bound_logger, level)(message, *args, **kwargs)


def _configure_logger():
    _loguru_logger.remove()
    _loguru_logger.add(
        sys.stdout,
        level="INFO" if constants.APP_ENV.lower() == "production" else "DEBUG",
        serialize=constants.APP_ENV.lower() == "production",
        format=(
            "{time:YYYY-MM-DDTHH:mm:ss.SSSZ} | {level} | "
            "{extra[event]} | request_id={extra[request_id]} | {message}"
        ),
    )
    return _loguru_logger.bind(event="-", request_id="-")


logger = _LoggerAdapter()
