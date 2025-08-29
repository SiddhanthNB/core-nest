from app.config.logger import logger
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from app.config.postgres import async_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.
    On startup, it "warms up" the database connection pool.
    On shutdown, it gracefully closes the database connection pool.
    """
    logger.info("Application starting up...")
    logger.info("Warming up database connection pool...")
    try:
        async with async_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        logger.info("Database connection pool is warm and ready.")
    except Exception as e:
        logger.error(f"Failed to warm up database connection pool: {e}", exc_info=True)

    yield

    logger.info("Application shutting down, closing database connection pool...")
    await async_engine.dispose()
    logger.info("Database connection pool closed.")
