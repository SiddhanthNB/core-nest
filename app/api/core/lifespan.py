from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.config.logger import logger
from app.db import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.
    On startup, it "warms up" the database connection pool.
    On shutdown, it gracefully closes the database connection pool.
    """
    logger.bind(event="app_started").info("Application starting up...")
    logger.bind(event="app_started").info("Warming up database connection pool...")
    try:
        async with db.async_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        logger.bind(event="app_started").info("Database connection pool is warm and ready.")
    except Exception as e:
        logger.bind(event="unexpected_error").error(f"Failed to warm up database connection pool: {e}", exc_info=True)
        raise

    yield

    logger.bind(event="app_stopped").info("Application shutting down, closing database connection pool...")
    await db.async_engine.dispose()
    logger.bind(event="app_stopped").info("Database connection pool closed.")
