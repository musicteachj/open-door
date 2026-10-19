"""Removing a throwaway sandbox together with the daily-ledger rows its turns wrote.

Shared by the assistant eval (`evals/assistant/run.py`) and the proxy check
(`scripts/proxy-check/check.py`), which both run real turns in a sandbox and then clean up. Run it
only as the database owner: the API's login cannot delete a tenant.

The daily ledger (`ai_spend_daily`) has no tenant, so deleting the tenant does not cascade to it.
Each of the sandbox's own `ai_spend` rows is matched to one daily row, of the same kind and amount
and the same instant (a reservation's two rows are written in one transaction, so their
`created_at` is equal). The daily rows go first and the tenant second, in one transaction, so a
failure leaves both in place and never a tenant with no ledger link.

Only the eval sweeps such leftovers at its next start (its sandbox has a fixed ID). The proxy
check makes fresh random sandboxes, so a failed cleanup there leaves its sandbox until it expires
(the cleanup login removes expired ones) and its daily rows until
`apps/api/scripts/clear_browser_test_spend.py` is run.
"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

type SpendRow = tuple[str, Decimal, datetime]


async def spend_rows_of(
    connection: AsyncConnection, tenant_ids: Sequence[UUID], *, not_before: datetime | None = None
) -> list[SpendRow]:
    """The `ai_spend` rows (kind, amount, instant) of these tenants, none older than `not_before`
    when it is given. Read before the tenants are deleted, because the rows cascade with them."""
    statement = text(
        "SELECT kind, amount_usd, created_at FROM ai_spend"
        " WHERE tenant_id IN :tenant_ids AND (CAST(:not_before AS timestamptz) IS NULL"
        " OR created_at >= :not_before)"
    ).bindparams(bindparam("tenant_ids", expanding=True))
    rows = await connection.execute(
        statement, {"tenant_ids": list(tenant_ids), "not_before": not_before}
    )
    return [(row.kind, row.amount_usd, row.created_at) for row in rows]


async def delete_daily_rows(
    connection: AsyncConnection, rows: Sequence[SpendRow], *, not_before: datetime | None = None
) -> None:
    """Delete one daily ledger row for each spend row: the same kind and amount, and the same
    instant. One to one, so a daily row is used for at most one spend row. With `not_before`, a
    row older than it is never taken."""
    for kind, amount, created_at in rows:
        await connection.execute(
            text(
                "DELETE FROM ai_spend_daily WHERE id = ("
                " SELECT id FROM ai_spend_daily"
                " WHERE kind = :kind AND amount_usd = :amount AND created_at = :created_at"
                " AND (CAST(:not_before AS timestamptz) IS NULL OR created_at >= :not_before)"
                " ORDER BY id LIMIT 1)"
            ),
            {"kind": kind, "amount": amount, "created_at": created_at, "not_before": not_before},
        )


async def remove_sandboxes(
    owner_engine: AsyncEngine,
    tenant_ids: Sequence[UUID],
    rows: Sequence[SpendRow],
    *,
    not_before: datetime | None = None,
) -> None:
    """Delete the daily rows that match `rows`, then the tenants, in one owner transaction. A
    failure rolls both back."""
    async with owner_engine.begin() as connection:
        await delete_daily_rows(connection, rows, not_before=not_before)
        for tenant_id in tenant_ids:
            await connection.execute(
                text("DELETE FROM tenants WHERE id = :tenant_id"), {"tenant_id": tenant_id}
            )
