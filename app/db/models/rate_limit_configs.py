from sqlalchemy import Column, Integer, ForeignKey, DateTime, func, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.models import BaseModel
from app.utils.helpers import flush_client_cache

class RateLimitConfig(BaseModel):
    __tablename__ = "corenest__rate_limit_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    requests_per_minute = Column(Integer, nullable=True)
    requests_per_hour = Column(Integer, nullable=True)
    requests_per_day = Column(Integer, nullable=True)
    concurrent_requests_limit = Column(Integer, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    client_id = Column(UUID(as_uuid=True), ForeignKey("corenest__clients.id"), nullable=False, unique=True)

    client = relationship("Client", back_populates="rate_limit_config")

    def __repr__(self):
        return f"<RateLimitConfig(client_id='{self.client_id}')>"

event.listen(RateLimitConfig, 'after_update', flush_client_cache)
