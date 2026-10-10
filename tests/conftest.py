from __future__ import annotations

import os
import sys
from pathlib import Path

# litellm fetches its model cost map over the network at import unless told to use the bundled copy
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from logging.handlers import TimedRotatingFileHandler  # noqa: E402

from app.config.logger import logger  # noqa: E402

# keep test runs out of the real logs/ file
for _handler in [handler for handler in logger.handlers if isinstance(handler, TimedRotatingFileHandler)]:
    logger.removeHandler(_handler)
    _handler.close()
