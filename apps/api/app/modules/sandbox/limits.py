"""How many sandboxes one address, and all addresses together, may start (ADR 0021).

Each start leaves a row in `sandbox_starts`: a keyed hash of the visitor's address and a time. The
route counts them in a short transaction of its own under an advisory lock, which also records the
start, so two starts at the limit can't both pass. That happens before the visitor's current
session is touched, so a refused visitor keeps the sandbox they have. The lock is released before
the sandbox is seeded. A start whose seed then fails stays counted (deliberately conservative).

All times are the database's (`now()`), the clock that stamps the rows.
"""

import hashlib
import hmac
import ipaddress
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.admission import seconds_until_next_utc_day
from app.db.models import SandboxStart

logger = logging.getLogger(__name__)

# Every address that can't be read as one (or a request with no client) shares one bucket, so it
# is limited together instead of escaping the limits.
UNKNOWN_ADDRESS: Final = "unknown"
# An IPv6 visitor gets a whole /64 to themselves, so one cannot dodge the limit by rotating
# addresses inside it.
IPV6_PREFIX_LENGTH: Final = 64


_HOUR = timedelta(hours=1)
_DAY = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class StartLimits:
    per_hour: int
    per_day: int
    daily_total: int


class StartLimitError(Exception):
    """A start was refused. `scope` is `address` (the hourly or daily limit of one address) or
    `day` (all addresses, this UTC day). `retry_after_seconds` is at least 1."""

    def __init__(self, scope: str, retry_after_seconds: int) -> None:
        super().__init__(scope)
        self.scope = scope
        self.retry_after_seconds = max(1, retry_after_seconds)


def normalized_address(address: str | None) -> str:
    """The text that gets hashed: IPv4 as is, an IPv4-mapped IPv6 address as the IPv4, any other
    IPv6 address as its /64 network, and anything else as one shared bucket."""
    if not address:
        logger.warning("A sandbox start had no client address; counting it in the shared bucket")
        return UNKNOWN_ADDRESS
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        # The raw value is deliberately not logged.
        logger.warning("A sandbox start had an unreadable client address; using the shared bucket")
        return UNKNOWN_ADDRESS
    if isinstance(parsed, ipaddress.IPv6Address):
        if parsed.ipv4_mapped is not None:
            return str(parsed.ipv4_mapped)
        return str(ipaddress.ip_network((parsed, IPV6_PREFIX_LENGTH), strict=False))
    return str(parsed)


def address_hash(key: bytes, address: str | None) -> bytes:
    """HMAC-SHA256 of the normalized address under `key`: 32 bytes, not reversible without it."""
    return hmac.new(key, normalized_address(address).encode(), hashlib.sha256).digest()


# One query for the three counts. The window is the last 24 hours (the UTC day is inside it).
COUNTS = text(
    """
    SELECT
        count(*) FILTER (WHERE ip_hash = :ip_hash AND created_at > now() - interval '1 hour')
            AS hour_count,
        count(*) FILTER (WHERE ip_hash = :ip_hash) AS day_count,
        count(*) FILTER (
            WHERE created_at >= (date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')
        ) AS total_count,
        now() AS now
    FROM sandbox_starts
    WHERE created_at > now() - interval '24 hours'
    """
)

# This address's starts in the last 24 hours, oldest first. Read only when a limit binds, to say
# when the wait ends.
ADDRESS_STARTS = text(
    """
    SELECT created_at FROM sandbox_starts
    WHERE ip_hash = :ip_hash AND created_at > now() - interval '24 hours'
    ORDER BY created_at
    """
)


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(1, math.ceil((moment - now).total_seconds()))


def _wait_for_window(
    starts: list[datetime], count: int, limit: int, window: timedelta, now: datetime
) -> int:
    """Seconds until a start is allowed again under one window's limit.

    A start is allowed when the count is below the limit, so `count - limit + 1` of the oldest
    starts must leave the window. The wait ends when the last of those does. (At exactly the
    limit that is the oldest start; over it, because the limit was lowered, a later one.)
    """
    inside = [created_at for created_at in starts if created_at > now - window]
    if not inside:
        # The counts and the list are separate statements, so rows can vanish between them (the
        # cleanup job). With nothing to measure from, wait the whole window: the conservative
        # answer, never an error.
        return _seconds_until(now + window, now)
    leaving = inside[min(max(count - limit, 0), len(inside) - 1)]
    return _seconds_until(leaving + window, now)


async def check_start_limits(db: AsyncSession, ip_hash: bytes, limits: StartLimits) -> None:
    """Raise `StartLimitError` if this address, or the day, is at a limit. Changes nothing.

    The day's total is checked first, and its wait is until the next UTC day. When this address is
    at its hourly limit, its daily limit, or both, the wait is the longest of them: the visitor
    can't start sooner than every binding limit allows.
    """
    row = (await db.execute(COUNTS, {"ip_hash": ip_hash})).one()
    now: datetime = row.now
    if row.total_count >= limits.daily_total:
        raise StartLimitError("day", seconds_until_next_utc_day(now))
    hour_binds = row.hour_count >= limits.per_hour
    day_binds = row.day_count >= limits.per_day
    if not (hour_binds or day_binds):
        return
    starts: list[datetime] = list(
        (await db.execute(ADDRESS_STARTS, {"ip_hash": ip_hash})).scalars()
    )
    waits: list[int] = []
    if hour_binds:
        waits.append(_wait_for_window(starts, row.hour_count, limits.per_hour, _HOUR, now))
    if day_binds:
        waits.append(_wait_for_window(starts, row.day_count, limits.per_day, _DAY, now))
    raise StartLimitError("address", max(waits))


async def record_start(db: AsyncSession, ip_hash: bytes) -> None:
    """Add this start to the count. The database stamps its time."""
    await db.execute(insert(SandboxStart).values(ip_hash=ip_hash))
