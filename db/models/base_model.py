from config.logger import logger
from config.postgres import get_session
from datetime import datetime, timezone
from sqlalchemy import func, asc, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import SQLAlchemyError, OperationalError

_session = get_session()
Base = declarative_base()

class BaseModel(Base):
	__abstract__ = True

	@classmethod
	def create_record(cls, fields):
		"""Create a new record."""
		try:
			if not fields: raise OperationalError("Parameter 'fields' cannot be empty")

			obj = cls(**fields)
			with _session() as session:
				session.add(obj)
				session.commit()
				session.refresh(obj)
			return obj
		except SQLAlchemyError as e:
			session.rollback()
			logger.error(f"SQLAlchemy error: {e}", exc_info=True)
			return False
		except Exception as e:
			logger.error(f"Error: {e}", exc_info=True)
			return False

	@classmethod
	def fetch_record_by_id(cls, record_id):
		"""Find a record by its ID."""
		try:
			if not record_id: raise OperationalError("Parameter 'record_id' cannot be empty")

			with _session() as session:
				return session.query(cls).get(record_id)
		except Exception as e:
			logger.error(f"Error: {e}", exc_info=True)
			return False

	@classmethod
	def fetch_records(cls, filters=None):
		"""Find all records by a filter."""
		try:
			filters = filters or {}
			with _session() as session:
				return session.query(cls).filter_by(**filters).all()
		except Exception as e:
			logger.error(f"Error: {e}", exc_info=True)
			return False

	@classmethod
	def count(cls, filters=None):
		"""Count records by a filter."""
		try:
			filters = filters or {}
			with _session() as session:
				return session.query(func.count(cls.id)).filter_by(**filters).scalar()
		except Exception as e:
			logger.error(f"Error: {e}", exc_info=True)
			return False

	@classmethod
	def first(cls, count=1):
		"""Fetch the first records by the given count."""
		try:
			with _session() as session:
				query = session.query(cls).order_by(asc(cls.id)).limit(count)
				return query.first() if count == 1 else query.all()
		except Exception as e:
			logger.error(f"Error: {e}", exc_info=True)
			return False

	@classmethod
	def last(cls, count=1):
		"""Fetch the last records by the given count."""
		try:
			with _session() as session:
				query = session.query(cls).order_by(desc(cls.id)).limit(count)
				return query.first() if count == 1 else query.all()
		except Exception as e:
			logger.error(f"Error: {e}", exc_info=True)
			return False

	@classmethod
	def update_records(cls, filters, fields):
		"""Update records matching the filter with new values."""
		try:
			if not fields: raise OperationalError("Parameter 'fields' cannot be empty")

			fields['updated_at'] = datetime.now(timezone.utc)

			with _session() as session:
				result = session.query(cls).filter_by(**filters).update(fields)
				session.commit()
				return result
		except SQLAlchemyError as e:
			session.rollback()
			logger.error(f"SQLAlchemy error: {e}", exc_info=True)
			return False
		except Exception as e:
			logger.error(f"Error: {e}", exc_info=True)
			return False

	def update_attributes(self, fields):
		"""Update specific fields of the current instance."""
		try:
			if not fields: raise OperationalError("Parameter 'fields' cannot be empty")

			fields['updated_at'] = datetime.now(timezone.utc)

			with _session() as session:
				for key, value in fields.items():
					setattr(self, key, value)
				session.commit()
				session.refresh(self)
				return self
		except SQLAlchemyError as e:
			session.rollback()
			logger.error(f"SQLAlchemy error: {e}", exc_info=True)
			return False
		except Exception as e:
			logger.error(f"Error: {e}", exc_info=True)
			return False

	@classmethod
	def delete_records(cls, filters):
		"""Delete records matching the filter."""
		try:
			with _session() as session:
				result = session.query(cls).filter_by(**filters).delete()
				session.commit()
				return result
		except SQLAlchemyError as e:
			session.rollback()
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
