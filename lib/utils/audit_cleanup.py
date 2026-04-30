from __future__ import annotations

from datetime import UTC, datetime, timedelta

from duo_orm import text

from app.db import db


async def cleanup_audit_logs(*, retention_days: int = 60) -> int:
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=retention_days)
    async with db.async_engine.begin() as connection:
        result = await connection.execute(
            text(
                """
                DELETE FROM corenest__audit_logs
                WHERE created_at < :cutoff
                """
            ),
            {"cutoff": cutoff},
        )
    return int(result.rowcount or 0)
