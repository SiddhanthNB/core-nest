"""
CoreNest FastAPI Application Package
"""
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from app.api.endpoints import router
from app.utils.helpers.fastapi_lifespan import lifespan
from app.utils.helpers.api_logger import api_logger_middleware

def create_app():
    """Create and configure FastAPI application"""
    app = FastAPI(lifespan=lifespan)

    # Add middleware
    app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
    app.add_middleware(api_logger_middleware)

    # Root routes
    app.add_api_route('/', lambda: RedirectResponse(url='/redoc'), methods=['GET'], name='Root')
    app.add_api_route('/ping', lambda: JSONResponse(content='pong', status_code=status.HTTP_200_OK), methods=['GET'], name='Ping')

    # Include API routes
    app.include_router(router)

    return app

__all__ = [
    "create_app"
]
