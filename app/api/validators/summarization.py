from typing import Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator


class Summarization(BaseModel):
    text: str = Field(..., description="Text text to be summarized")
    provider: Optional[str] = Field(
        None,
        description="The provider to use for summarization",
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'text' cannot be empty or blank",
            )
        return value

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str | None) -> str | None:
        valid_providers = ["google", "openrouter", "groq", "mistral", "cerebras"]
        if value and value not in valid_providers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Provider '{value}' is not supported. "
                    f"Supported providers are: {valid_providers}"
                ),
            )
        return value
