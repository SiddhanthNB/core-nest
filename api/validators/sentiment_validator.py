from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

class SentimentValidator(BaseModel):
    text: str = Field(..., description="Text for sentiment analysis")

    @field_validator("text")
    @classmethod
    def validate_text(cls, v):
        if not v or not v.strip():
            raise HTTPException(status_code=400, detail="'text' cannot be empty or blank")
        return v
