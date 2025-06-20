import os
import logging
from datetime import datetime
import utils.constants as constants
from logging.handlers import TimedRotatingFileHandler

def _get_file_path(timestamp: str) -> str:
    return os.path.join(log_dir, f"{constants.PROJECT_NAME}.{timestamp}.log")

def _custom_namer(default_name: str) -> str:
  try:
      date_str = default_name.split('.')[-1]
      return _get_file_path(timestamp=date_str)
  except ValueError:
      return default_name

# setup directory
log_dir = os.path.join(os.getcwd(), 'log')
os.makedirs(log_dir, exist_ok=True)

# formatter
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s : %(message)s")

# rotation file handler
file_handler = TimedRotatingFileHandler(
	filename = _get_file_path(timestamp=datetime.now().strftime('%Y-%m-%d')),
	when = 'midnight',
	interval = 1,
	utc = True,
	backupCount = 7,
	encoding = 'utf-8'
)
file_handler.namer = _custom_namer
file_handler.setFormatter(formatter)

# standard out handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# config
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
