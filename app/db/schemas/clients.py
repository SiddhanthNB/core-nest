from __future__ import annotations

from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict

from .rate_limit_configs import RateLimitConfig as RateLimitConfigSchema


class Client:
    class Create(BaseModel):
        name: str
        hashed_api_key: str
        is_active: bool = True

    class Update(BaseModel):
        name: str | None = None
        hashed_api_key: str | None = None
        is_active: bool | None = None

    class Read(BaseModel):
        id: UUID4
        name: str
        is_active: bool
        created_at: datetime
        updated_at: datetime
        rate_limit_config: RateLimitConfigSchema.Read | None = None

        model_config = ConfigDict(from_attributes=True)
