import uvicorn
from fastapi import FastAPI
from api.routes import router
import utils.constants as constants
from fastapi.middleware.cors import CORSMiddleware
from utils.helpers.api_logger import api_logger_middleware
from fastapi.responses import JSONResponse, RedirectResponse

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origin_regex=r'', allow_methods='*')
app.add_middleware(api_logger_middleware)

@app.get('/')
async def root():
    return RedirectResponse(url='/redoc')

@app.get('/ping')
async def ping():
    return JSONResponse(content='pong', status_code=200)

app.include_router(router)

if __name__ == '__main__':
    reload = constants.APP_ENV.lower() == 'development'
    uvicorn.run('main:app', port=int(constants.APP_PORT), host='0.0.0.0', reload=reload)
