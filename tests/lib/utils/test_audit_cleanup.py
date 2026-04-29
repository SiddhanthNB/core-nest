from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from lib.utils.audit_cleanup import cleanup_audit_logs


@pytest.mark.asyncio
async def test_cleanup_audit_logs_deletes_rows_older_than_cutoff(mocker) -> None:
    execute = mocker.AsyncMock(return_value=SimpleNamespace(rowcount=7))

    @asynccontextmanager
    async def fake_begin():
        yield SimpleNamespace(execute=execute)

    fake_engine = SimpleNamespace(begin=lambda: fake_begin())
    mocker.patch("lib.utils.audit_cleanup.db.async_engine", fake_engine)

    deleted = await cleanup_audit_logs(retention_days=30)

    assert deleted == 7
    statement = execute.await_args.args[0]
    params = execute.await_args.args[1]
    assert "DELETE FROM corenest__audit_logs" in str(statement)
    assert "cutoff" in params
