from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import constants


class _Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool", "developer"]
    content: str

    model_config = ConfigDict(extra="forbid")


class Completions(BaseModel):
    messages: list[_Message] = Field(..., description="OpenAI-like message list")
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_completion_tokens: int | None = Field(default=None, gt=0)
    max_tokens: int | None = Field(default=None, gt=0)
    top_p: float | None = Field(default=None, ge=0, le=1)
    n: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    stop: str | list[str] | None = None
    functions: list[dict[str, Any]] | None = None
    function_call: str | dict[str, Any] | None = None
    logit_bias: dict[str, float] | None = None
    user: str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    seed: int | None = None
    logprobs: bool | None = None
    top_logprobs: int | None = Field(default=None, gt=0)
    extra_headers: dict[str, str] | None = None
    model: str | None = None
    provider: str | None = None
    stream: bool | None = None
    stream_options: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _validate_api_managed_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        forbidden = set(constants.API_MANAGED_PARAMS["completions"]["blocked_params"])
        used = sorted(field for field in forbidden if field in data)
        if used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported request fields for /completions: {', '.join(used)}",
            )
        return data

    @field_validator("messages")
    @classmethod
    def _validate_messages(cls, value: list[_Message]) -> list[_Message]:
        if not value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'messages' must include at least one message",
            )
        if not any(message.role == "user" for message in value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'messages' must include at least one user message",
            )
        return value

    @model_validator(mode="after")
    def _apply_defaults(self):
        for field, value in constants.API_MANAGED_PARAMS["completions"]["defaults"].items():
            setattr(self, field, value)
        return self
