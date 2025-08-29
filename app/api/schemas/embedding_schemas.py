from typing import List
from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator

class EmbeddingSchema(BaseModel):
    texts: List[str] = Field(..., description="List of input texts")

    @field_validator('texts')
    @classmethod
    def validate_texts(cls, v):
        if not v or len(v) == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one string must be provided in 'texts'")
        return v
