from typing import List
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

class EmbeddingValidator(BaseModel):
    texts: List[str] = Field(..., description="List of input texts")

    @field_validator('texts')
    @classmethod
    def validate_texts(cls, v):
        if not v or len(v) == 0:
            raise HTTPException(status_code=400, detail="At least one string must be provided in 'texts'")
        return v
