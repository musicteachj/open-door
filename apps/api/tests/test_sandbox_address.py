"""How a visitor's address becomes the value the start counter stores."""

import hashlib
import hmac
import logging

import pytest

from app.modules.sandbox.limits import address_hash, normalized_address

KEY = b"k" * 32


def test_the_hash_is_the_hmac_of_the_address_under_the_key() -> None:
    assert (
        address_hash(KEY, "203.0.113.5") == hmac.new(KEY, b"203.0.113.5", hashlib.sha256).digest()
    )
    assert len(address_hash(KEY, "203.0.113.5")) == 32


def test_another_key_gives_another_hash() -> None:
    assert address_hash(KEY, "203.0.113.5") != address_hash(b"j" * 32, "203.0.113.5")


def test_an_ipv4_mapped_ipv6_address_is_the_ipv4_address() -> None:
    assert address_hash(KEY, "::ffff:203.0.113.5") == address_hash(KEY, "203.0.113.5")
    assert normalized_address("::ffff:203.0.113.5") == "203.0.113.5"


def test_ipv6_addresses_in_one_64_share_a_hash() -> None:
    first = address_hash(KEY, "2001:db8:1:2::1")
    assert first == address_hash(KEY, "2001:db8:1:2:aaaa:bbbb:cccc:dddd")
    assert first != address_hash(KEY, "2001:db8:1:3::1")
    assert normalized_address("2001:DB8:1:2::1") == "2001:db8:1:2::/64"


def test_different_ipv4_addresses_differ() -> None:
    assert address_hash(KEY, "203.0.113.5") != address_hash(KEY, "203.0.113.6")


@pytest.mark.parametrize("value", [None, "", "testclient", "not an address", "999.1.1.1"])
def test_anything_unreadable_shares_one_bucket_and_is_not_logged(
    value: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        hashed = address_hash(KEY, value)
    assert hashed == address_hash(KEY, None)
    assert caplog.records
    for record in caplog.records:
        if value:
            assert value not in record.getMessage()


def test_the_wait_for_a_window_with_no_starts_left_is_the_whole_window_not_an_error() -> None:
    from datetime import UTC, datetime, timedelta

    from app.modules.sandbox.limits import _wait_for_window

    now = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
    # The counts said the limit was reached, but the rows were gone by the time they were read.
    assert _wait_for_window([], 5, 5, timedelta(hours=1), now) == 3600
    outside = [now - timedelta(hours=2)]
    assert _wait_for_window(outside, 5, 5, timedelta(hours=1), now) == 3600
