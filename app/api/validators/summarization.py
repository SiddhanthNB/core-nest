from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Summarization(BaseModel):
    text: str = Field(..., description="Text to be summarized")
    model: str | None = None
    provider: str | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    stream: bool | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'text' cannot be empty or blank",
            )
        return value

    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'system_prompt' cannot be blank",
            )
        return value

    @model_validator(mode="after")
    def validate_locked_fields(self):
        forbidden = {
            "model",
            "provider",
            "temperature",
            "tools",
            "tool_choice",
            "response_format",
            "stream",
        }
        used = sorted(field for field in forbidden if field in self.__pydantic_fields_set__)
        if used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Locked request fields for /summaries: {', '.join(used)}",
            )
        return self
