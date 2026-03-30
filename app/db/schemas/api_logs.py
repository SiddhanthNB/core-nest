from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class APILog:
    class Create(BaseModel):
        path: str
        method: str
        success: bool
        status_code: int | None = None
        process_time: float | None = None
        rq_params: dict[str, Any]

    class Update(BaseModel):
        success: bool | None = None
        status_code: int | None = None
        process_time: float | None = None
        rq_params: dict[str, Any] | None = None

    class Read(BaseModel):
        id: int
        path: str
        method: str
        success: bool
        status_code: int | None
        process_time: float | None
        rq_params: dict[str, Any]
        created_at: datetime
        updated_at: datetime

        model_config = ConfigDict(from_attributes=True)
