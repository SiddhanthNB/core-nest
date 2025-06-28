from typing import Generator
from app.config.postgres import db_session, close_session


def get_db_session() -> Generator:
    """
    FastAPI dependency to get database session.

    For scoped sessions, the session should be closed at the end of each request
    to ensure proper cleanup and avoid connection leaks.

    Yields:
        db_session: SQLAlchemy session instance

    Usage:
        @app.post('/example')
        def create_record(db: Session = Depends(get_db_session)):
            # Use db session here
            pass
    """
    try:
        yield db_session
    finally:
        # Close scoped session at the end of each request
        close_session()
