"""
Main entry point for CoreNest API
"""
import uvicorn
from app.api import create_app
from app.utils import constants

app = create_app()

if __name__ == '__main__':
    local_env = constants.APP_ENV.lower() == 'development'
    uvicorn_conf = {
        'port': constants.APP_PORT,
        'host': '0.0.0.0',
        'reload': local_env,
        'workers': None if local_env else constants.WEB_CONCURRENCY,
    }
    uvicorn.run('main:app', **uvicorn_conf)
