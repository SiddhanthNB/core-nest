"""set null on audit logs client fk

Revision ID: ae102f9f1c3b
Revises: 87657050f3a0
Create Date: 2026-04-28 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ae102f9f1c3b"
down_revision: Union[str, Sequence[str], None] = "87657050f3a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    fk_name = _audit_logs_client_fk_name(bind)
    if fk_name:
        op.drop_constraint(fk_name, "corenest__audit_logs", type_="foreignkey")
    op.create_foreign_key(
        None,
        "corenest__audit_logs",
        "corenest__clients",
        ["client_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    fk_name = _audit_logs_client_fk_name(bind)
    if fk_name:
        op.drop_constraint(fk_name, "corenest__audit_logs", type_="foreignkey")
    op.create_foreign_key(
        None,
        "corenest__audit_logs",
        "corenest__clients",
        ["client_id"],
        ["id"],
    )


def _audit_logs_client_fk_name(bind) -> str | None:
    inspector = sa.inspect(bind)
    for foreign_key in inspector.get_foreign_keys("corenest__audit_logs"):
        if foreign_key.get("referred_table") != "corenest__clients":
            continue
        if foreign_key.get("constrained_columns") != ["client_id"]:
            continue
        return foreign_key.get("name")
    return None
