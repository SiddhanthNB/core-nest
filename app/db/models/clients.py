import uuid
from datetime import datetime

from duo_orm import Boolean, DateTime, PG_UUID, String, mapped_column, relationship

from app.db import db


class Client(db.Model):
    __tablename__ = "corenest__clients"

    # columns
    id: uuid.UUID = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: str
    hashed_api_key: str = mapped_column(String, nullable=False, unique=True)
    is_active: bool = mapped_column(Boolean, nullable=False, default=True)
    created_at: datetime = mapped_column(DateTime(), nullable=False, info={"set_on": "create"})
    updated_at: datetime = mapped_column(DateTime(), nullable=False, info={"set_on": {"create", "update"}})

    # relationships
    rate_limit_config = relationship("RateLimitConfig", back_populates="client", uselist=False, cascade="all, delete-orphan", lazy="joined")
    audit_logs = relationship("AuditLog", back_populates="client", lazy="select", passive_deletes=True)

    # lifecycle events
    @classmethod
    def __declare_last__(cls) -> None:
        pass
