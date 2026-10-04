"""The bootstrap script's pure parts: its refusals and the password verifier. No database needed."""

import base64
import hashlib
import hmac
import re
from urllib.parse import quote

import pytest

from scripts.bootstrap_db_users import Login, logins_from, scram_verifier

OWNER_URL = "postgresql+asyncpg://opendoor:owner-pw@127.0.0.1:5433/opendoor"
APP_URL = "postgresql+asyncpg://od_app_login:app-pw@127.0.0.1:5433/opendoor"
CLEANUP_URL = "postgresql+asyncpg://od_cleanup_login:cleanup-pw@127.0.0.1:5433/opendoor"


def test_each_url_gives_its_login_the_matching_role() -> None:
    logins = logins_from(APP_URL, CLEANUP_URL, OWNER_URL)

    assert logins == [
        Login("od_app_login", "app-pw", "od_app", "DATABASE_URL"),
        Login("od_cleanup_login", "cleanup-pw", "od_cleanup", "CLEANUP_DATABASE_URL"),
    ]


def test_the_cleanup_url_is_optional() -> None:
    assert [login.role for login in logins_from(APP_URL, None, OWNER_URL)] == ["od_app"]


def test_the_owner_may_not_be_the_apis_login() -> None:
    owner_as_app = "postgresql+asyncpg://opendoor:owner-pw@127.0.0.1:5433/opendoor"

    with pytest.raises(SystemExit, match=r"DATABASE_URL names 'opendoor'.*login user of its own"):
        logins_from(owner_as_app, None, OWNER_URL)


def test_the_owner_may_not_be_the_cleanup_login() -> None:
    with pytest.raises(SystemExit, match=r"CLEANUP_DATABASE_URL names 'opendoor'"):
        logins_from(APP_URL, OWNER_URL, OWNER_URL)


@pytest.mark.parametrize("role", ["od_app", "od_cleanup"])
def test_a_login_may_not_be_named_after_a_role(role: str) -> None:
    named_for_role = f"postgresql+asyncpg://{role}:pw@127.0.0.1:5433/opendoor"

    with pytest.raises(SystemExit, match=f"DATABASE_URL names '{role}'"):
        logins_from(named_for_role, None, OWNER_URL)
    with pytest.raises(SystemExit, match=f"CLEANUP_DATABASE_URL names '{role}'"):
        logins_from(APP_URL, named_for_role, OWNER_URL)


def test_the_two_urls_may_not_name_the_same_user() -> None:
    with pytest.raises(SystemExit, match="must name different users"):
        logins_from(APP_URL, APP_URL, OWNER_URL)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://od_app_login@127.0.0.1:5433/opendoor",
        "postgresql+asyncpg://:app-pw@127.0.0.1:5433/opendoor",
    ],
)
def test_a_login_needs_a_user_name_and_a_password(url: str) -> None:
    with pytest.raises(SystemExit, match="must include a user name and a password"):
        logins_from(url, None, OWNER_URL)


@pytest.mark.parametrize("password", ["p%C3%A4ssword", "tab%09inside", "bell%07", "%E2%82%AC"])
def test_a_password_that_is_not_printable_ascii_is_refused_without_being_shown(
    password: str,
) -> None:
    # Postgres runs SASLprep on a password before hashing it, and SASLprep leaves only printable
    # ASCII unchanged. The script does not implement it, so it refuses everything else.
    url = f"postgresql+asyncpg://od_app_login:{password}@127.0.0.1:5433/opendoor"

    with pytest.raises(SystemExit, match="printable ASCII") as refusal:
        logins_from(url, None, OWNER_URL)

    assert password not in str(refusal.value)


def test_every_printable_ascii_character_is_accepted_in_a_password() -> None:
    every_character = "".join(chr(code) for code in range(0x20, 0x7F))
    quoted = quote(every_character, safe="")

    [login] = logins_from(
        f"postgresql+asyncpg://od_app_login:{quoted}@h:5433/opendoor", None, OWNER_URL
    )

    assert login.password == every_character


# The example in RFC 7677, section 3: user "user", password "pencil", salt W22ZaJ0S..., 4096 rounds.
RFC_7677_SALT = base64.b64decode("W22ZaJ0SNY7soEsUEjb6gQ==")
RFC_7677_NONCE = "rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0"
RFC_7677_AUTH_MESSAGE = (
    f"n=user,r=rOprNGfwEbeRWgbNEkqO,r={RFC_7677_NONCE},s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096,"
    f"c=biws,r={RFC_7677_NONCE}"
)
RFC_7677_CLIENT_PROOF = base64.b64decode("dHzbZapWIk4jUhN+Ute9ytag9zjfMHgsqmmiz7AndVQ=")
RFC_7677_SERVER_SIGNATURE = base64.b64decode("6rriTRBi23WpRR/wtup+mMhUZUn/dB5nLTJRsjl95G4=")
KNOWN_VERIFIER = (
    "SCRAM-SHA-256$4096:W22ZaJ0SNY7soEsUEjb6gQ==$"
    "WG5d8oPm3OtcPnkdi4Uo7BkeZkBFzpcXkuLmtbsT4qY=:wfPLwcE6nTWhTAmQ7tl2KeoiWGPlZqQxSrmfPwDl2dU="
)


def test_the_verifier_for_a_fixed_salt_is_the_known_value() -> None:
    assert scram_verifier("pencil", salt=RFC_7677_SALT) == KNOWN_VERIFIER


def test_the_verifier_agrees_with_the_rfc_7677_exchange() -> None:
    # The RFC's client proof is ClientKey XOR HMAC(StoredKey, AuthMessage), and its server
    # signature is HMAC(ServerKey, AuthMessage). Both can be checked against the verifier alone.
    _, _, keys = scram_verifier("pencil", salt=RFC_7677_SALT).split("$")
    stored_key, server_key = (base64.b64decode(key) for key in keys.split(":"))
    auth_message = RFC_7677_AUTH_MESSAGE.encode()

    client_signature = hmac.digest(stored_key, auth_message, "sha256")
    client_key = bytes(a ^ b for a, b in zip(RFC_7677_CLIENT_PROOF, client_signature, strict=True))

    assert hashlib.sha256(client_key).digest() == stored_key
    assert hmac.digest(server_key, auth_message, "sha256") == RFC_7677_SERVER_SIGNATURE


def test_each_verifier_gets_a_fresh_random_salt_and_never_contains_the_password() -> None:
    first = scram_verifier("a long enough secret")
    second = scram_verifier("a long enough secret")

    assert first != second
    base64_part = r"[A-Za-z0-9+/]"
    shape = rf"SCRAM-SHA-256\$4096:{base64_part}{{22}}==\${base64_part}{{43}}=:{base64_part}{{43}}="
    assert re.fullmatch(shape, first)
    assert "secret" not in first
