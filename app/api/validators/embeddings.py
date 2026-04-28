from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Embeddings(BaseModel):
    input: str | list[str] = Field(..., description="Embedding input payload")
    model: str | None = None
    provider: str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    stream: bool | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict) and "input" not in data and "texts" in data:
            normalized = dict(data)
            normalized["input"] = normalized.pop("texts")
            return normalized
        return data

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: str | list[str]) -> str | list[str]:
        if isinstance(value, list) and not value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one string must be provided in 'input'",
            )
        return value

    @model_validator(mode="after")
    def validate_locked_fields(self):
        forbidden = {"model", "provider", "tools", "tool_choice", "response_format", "stream"}
        used = sorted(field for field in forbidden if field in self.__pydantic_fields_set__)
        if used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported request fields for /embeddings: {', '.join(used)}",
            )
        return self
