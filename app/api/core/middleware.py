import json
import time
import uuid
from typing import Any, Callable
from fastapi import FastAPI
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import constants
from app.config.logger import logger
from app.db.models.audit_logs import AuditLog

class _APILoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        start = time.perf_counter()
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request_body = await self._request_json(request)
        request.state.audit_context = self._build_audit_context(
            request=request,
            request_id=request_id,
            request_body=request_body,
        )
        request_logger = logger.bind(
            event="request_started",
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )
        request_logger.info("Request started")

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.bind(
                event="unexpected_error",
                request_id=request_id,
                path=request.url.path,
                method=request.method,
                error_type=type(exc).__name__,
            ).error(
                f"Unhandled request failure for {request.url.path}",
                exc_info=True,
            )
            response = JSONResponse(
                content={"detail": "Internal Server Error"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        process_time_ms = round((time.perf_counter() - start) * 1000, 2)
        log_event = "request_failed" if response.status_code >= 500 else "request_completed"
        logger.bind(
            event=log_event,
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            latency_ms=process_time_ms,
        ).info(f"Request finished with status {response.status_code}")

        existing_background = response.background
        response.background = BackgroundTask(
            self._run_background_tasks,
            existing_background,
            request,
            process_time_ms,
            response.status_code,
        )

        return response

    async def _run_background_tasks(
        self,
        existing_background: BackgroundTask | None,
        request: Request,
        process_time_ms: float,
        status_code: int,
    ) -> None:
        if existing_background is not None:
            await existing_background()
        await self._push_log_into_db(
            request=request,
            process_time_ms=process_time_ms,
            status_code=status_code,
        )

    async def _push_log_into_db(
        self,
        *,
        request: Request,
        process_time_ms: float,
        status_code: int,
    ) -> None:
        try:
            if request.url.path == "/ping" and request.method.lower() == "get":
                return

            if constants.APP_ENV.lower() == "development":
                return

            if status_code == status.HTTP_401_UNAUTHORIZED:
                return

            audit_context = getattr(request.state, "audit_context", {})
            response_meta = dict(audit_context.get("response_meta") or {})
            response_meta.setdefault("provider_attempts", [])
            response_meta.setdefault(
                "attempt_count",
                len([attempt for attempt in response_meta["provider_attempts"] if attempt.get("status") != "skipped"]),
            )
            final_attempt = next(
                (attempt for attempt in reversed(response_meta["provider_attempts"]) if attempt.get("status") == "succeeded"),
                None,
            )
            last_failed_attempt = next(
                (attempt for attempt in reversed(response_meta["provider_attempts"]) if attempt.get("status") == "failed"),
                None,
            )
            audit_payload = {
                "request_id": audit_context.get("request_id"),
                "request_meta": audit_context.get("request_meta", {}),
                "response_meta": response_meta,
            }

            client = getattr(request.state, "client", None)
            await AuditLog.acreate(
                request_id=uuid.UUID(str(audit_context["request_id"])),
                path=request.url.path,
                method=request.method,
                client_id=getattr(client, "id", None),
                provider=(final_attempt or last_failed_attempt or {}).get("provider"),
                model=(final_attempt or last_failed_attempt or {}).get("model"),
                success=status_code < 400,
                status_code=status_code,
                process_time_ms=process_time_ms,
                error=(last_failed_attempt or {}).get("error") or (f"HTTP {status_code}" if status_code >= 400 else None),
                request_meta=audit_payload["request_meta"],
                response_meta=audit_payload["response_meta"],
            )
        except Exception as e:
            logger.bind(event="audit_log_failed").error(f"Error saving API log to database: {str(e)}", exc_info=True)

    async def _request_json(self, request: Request) -> dict[str, Any]:
        try:
            request_body = await request.body()
            if not request_body:
                return {}
            payload = json.loads(request_body)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _build_audit_context(self, *, request: Request, request_id: str, request_body: dict[str, Any]) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "request_meta": self._request_meta(request, request_body),
            "response_meta": {
                "provider_attempts": [],
            },
        }

    def _request_meta(self, request: Request, request_body: dict[str, Any]) -> dict[str, Any]:
        request_meta: dict[str, Any] = {
            "provider_pref": request.headers.get("X-LLM-Provider"),
        }
        for key in ("stream", "temperature", "max_tokens", "top_p"):
            if request_body.get(key) is not None:
                request_meta[key] = request_body[key]
        if isinstance(request_body.get("messages"), list):
            request_meta["message_count"] = len(request_body["messages"])
        if isinstance(request_body.get("tools"), list):
            request_meta["tool_count"] = len(request_body["tools"])
        if request_body.get("input") is not None:
            request_meta["input_count"] = len(request_body["input"]) if isinstance(request_body["input"], list) else 1
        return request_meta

def register_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(_APILoggerMiddleware)
