import uuid
from datetime import datetime

from duo_orm import DateTime, String, mapped_column
from sqlalchemy import Boolean, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import db
from app.db.events import flush_client_cache


class Client(db.Model):
    __tablename__ = "corenest__clients"

    id: uuid.UUID = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: str
    hashed_api_key: str = mapped_column(String, nullable=False, unique=True)
    is_active: bool = mapped_column(Boolean, nullable=False, default=True)
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

    rate_limit_config = relationship(
        "RateLimitConfig",
        back_populates="client",
        uselist=False,
        cascade="all, delete-orphan",
        # lazy="joined"
    )

    def __repr__(self):
        return f"<Client(name='{self.name}', is_active={self.is_active})>"


event.listen(Client, 'after_update', flush_client_cache)
event.listen(Client, 'after_delete', flush_client_cache)
