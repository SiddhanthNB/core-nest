from fastapi import FastAPI

from app.api.core.lifespan import lifespan
from app.api.core.middleware import register_middleware
from app.api.core.routes import register_routes


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    register_middleware(app)
    register_routes(app)
    return app
