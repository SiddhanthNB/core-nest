from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import constants

from .completions import _Message


class Sentiments(BaseModel):
    messages: list[_Message] = Field(..., description="OpenAI-like message list without system messages")
    model: str | None = None
    provider: str | None = None
    temperature: float | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    stream: bool | None = None
    stream_options: dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _validate_api_managed_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        forbidden = set(constants.API_MANAGED_PARAMS["sentiments"]["blocked_params"])
        used = sorted(field for field in forbidden if field in data)
        if used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Locked request fields for /sentiments: {', '.join(used)}",
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
        if any(message.role == "system" for message in value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="System messages are not allowed for /sentiments",
            )
        return value

    @model_validator(mode="after")
    def _apply_defaults(self):
        for field, value in constants.API_MANAGED_PARAMS["sentiments"]["defaults"].items():
            setattr(self, field, value)
        return self
