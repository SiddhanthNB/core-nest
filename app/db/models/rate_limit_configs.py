import uuid
from datetime import datetime

from duo_orm import DateTime, mapped_column
from sqlalchemy import ForeignKey, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import db
from app.db.events import flush_client_cache


class RateLimitConfig(db.Model):
    __tablename__ = "corenest__rate_limit_configs"

    id: int = mapped_column(primary_key=True, autoincrement=True)
    requests_per_minute: int | None
    requests_per_hour: int | None
    requests_per_day: int | None
    concurrent_requests_limit: int | None
    client_id: uuid.UUID = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corenest__clients.id"),
        nullable=False,
        unique=True,
    )
    created_at: datetime = mapped_column(
        DateTime(),
        nullable=False,
        info={"set_on": "create"},
    )
    updated_at: datetime = mapped_column(
        DateTime(),
        nullable=False,
        info={"set_on": {"create", "update"}},
    )

    client = relationship("Client", back_populates="rate_limit_config")

    def __repr__(self):
        return f"<RateLimitConfig(client_id='{self.client_id}')>"

event.listen(RateLimitConfig, 'after_update', flush_client_cache)
