import os
import tomllib
from pathlib import Path
from urllib.parse import quote_plus

import yaml
from dotenv import load_dotenv
from fastapi import HTTPException, status

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
LLM_DIR = REPO_ROOT / "lib" / "llm"
PROMPTS_DIR = LLM_DIR / "prompts"
PYPROJECT_TOML_PATH = REPO_ROOT / "pyproject.toml"
LLM_PROVIDERS_CONFIG_PATH = REPO_ROOT / "app" / "config" / "llm_providers.yaml"
API_MANAGED_PARAMS_CONFIG_PATH = REPO_ROOT / "app" / "config" / "api_managed_params.yaml"

APP_ENV = os.getenv("APP_ENV", "production")
APP_PORT = int(os.getenv("PORT", 3000))

WEB_CONCURRENCY = int(os.getenv("WEB_CONCURRENCY", 1))

SUPABASE_DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL").replace("[YOUR-PASSWORD]", quote_plus(SUPABASE_DB_PASSWORD))

REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_URL = os.getenv("REDIS_URL").replace("[YOUR-PASSWORD]", quote_plus(REDIS_PASSWORD))

GITHUB_STEP_SUMMARY = os.getenv("GITHUB_STEP_SUMMARY")


def _load_yaml_config(path: Path, name: str) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{name} config file not found!",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reading {name} config file: {e}",
        )


def _load_toml_config(path: Path, name: str) -> dict:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{name} config file not found!",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reading {name} config file: {e}",
        )


_pyproject = _load_toml_config(PYPROJECT_TOML_PATH, "Project metadata")
PROJECT_NAME = _pyproject["project"]["name"]


_api_managed_params = _load_yaml_config(API_MANAGED_PARAMS_CONFIG_PATH, "API managed params")

API_MANAGED_PARAMS = _api_managed_params["endpoints"]

_llm_providers = _load_yaml_config(LLM_PROVIDERS_CONFIG_PATH, "LLM providers")

PROVIDERS = _llm_providers["providers"]


def _enabled_provider_entries():
    return (
        (provider_name, provider_config)
        for provider_name, provider_config in PROVIDERS.items()
        if provider_config.get("enabled", True)
    )


COMPLETION_PROVIDERS = tuple(
    provider_name
    for provider_name, provider_config in _enabled_provider_entries()
    if provider_config.get("models", {}).get("completion")
)
EMBEDDING_PROVIDERS = tuple(
    provider_name
    for provider_name, provider_config in _enabled_provider_entries()
    if provider_config.get("models", {}).get("embedding")
)
