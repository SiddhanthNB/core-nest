from fastapi import FastAPI, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.controllers import api_router


def _docs_redirect() -> RedirectResponse:
    return RedirectResponse(url="/docs")


def _ping() -> JSONResponse:
    return JSONResponse(content="pong", status_code=status.HTTP_200_OK)


def register_routes(app: FastAPI) -> None:
    app.add_api_route("/", _docs_redirect, methods=["GET"], name="Root")
    app.add_api_route("/ping", _ping, methods=["GET"], name="Ping")
    app.include_router(api_router)
