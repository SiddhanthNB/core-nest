"""reshape api logs into audit logs"""

import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '87657050f3a0'
down_revision: Union[str, Sequence[str], None] = '24476ccffe41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "corenest__audit_logs",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("process_time_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("request_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["corenest__clients.id"]),
        sa.PrimaryKeyConstraint("request_id"),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT path, method, success, status_code, process_time, rq_params, created_at
            FROM corenest__api_logs
            """
        )
    ).mappings()

    audit_logs_table = sa.table(
        "corenest__audit_logs",
        sa.column("request_id", postgresql.UUID(as_uuid=True)),
        sa.column("path", sa.String()),
        sa.column("method", sa.String()),
        sa.column("client_id", postgresql.UUID(as_uuid=True)),
        sa.column("provider", sa.String()),
        sa.column("model", sa.String()),
        sa.column("success", sa.Boolean()),
        sa.column("status_code", sa.Integer()),
        sa.column("process_time_ms", sa.Float()),
        sa.column("error", sa.String()),
        sa.column("request_meta", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("response_meta", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("created_at", sa.DateTime()),
    )

    insert_rows: list[dict[str, object]] = []
    for row in rows:
        legacy_payload = _ensure_dict(row["rq_params"])
        request_meta = legacy_payload.get("request_meta")
        response_meta = legacy_payload.get("response_meta")
        if not isinstance(request_meta, dict):
            request_meta = legacy_payload if isinstance(legacy_payload, dict) else {}
        if not isinstance(response_meta, dict):
            response_meta = {}

        insert_rows.append(
            {
                "request_id": _coerce_uuid(legacy_payload.get("request_id")) or uuid.uuid4(),
                "path": row["path"],
                "method": row["method"],
                "client_id": _coerce_uuid(legacy_payload.get("client_id")) or _coerce_uuid(request_meta.get("client_id")),
                "provider": response_meta.get("final_provider"),
                "model": response_meta.get("final_model"),
                "success": row["success"],
                "status_code": row["status_code"],
                "process_time_ms": row["process_time"],
                "error": response_meta.get("error") or (f"HTTP {row['status_code']}" if row["status_code"] and row["status_code"] >= 400 else None),
                "request_meta": request_meta,
                "response_meta": response_meta,
                "created_at": row["created_at"],
            }
        )

    if insert_rows:
        op.bulk_insert(audit_logs_table, insert_rows)

    op.drop_table("corenest__api_logs")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "corenest__api_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("process_time", sa.Float(), nullable=True),
        sa.Column("rq_params", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT request_id, path, method, success, status_code, process_time_ms,
                   request_meta, response_meta, created_at
            FROM corenest__audit_logs
            ORDER BY created_at
            """
        )
    ).mappings()

    api_logs_table = sa.table(
        "corenest__api_logs",
        sa.column("path", sa.String()),
        sa.column("method", sa.String()),
        sa.column("success", sa.Boolean()),
        sa.column("status_code", sa.Integer()),
        sa.column("process_time", sa.Float()),
        sa.column("rq_params", sa.JSON()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )

    insert_rows: list[dict[str, object]] = []
    for row in rows:
        insert_rows.append(
            {
                "path": row["path"],
                "method": row["method"],
                "success": row["success"],
                "status_code": row["status_code"],
                "process_time": row["process_time_ms"],
                "rq_params": {
                    "request_id": str(row["request_id"]),
                    "request_meta": _ensure_dict(row["request_meta"]),
                    "response_meta": _ensure_dict(row["response_meta"]),
                },
                "created_at": row["created_at"],
                "updated_at": row["created_at"],
            }
        )

    if insert_rows:
        op.bulk_insert(api_logs_table, insert_rows)

    op.drop_table("corenest__audit_logs")


def _ensure_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _coerce_uuid(value: object) -> uuid.UUID | None:
    if not value:
        return None
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None
