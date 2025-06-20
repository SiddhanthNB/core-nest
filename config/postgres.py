from config.logger import logger
import utils.constants as constants
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session

_engine = create_engine(
	constants.SUPABASE_DB_URL,
	echo=constants.APP_ENV == 'development',
	pool_size=5,
	pool_recycle=3600,
	max_overflow=10,
	pool_pre_ping=True,
	pool_timeout=30,
	connect_args={
		"connect_timeout": 10,
		"application_name": constants.PROJECT_NAME
	}
)

db_session = scoped_session(sessionmaker(bind=_engine))

def close_session():
	try:
		db_session.remove()
	except Exception as e:
		logger.warning(f"Error during session cleanup (this is usually harmless): {e}")
		try:
			db_session.registry.clear()
		except Exception:
			pass

def execute_query(raw_query, params = None):
	res = { 'rows': [], 'columns': [] }
	try:
		with _engine.connect() as connection:
			result = connection.execute(text(raw_query), params)
			res['columns'] = list(result.keys())
			res['rows']    = [ tuple(row) for row in result.fetchall() ]
	except Exception as e:
		logger.error(f'Error: {e}', exc_info = True)
		return res

'''
  query = """
			SELECT users.id, users.access_key, users.organisation_id, users.status, users.education, users.title, users.email, users.is_admin, users.employee_level, users.profiles
			FROM users
			JOIN organisations ON organisations.id = users.organisation_id
			WHERE organisations.access_key = :org_access_key AND users.is_admin IN :is_admin
        """
  params = {'org_access_key': 'ff67f6cd-29f1-48bc-9d22-9e196efb7b9c', 'is_admin': (True)}
  result = execute_query(query, params)
  result.get('rows')
  result.get('columns')
'''
