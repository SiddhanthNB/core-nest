import os
import yaml
from dotenv import load_dotenv
from fastapi import HTTPException
from urllib.parse import quote_plus

load_dotenv()

APP_ENV = os.getenv('APP_ENV', 'production')
APP_PORT = os.getenv('APP_PORT', 3000)
PROJECT_NAME = 'corenest'

CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')

SUPABASE_DB_PASSWORD = os.getenv('SUPABASE_DB_PASSWORD')
SUPABASE_DB_URL = os.getenv('SUPABASE_DB_URL').replace('[YOUR-PASSWORD]', quote_plus(SUPABASE_DB_PASSWORD))

try:
    # Get absolute path to config file
    config_path = os.path.join(os.path.dirname(__file__), 'providers.yaml')
    with open(config_path, 'r') as f:
        _config_str = f.read()
    _config_str = _config_str.format(**os.environ)
    _settings = yaml.safe_load(_config_str)
except FileNotFoundError:
    raise HTTPException(status_code=500, detail=f'Config file not found!')
except KeyError as e:
    raise HTTPException(status_code=500, detail=f'Missing environment variable: {e}')
except Exception as e:
    raise HTTPException(status_code=500, detail=f'Error reading config file: {e}')

SERVICES = _settings['services']
