import uuid
from sqlalchemy import Column, String, Boolean, DateTime, func, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.models import BaseModel
from app.utils.helpers import flush_client_cache

class Client(BaseModel):
    __tablename__ = "corenest__clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    hashed_api_key = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship to RateLimitConfig (one-to-one), eagerly loaded for performance.
    rate_limit_config = relationship("RateLimitConfig", back_populates="client", uselist=False, cascade="all, delete-orphan", lazy="joined")

    def __repr__(self):
        return f"<Client(name='{self.name}', is_active={self.is_active})>"

event.listen(Client, 'after_update', flush_client_cache)
event.listen(Client, 'after_delete', flush_client_cache)
