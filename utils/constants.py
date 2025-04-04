import os
import yaml
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

APP_ENV = os.getenv('APP_ENV', 'production')
APP_PORT = os.getenv('APP_PORT', 3000)
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')

try:
    with open('utils/inference_providers/providers.yaml', 'r') as f:
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
