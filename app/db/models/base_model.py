from sqlalchemy import inspect, select, update, delete, func, asc, desc
from app.config.logger import logger
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy.exc import SQLAlchemyError, OperationalError

Base = declarative_base()

class BaseModel(Base):
    __abstract__ = True

    @classmethod
    async def create_record(cls, db_session: AsyncSession, fields: dict):
        """Create a new record."""
        try:
            if not fields: raise OperationalError("Parameter 'fields' cannot be empty")

            obj = cls(**fields)
            db_session.add(obj)
            await db_session.commit()
            await db_session.refresh(obj)
            return obj
        except SQLAlchemyError as e:
            await db_session.rollback()
            logger.error(f"SQLAlchemy error: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return False

    @classmethod
    async def fetch_record_by_id(cls, db_session: AsyncSession, record_id: int):
        """Find a record by its ID."""
        try:
            if not record_id: raise OperationalError("Parameter 'record_id' cannot be empty")
            return await db_session.get(cls, record_id)
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return False

    @classmethod
    async def fetch_records(cls, db_session: AsyncSession, filters: dict = None):
        """Find all records by a filter."""
        try:
            filters = filters or {}
            result = await db_session.execute(select(cls).filter_by(**filters))
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return False

    @classmethod
    async def count(cls, db_session: AsyncSession, filters: dict = None):
        """Count records by a filter."""
        try:
            filters = filters or {}
            pk_column = inspect(cls).primary_key[0]
            result = await db_session.execute(select(func.count(pk_column)).filter_by(**filters))
            return result.scalar()
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return False

    @classmethod
    async def first(cls, db_session: AsyncSession, count: int = 1):
        """Fetch the first records by the given count."""
        try:
            pk_column = inspect(cls).primary_key[0]
            query = select(cls).order_by(asc(pk_column)).limit(count)
            result = await db_session.execute(query)
            return result.scalars().first() if count == 1 else result.scalars().all()
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return False

    @classmethod
    async def last(cls, db_session: AsyncSession, count: int = 1):
        """Fetch the last records by the given count."""
        try:
            pk_column = inspect(cls).primary_key[0]
            query = select(cls).order_by(desc(pk_column)).limit(count)
            result = await db_session.execute(query)
            return result.scalars().first() if count == 1 else result.scalars().all()
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return False

    @classmethod
    async def update_records(cls, db_session: AsyncSession, filters: dict, fields: dict):
        """Update records matching the filter with new values."""
        try:
            if not fields: raise OperationalError("Parameter 'fields' cannot be empty")

            fields['updated_at'] = datetime.now(timezone.utc)

            statement = update(cls).filter_by(**filters).values(**fields)
            result = await db_session.execute(statement)
            await db_session.commit()
            return result.rowcount
        except SQLAlchemyError as e:
            await db_session.rollback()
            logger.error(f"SQLAlchemy error: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return False

    async def update_attributes(self, db_session: AsyncSession, fields: dict):
        """Update specific fields of the current instance."""
        try:
            if not fields: raise OperationalError("Parameter 'fields' cannot be empty")

            fields['updated_at'] = datetime.now(timezone.utc)

            for key, value in fields.items():
                setattr(self, key, value)
            db_session.add(self)
            await db_session.commit()
            await db_session.refresh(self)
            return self
        except SQLAlchemyError as e:
            await db_session.rollback()
            logger.error(f"SQLAlchemy error: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return False

    async def destroy(self, db_session: AsyncSession):
        """Delete current instance"""
        try:
            await db_session.delete(self)
            await db_session.commit()
            return True
        except SQLAlchemyError as e:
            await db_session.rollback()
            logger.error(f"SQLAlchemy error: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return False

    @classmethod
    async def delete_records(cls, db_session: AsyncSession, filters: dict):
        """Delete records matching the filter."""
        try:
            statement = delete(cls).filter_by(**filters)
            result = await db_session.execute(statement)
            await db_session.commit()
            return result.rowcount
        except SQLAlchemyError as e:
            await db_session.rollback()
            logger.error(f"SQLAlchemy error: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return False

    def to_dict(self):
        """Convert the instance to a dictionary representation."""
        try:
            return { column.name: getattr(self, column.name) for column in self.__table__.columns }
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return False
