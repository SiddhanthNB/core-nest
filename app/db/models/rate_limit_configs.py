import uuid
from datetime import datetime

from duo_orm import DateTime, ForeignKey, PG_UUID, mapped_column, relationship

from app.db import db


class RateLimitConfig(db.Model):
    __tablename__ = "corenest__rate_limit_configs"

    # columns
    id: int = mapped_column(primary_key=True, autoincrement=True)
    requests_per_minute: int | None
    requests_per_hour: int | None
    requests_per_day: int | None
    concurrent_requests_limit: int | None
    client_id: uuid.UUID = mapped_column(PG_UUID(as_uuid=True), ForeignKey("corenest__clients.id"), nullable=False, unique=True)
    created_at: datetime = mapped_column(DateTime(), nullable=False, info={"set_on": "create"})
    updated_at: datetime = mapped_column(DateTime(), nullable=False, info={"set_on": {"create", "update"}})

    # relationships
    client = relationship("Client", back_populates="rate_limit_config")

    # lifecycle events
    @classmethod
    def __declare_last__(cls) -> None:
        pass
