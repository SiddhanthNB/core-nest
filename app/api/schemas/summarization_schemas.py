from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator

class SummarizationSchema(BaseModel):
    text: str = Field(..., description="Text text to be summarized")

    @field_validator("text")
    @classmethod
    def validate_text(cls, v):
        if not v or not v.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'text' cannot be empty or blank")
        return v
