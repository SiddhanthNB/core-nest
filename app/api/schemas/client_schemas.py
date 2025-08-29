from pydantic import BaseModel, UUID4, ConfigDict
from datetime import datetime

class RateLimitConfigOut(BaseModel):
    requests_per_minute: int | None
    requests_per_hour: int | None
    requests_per_day: int | None
    concurrent_requests_limit: int | None

    model_config = ConfigDict(from_attributes=True)

class ClientOut(BaseModel):
    id: UUID4
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    rate_limit_config: RateLimitConfigOut | None = None

    model_config = ConfigDict(from_attributes=True)
