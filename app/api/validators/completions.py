from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool", "developer"]
    content: str

    model_config = ConfigDict(extra="forbid")


class Completions(BaseModel):
    messages: list[Message] = Field(..., description="OpenAI-like message list")
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    top_p: float | None = Field(default=None, ge=0, le=1)
    stream: bool | None = None
    stop: str | list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    model: str | None = None
    provider: str | None = None
    user_prompt: str | None = None
    system_prompt: str | None = None
    structured_output: bool | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, value: list[Message]) -> list[Message]:
        if not value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'messages' must include at least one message",
            )
        return value

    @model_validator(mode="after")
    def validate_locked_fields(self):
        forbidden = {"model", "provider", "user_prompt", "system_prompt", "structured_output", "stream"}
        used = sorted(field for field in forbidden if field in self.__pydantic_fields_set__)
        if used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported request fields for /completions: {', '.join(used)}",
            )
        return self
