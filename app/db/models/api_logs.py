from sqlalchemy.sql import func
from app.db.models.base_model import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean, Float

class APILog(BaseModel):
    __tablename__ = "corenest__api_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    path = Column(String, nullable=False)
    method = Column(String, nullable=False)
    success = Column(Boolean, nullable=False)
    status_code = Column(Integer, nullable=True)
    process_time = Column(Float, nullable=True)
    auth_headers = Column(JSON, nullable=True)
    rq_params = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
