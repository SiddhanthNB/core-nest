import asyncio
from fastapi import FastAPI
from app.config.postgres import close_session
from app.config.logger import logger
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")

    yield

    logger.info("Application shutting down, performing final session cleanup...")
    await asyncio.to_thread(close_session)
