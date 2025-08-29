from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.postgres import get_async_db_session

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an asynchronous database session.
    """
    async with get_async_db_session() as session:
        yield session
