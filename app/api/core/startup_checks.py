from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from duo_orm.migrations.config import get_version_table

from app.db import db

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ALEMBIC_INI_PATH = _REPO_ROOT / "app" / "db" / "migrations" / "alembic.ini"
_PYPROJECT_PATH = _REPO_ROOT / "pyproject.toml"


def ensure_no_pending_migrations() -> None:
    config = Config(str(_ALEMBIC_INI_PATH))
    script = ScriptDirectory.from_config(config)
    version_table = get_version_table(pyproject_path=_PYPROJECT_PATH)

    with db.sync_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"version_table": version_table})
        current_revision = context.get_current_revision()

    head_revision = script.get_current_head()
    if current_revision != head_revision:
        raise RuntimeError(
            f"Pending migrations detected: current={current_revision}, head={head_revision}"
        )
