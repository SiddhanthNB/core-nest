from typing import List, Optional
from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator

class EmbeddingSchema(BaseModel):
    texts: List[str] = Field(..., description="List of input texts")
    provider: Optional[str] = Field(None, description="The provider to use for generating embeddings")

    @field_validator('texts')
    @classmethod
    def validate_texts(cls, v):
        if not v or len(v) == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one string must be provided in 'texts'")
        return v

    @field_validator('provider')
    @classmethod
    def validate_provider(cls, v):
        if v and v not in ['google', 'openai']:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Provider '{v}' is not supported. Supported providers are: ['google', 'openai']")
        return v
