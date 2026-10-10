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


def _validation_error_code(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid_request"

    first_error = errors[0]
    error_type = str(first_error.get("type") or "")
    if error_type == "missing":
        return "missing_field"
    return "invalid_value"


def _normalized_validation_error(exc: RequestValidationError) -> tuple[str, str | None, str]:
    errors = exc.errors()
    if not errors:
        return "Invalid request body", None, "invalid_request"

    first_error = errors[0]
    loc = first_error.get("loc") or ()
    param = next((str(part) for part in reversed(loc) if part not in {"body", "query", "path", "header"}), None)
    message = str(first_error.get("msg") or "Invalid request body")
    error_type = str(first_error.get("type") or "")
    if error_type == "missing" and param:
        return f"Missing required field '{param}'", param, "missing_field"
    if param:
        return f"Invalid value for '{param}': {message}", param, "invalid_value"
    return message, None, "invalid_value"


def _http_error_type(status_code: int) -> str:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return "authentication_error"
    if status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        return "service_unavailable_error"
    return "invalid_request_error"


def _http_error_metadata(status_code: int, message: str) -> tuple[str | None, str | None]:
    if "Unsupported model '" in message:
        return "model", "unsupported_model"
    if "Streaming is not supported" in message:
        return "stream", "unsupported_streaming"
    if "Only n=1 is supported" in message:
        return "n", "unsupported_n"
    if "logprobs=true is not supported" in message:
        return "logprobs", "unsupported_logprobs"
    if "top_logprobs is not supported" in message:
        return "top_logprobs", "unsupported_top_logprobs"
    if "Invalid or missing Authorization header" in message:
        return None, "missing_authorization_header"
    if "Invalid or inactive API Key" in message:
        return None, "invalid_api_key"
    if "circuit is open" in message and status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        return None, "provider_circuit_open"
    if "returned invalid JSON" in message and status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        return None, "invalid_provider_response"
    if "No provider could satisfy the request" in message and status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        return None, "provider_unavailable"
    if "'messages' must include at least one message" in message:
        return "messages", "invalid_messages"
    if "'messages' must include at least one user message" in message:
        return "messages", "invalid_messages"
    if "System messages are not allowed" in message:
        return "messages", "unsupported_system_message"
    if "At least one string must be provided in 'input'" in message:
        return "input", "invalid_input"
    return None, None


def _alembic_config() -> Config:
    return Config(str(_ALEMBIC_INI_PATH))


def _current_revision(*, version_table: str) -> str | None:
    with db.sync_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"version_table": version_table})
        return context.get_current_revision()


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        message, param, code = _normalized_validation_error(exc)
        return JSONResponse(
            content=_openai_error(message, type_="invalid_request_error", param=param, code=code),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            return JSONResponse(content=detail, status_code=exc.status_code, headers=exc.headers)

        if isinstance(detail, dict):
            message = str(detail.get("detail") or detail.get("message") or "Request failed")
            error_type = str(detail.get("type") or _http_error_type(exc.status_code))
            param = detail.get("param")
            code = detail.get("code")
        else:
            message = str(detail)
            error_type = _http_error_type(exc.status_code)
            param = None
            code = None

        inferred_param, inferred_code = _http_error_metadata(exc.status_code, message)
        param = param if param is not None else inferred_param
        code = code if code is not None else inferred_code

        return JSONResponse(
            content=_openai_error(message, type_=error_type, param=param, code=code),
            status_code=exc.status_code,
            headers=exc.headers,
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
