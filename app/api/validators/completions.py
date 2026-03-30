from typing import Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator


class Completions(BaseModel):
    user_prompt: str = Field(..., description="User input prompt")
    system_prompt: Optional[str] = Field(
        default="You are a helpful assistant",
        description="System prompt for the assistant",
    )
    structured_output: Optional[bool] = Field(
        default=False,
        description="Whether the output should be structured",
    )
    provider: Optional[str] = Field(
        None,
        description="The provider to use for completion",
    )

    @field_validator("user_prompt")
    @classmethod
    def validate_user_prompt(cls, value: str) -> str:
        if not value or not value.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'user_prompt' cannot be empty",
            )
        return value

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str | None) -> str | None:
        valid_providers = [
            "google",
            "openrouter",
            "huggingface",
            "groq",
            "mistral",
            "cerebras",
        ]
        if value and value not in valid_providers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Provider '{value}' is not supported. "
                    f"Supported providers are: {valid_providers}"
                ),
            )
        return value
