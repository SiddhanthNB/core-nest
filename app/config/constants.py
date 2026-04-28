import os
from pathlib import Path
import yaml
from dotenv import load_dotenv
from fastapi import HTTPException, status
from urllib.parse import quote_plus

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
LLM_DIR = REPO_ROOT / "lib" / "llm"
PROMPTS_DIR = LLM_DIR / "prompts"
PROVIDERS_CONFIG_PATH = LLM_DIR / "providers.yaml"

PROJECT_NAME = 'corenest'

APP_ENV = os.getenv('APP_ENV', 'production')
APP_PORT = int(os.getenv('PORT', 3000))

WEB_CONCURRENCY = int(os.getenv('WEB_CONCURRENCY', 1))

SUPABASE_DB_PASSWORD = os.getenv('SUPABASE_DB_PASSWORD')
SUPABASE_DB_URL = os.getenv('SUPABASE_DB_URL').replace('[YOUR-PASSWORD]', quote_plus(SUPABASE_DB_PASSWORD))

REDIS_PASSWORD = os.getenv('REDIS_PASSWORD')
REDIS_URL = os.getenv('REDIS_URL').replace('[YOUR-PASSWORD]', quote_plus(REDIS_PASSWORD))

try:
    with PROVIDERS_CONFIG_PATH.open("r", encoding="utf-8") as f:
        _settings = yaml.safe_load(f)
except FileNotFoundError:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Config file not found!')
except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Error reading config file: {e}')

PROVIDERS = _settings['providers']


def resolve_provider_api_key(provider_name: str) -> str | None:
    provider_config = PROVIDERS.get(provider_name)
    if not provider_config:
        return None
    api_key_env = provider_config.get("api_key_env")
    if not api_key_env:
        return None
    return os.getenv(api_key_env)


def _build_legacy_services() -> dict:
    services: dict[str, dict] = {}
    for provider_name, provider_config in PROVIDERS.items():
        models = provider_config.get("models", {})
        service_entry: dict[str, object] = {
            "key": resolve_provider_api_key(provider_name),
        }
        if "chat" in models:
            service_entry["generation"] = {"model": models["chat"]}
        if "embedding" in models:
            service_entry["embedding"] = {"model": models["embedding"]}
        services[provider_name] = service_entry

    if "gemini" in services:
        services["google"] = services["gemini"]

    return services


SERVICES = _build_legacy_services()
