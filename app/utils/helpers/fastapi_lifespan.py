from fastapi import FastAPI
from config.postgres import close_session
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_session()
