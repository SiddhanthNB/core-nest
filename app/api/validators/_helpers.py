from __future__ import annotations

from app.config import constants

_MODEL_ALIAS_PREFIX = f"{constants.PROJECT_NAME}/"


def _completion_model_aliases() -> set[str]:
    return {
        f"{_MODEL_ALIAS_PREFIX}auto",
        *{f"{_MODEL_ALIAS_PREFIX}{provider}" for provider in constants.COMPLETION_PROVIDERS},
    }


def _embedding_model_aliases() -> set[str]:
    return {f"{_MODEL_ALIAS_PREFIX}{provider}" for provider in constants.EMBEDDING_PROVIDERS}


def validate_completion_model_alias(model: str) -> str:
    if model not in _completion_model_aliases():
        raise ValueError(f"Unsupported model '{model}'")
    return model


def validate_embedding_model_alias(model: str) -> str:
    if model not in _embedding_model_aliases():
        raise ValueError(f"Unsupported model '{model}'")
    return model
