from datetime import datetime

from duo_orm import DateTime, JSON, mapped_column
from sqlalchemy import Float

from app.db import db


class APILog(db.Model):
    __tablename__ = "corenest__api_logs"

    id: int = mapped_column(primary_key=True, autoincrement=True)
    path: str
    method: str
    success: bool
    status_code: int | None
    process_time: float | None = mapped_column(Float, nullable=True)
    rq_params: dict = mapped_column(JSON, nullable=False)
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
