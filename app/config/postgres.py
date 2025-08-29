from app.config.logger import logger
from app.utils import constants
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from contextlib import asynccontextmanager
from typing import AsyncGenerator

db_url = constants.SUPABASE_DB_URL.replace("postgresql://", "postgresql+psycopg://")

async_engine = create_async_engine(
    db_url,
    pool_size=5,
    pool_recycle=3600,
    max_overflow=10,
    pool_pre_ping=True,
    pool_timeout=30,
    connect_args={ "application_name": constants.PROJECT_NAME }
)

async_session_maker = async_sessionmaker(bind=async_engine, expire_on_commit=False)

@asynccontextmanager
async def get_async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    A session generator for use in standalone scripts or background tasks.

    This context manager handles the creation and cleanup of a session.

    Usage:
        async with get_async_db_session() as session:
            await session.execute(...)
    """
    async with async_session_maker() as session:
        yield session

async def execute_query(raw_query, params=None):
    """
    Execute a raw SQL query and return the result.

    This function is a low-level database access method and should be used with caution.

    It is recommended to use higher-level abstractions (e.g., ORM) for most database interactions.

    Usage:
        raw_query = "SELECT * FROM users WHERE id = :user_id"
        params = {"user_id": 1}
        result = await execute_query(raw_query, params)
        print(result.get('rows'))
        print(result.get('columns'))
    """
    res = {'rows': [], 'columns': []}
    try:
        async with async_engine.connect() as connection:
            result = await connection.execute(text(raw_query), params)
            res['columns'] = list(result.keys())
            res['rows'] = [tuple(row) for row in result.fetchall()]
        return res
    except Exception as e:
        logger.error(f'Error: {e}', exc_info=True)
        return res
