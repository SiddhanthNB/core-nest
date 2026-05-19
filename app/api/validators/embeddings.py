from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import constants

from ._helpers import validate_embedding_model_alias


class Embeddings(BaseModel):
    input: str | list[str] = Field(..., description="Embedding input payload")
    model: str = Field(..., description="CoreNest embedding model alias")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _validate_api_managed_fields(cls, data: Any) -> Any:
        if isinstance(data, dict) and any(field in data for field in constants.API_MANAGED_PARAMS["embeddings"]["blocked_params"]):  # fmt: skip
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported request fields for /embeddings: model",
            )
        return data

    @field_validator("input")
    @classmethod
    def _validate_input(cls, value: str | list[str]) -> str | list[str]:
        if isinstance(value, list) and not value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one string must be provided in 'input'",
            )
        return value

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        try:
            return validate_embedding_model_alias(value)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @model_validator(mode="after")
    def _apply_defaults(self):
        for field, value in constants.API_MANAGED_PARAMS["embeddings"]["defaults"].items():
            setattr(self, field, value)
        return self
