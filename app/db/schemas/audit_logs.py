from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, UUID4


class AuditLog:
    class Create(BaseModel):
        request_id: UUID4
        path: str
        method: str
        client_id: UUID4 | None = None
        provider: str | None = None
        model: str | None = None
        success: bool
        status_code: int | None = None
        process_time_ms: float | None = None
        error: str | None = None
        request_meta: dict[str, Any]
        response_meta: dict[str, Any]

    class Update(BaseModel):
        provider: str | None = None
        model: str | None = None
        success: bool | None = None
        status_code: int | None = None
        process_time_ms: float | None = None
        error: str | None = None
        request_meta: dict[str, Any] | None = None
        response_meta: dict[str, Any] | None = None

    class Read(BaseModel):
        request_id: UUID4
        path: str
        method: str
        client_id: UUID4 | None
        provider: str | None
        model: str | None
        success: bool
        status_code: int | None
        process_time_ms: float | None
        error: str | None
        request_meta: dict[str, Any]
        response_meta: dict[str, Any]
        created_at: datetime

        model_config = ConfigDict(from_attributes=True)
