from __future__ import annotations

from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from duo_orm.migrations.config import get_version_table
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import constants
from app.db import db

_ALEMBIC_INI_PATH = constants.REPO_ROOT / "app" / "db" / "migrations" / "alembic.ini"
_PYPROJECT_PATH = constants.REPO_ROOT / "pyproject.toml"


def _openai_error(message: str, *, type_: str, param: str | None = None, code: str | None = None) -> dict[str, dict[str, Any]]:  # fmt: skip
    return {
        "error": {
            "message": message,
            "type": type_,
            "param": param,
            "code": code,
        }
    }


def _validation_error_message(exc: RequestValidationError) -> tuple[str, str | None]:
    errors = exc.errors()
    if not errors:
        return "Invalid request body", None

    first_error = errors[0]
    loc = first_error.get("loc") or ()
    param = next((str(part) for part in reversed(loc) if part != "body"), None)
    message = first_error.get("msg") or "Invalid request body"
    if param:
        return f"Invalid value for '{param}': {message}", param
    return message, None


def _http_error_type(status_code: int) -> str:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return "authentication_error"
    if status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        return "service_unavailable_error"
    return "invalid_request_error"


def _alembic_config() -> Config:
    return Config(str(_ALEMBIC_INI_PATH))


def _current_revision(*, version_table: str) -> str | None:
    with db.sync_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"version_table": version_table})
        return context.get_current_revision()


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        message, param = _validation_error_message(exc)
        return JSONResponse(
            content=_openai_error(message, type_="invalid_request_error", param=param),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            return JSONResponse(content=detail, status_code=exc.status_code)

        if isinstance(detail, dict):
            message = str(detail.get("detail") or detail.get("message") or "Request failed")
        else:
            message = str(detail)

        return JSONResponse(
            content=_openai_error(message, type_=_http_error_type(exc.status_code)),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_exception(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse(
            content=_openai_error("Internal Server Error", type_="server_error"),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def ensure_no_pending_migrations() -> None:
    config = _alembic_config()
    script = ScriptDirectory.from_config(config)
    version_table = get_version_table(pyproject_path=_PYPROJECT_PATH)
    current_revision = _current_revision(version_table=version_table)
    head_revision = script.get_current_head()
    if current_revision != head_revision:
        raise RuntimeError(f"Pending migrations detected: current={current_revision}, head={head_revision}")
