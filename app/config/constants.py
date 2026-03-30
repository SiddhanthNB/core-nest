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
        _config_str = f.read()
    _config_str = _config_str.format(**os.environ)
    _settings = yaml.safe_load(_config_str)
except FileNotFoundError:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Config file not found!')
except KeyError as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Missing environment variable: {e}')
except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Error reading config file: {e}')

SERVICES = _settings['services']
