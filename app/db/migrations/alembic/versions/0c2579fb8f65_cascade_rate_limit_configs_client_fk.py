"""cascade rate limit configs client fk

Revision ID: 0c2579fb8f65
Revises: ae102f9f1c3b
Create Date: 2026-10-15 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0c2579fb8f65"
down_revision: Union[str, Sequence[str], None] = "ae102f9f1c3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    fk_name = _rate_limit_configs_client_fk_name(bind)
    if fk_name:
        op.drop_constraint(fk_name, "corenest__rate_limit_configs", type_="foreignkey")
    op.create_foreign_key(
        None,
        "corenest__rate_limit_configs",
        "corenest__clients",
        ["client_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    bind = op.get_bind()
    fk_name = _rate_limit_configs_client_fk_name(bind)
    if fk_name:
        op.drop_constraint(fk_name, "corenest__rate_limit_configs", type_="foreignkey")
    op.create_foreign_key(
        None,
        "corenest__rate_limit_configs",
        "corenest__clients",
        ["client_id"],
        ["id"],
    )


def _rate_limit_configs_client_fk_name(bind) -> str | None:
    inspector = sa.inspect(bind)
    for foreign_key in inspector.get_foreign_keys("corenest__rate_limit_configs"):
        if foreign_key.get("referred_table") != "corenest__clients":
            continue
        if foreign_key.get("constrained_columns") != ["client_id"]:
            continue
        return foreign_key.get("name")
    return None
