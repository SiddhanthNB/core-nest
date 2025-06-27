"""
CoreNest FastAPI Application Package
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.endpoints import router
from app.utils.helpers.api_logger import api_logger_middleware

def create_app():
    """Create and configure FastAPI application"""
    app = FastAPI()

    # Add middleware
    app.add_middleware(CORSMiddleware, allow_origin_regex=r'', allow_methods='*')
    app.add_middleware(api_logger_middleware)

    # Root routes
    @app.get('/')
    async def root():
        return RedirectResponse(url='/redoc')

    @app.get('/ping')
    async def ping():
        return JSONResponse(content='pong', status_code=200)

    # Include API routes
    app.include_router(router)

    return app

# Export create_app for external usage
__all__ = ["create_app"]
