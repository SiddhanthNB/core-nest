from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, UUID4


class RateLimitConfig:
    class Create(BaseModel):
        client_id: UUID4
        requests_per_minute: int | None = None
        requests_per_hour: int | None = None
        requests_per_day: int | None = None
        concurrent_requests_limit: int | None = None

    class Update(BaseModel):
        requests_per_minute: int | None = None
        requests_per_hour: int | None = None
        requests_per_day: int | None = None
        concurrent_requests_limit: int | None = None

    class Read(BaseModel):
        id: int
        client_id: UUID4
        requests_per_minute: int | None
        requests_per_hour: int | None
        requests_per_day: int | None
        concurrent_requests_limit: int | None
        created_at: datetime
        updated_at: datetime

        model_config = ConfigDict(from_attributes=True)
