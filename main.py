"""
Main entry point for CoreNest API
"""
import uvicorn
from app.api import create_app
from app.utils import constants

app = create_app()

if __name__ == '__main__':
    reload = constants.APP_ENV.lower() == 'development'
    uvicorn.run('main:app', port=int(constants.APP_PORT), host='0.0.0.0', reload=reload)
