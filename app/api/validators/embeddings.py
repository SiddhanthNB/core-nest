from typing import List

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator


class Embeddings(BaseModel):
    texts: List[str] = Field(..., description="List of input texts")
    provider: str = Field(
        ...,
        description="The provider to use for generating embeddings",
    )

    @field_validator("texts")
    @classmethod
    def validate_texts(cls, value: List[str]) -> List[str]:
        if not value or len(value) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one string must be provided in 'texts'",
            )
        return value

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        valid_providers = ["google", "mistral"]
        if value not in valid_providers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Provider '{value}' is not supported. "
                    f"Supported providers are: {valid_providers}"
                ),
            )
        return value
