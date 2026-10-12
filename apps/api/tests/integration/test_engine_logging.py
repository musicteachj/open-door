"""A failed statement must not carry its bound values into the error or the logs."""

import logging

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

SECRET = "ana-private-value-7431"  # noqa: S105


async def test_a_failed_statement_does_not_reveal_its_bound_values(
    app_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    with pytest.raises(DBAPIError) as failure:
        async with app_engine.connect() as connection:
            await connection.execute(
                text("SELECT CAST(:value AS text) FROM no_such_table"), {"value": SECRET}
            )

    # The failure is about the missing table, so the database's own message never repeats the value;
    # only SQLAlchemy's "[parameters: ...]" line could.
    assert SECRET not in str(failure.value)
    assert SECRET not in caplog.text
    assert "[parameters:" not in str(failure.value)
