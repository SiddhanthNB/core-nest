import uuid
from datetime import datetime

from duo_orm import DateTime, ForeignKey, PG_JSONB, PG_UUID, String, mapped_column, relationship
from sqlalchemy import Float

from app.db import db


class AuditLog(db.Model):
    __tablename__ = "corenest__audit_logs"

    request_id: uuid.UUID = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path: str
    method: str
    client_id: uuid.UUID | None = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("corenest__clients.id"),
        nullable=True,
    )
    provider: str | None = mapped_column(String, nullable=True)
    model: str | None = mapped_column(String, nullable=True)
    success: bool
    status_code: int | None
    process_time_ms: float | None = mapped_column(Float, nullable=True)
    error: str | None = mapped_column(String, nullable=True)
    request_meta: dict = mapped_column(PG_JSONB, nullable=False)
    response_meta: dict = mapped_column(PG_JSONB, nullable=False)
    created_at: datetime = mapped_column(
        DateTime(),
        nullable=False,
        info={"set_on": "create"},
    )

    client = relationship("Client", back_populates="audit_logs", lazy="select")
