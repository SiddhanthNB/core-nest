import uvicorn
from fastapi import FastAPI
from api.routes import router
import utils.constants as constants
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from utils.helpers.api_logger import api_logger_middleware

app = FastAPI()

app.add_middleware(
	CORSMiddleware,
	allow_origin_regex = r'',
	allow_methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
)

app.add_middleware(api_logger_middleware)

@app.get("/")
async def root():
    return RedirectResponse(url="/redoc")

@app.get('/site/status')
async def get_site_status():
  	return JSONResponse(content={ 'success': True }, status_code=200)

app.include_router(router)

if __name__ == '__main__':
    reload = constants.APP_ENV.lower() == 'development'
    uvicorn.run('main:app', port=int(constants.APP_PORT), host="0.0.0.0", reload=reload)
