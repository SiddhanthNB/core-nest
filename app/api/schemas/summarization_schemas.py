from typing import Optional
from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator

class SummarizationSchema(BaseModel):
    text: str = Field(..., description="Text text to be summarized")
    provider: Optional[str] = Field(None, description="The provider to use for summarization")

    @field_validator("text")
    @classmethod
    def validate_text(cls, v):
        if not v or not v.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'text' cannot be empty or blank")
        return v

    @field_validator('provider')
    @classmethod
    def validate_provider(cls, v):
        valid_providers = ['google', 'openrouter', 'groq', 'mistral', 'cerebras']
        if v and v not in valid_providers:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Provider '{v}' is not supported. Supported providers are: {valid_providers}")
        return v
