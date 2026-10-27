"""The envelope: sealing a value to its place, and wrapping data keys under a keyring."""

import base64
import re
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.ai.conversations import ConversationCipher
from app.core.encryption import (
    VERSION_BYTE,
    DecryptionFailed,
    KeyProvider,
    LocalKeyProvider,
    Place,
    load_key_provider,
    new_data_key,
    open_,
    seal,
    wrap_aad,
)

TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
ROW = uuid.UUID("22222222-2222-2222-2222-222222222222")
PLACE = Place("ai_turns", "question_ciphertext", TENANT, ROW)
WORDS = b"my manager keeps making comments about my age"


def line(key_id: str, key: bytes) -> str:
    return f"{key_id}:{base64.b64encode(key).decode()}"


def ring(*keys: tuple[str, bytes]) -> LocalKeyProvider:
    return LocalKeyProvider.from_keyring("\n".join(line(i, k) for i, k in keys))


KEY_A = bytes(range(32))
KEY_B = bytes(range(32, 64))


def test_a_value_opens_in_the_place_it_was_sealed_for() -> None:
    data_key = new_data_key()
    assert open_(data_key, seal(data_key, WORDS, place=PLACE), place=PLACE) == WORDS


@pytest.mark.parametrize(
    "other",
    [
        PLACE._replace(table="ai_feedback"),
        PLACE._replace(column="answer_ciphertext"),
        PLACE._replace(tenant_id=uuid.uuid4()),
        PLACE._replace(row_id=uuid.uuid4()),
    ],
    ids=["table", "column", "tenant", "row"],
)
def test_a_ciphertext_moved_to_any_other_place_fails(other: Place) -> None:
    data_key = new_data_key()
    sealed = seal(data_key, WORDS, place=PLACE)
    with pytest.raises(DecryptionFailed):
        open_(data_key, sealed, place=other)


def test_the_parts_of_a_place_are_length_prefixed_not_joined() -> None:
    # "ab"+"c" and "a"+"bc" would be the same joined string.
    data_key = new_data_key()
    sealed = seal(data_key, WORDS, place=PLACE._replace(table="ab", column="c"))
    with pytest.raises(DecryptionFailed):
        open_(data_key, sealed, place=PLACE._replace(table="a", column="bc"))


def test_another_data_key_cannot_open_it() -> None:
    sealed = seal(new_data_key(), WORDS, place=PLACE)
    with pytest.raises(DecryptionFailed):
        open_(new_data_key(), sealed, place=PLACE)


def test_a_flipped_byte_anywhere_fails_with_one_error_that_holds_no_secret() -> None:
    data_key = new_data_key()
    sealed = seal(data_key, WORDS, place=PLACE)
    messages = set()
    for index in range(len(sealed)):
        tampered = bytearray(sealed)
        tampered[index] ^= 0x01
        with pytest.raises(DecryptionFailed) as excinfo:
            open_(data_key, bytes(tampered), place=PLACE)
        messages.add(str(excinfo.value))
        assert WORDS.decode() not in repr(excinfo.value)
    assert len(messages) == 1  # a fixed message, whichever byte changed


@pytest.mark.parametrize("cut", [0, 1, 12, 13, 28])
def test_a_truncated_ciphertext_fails_the_same_way(cut: int) -> None:
    data_key = new_data_key()
    sealed = seal(data_key, WORDS, place=PLACE)
    with pytest.raises(DecryptionFailed):
        open_(data_key, sealed[:cut], place=PLACE)


def test_two_seals_of_the_same_text_differ_and_start_with_the_version_byte() -> None:
    data_key = new_data_key()
    first = seal(data_key, WORDS, place=PLACE)
    second = seal(data_key, WORDS, place=PLACE)
    assert first != second
    assert first[:1] == second[:1] == VERSION_BYTE
    assert first[1:13] != second[1:13]  # the nonce


def test_a_ciphertext_holds_no_plaintext() -> None:
    assert WORDS not in seal(new_data_key(), WORDS, place=PLACE)


def test_empty_text_seals_and_opens() -> None:
    data_key = new_data_key()
    assert open_(data_key, seal(data_key, b"", place=PLACE), place=PLACE) == b""


def test_a_data_key_is_32_random_bytes() -> None:
    assert len(new_data_key()) == 32
    assert new_data_key() != new_data_key()


def test_a_wrapped_data_key_unwraps_only_for_its_tenant_table_and_owner() -> None:
    keys = ring(("k1", KEY_A))
    data_key = new_data_key()
    aad = wrap_aad(TENANT, "ai_conversations", ROW)
    key_id, wrapped = keys.wrap(data_key, aad=aad)
    assert keys.unwrap(key_id, wrapped, aad=aad) == data_key
    for other in (
        wrap_aad(uuid.uuid4(), "ai_conversations", ROW),
        wrap_aad(TENANT, "cases", ROW),
        wrap_aad(TENANT, "ai_conversations", uuid.uuid4()),
    ):
        with pytest.raises(DecryptionFailed):
            keys.unwrap(key_id, wrapped, aad=other)


def test_a_wrapped_key_with_a_flipped_byte_fails() -> None:
    keys = ring(("k1", KEY_A))
    aad = wrap_aad(TENANT, "ai_conversations", ROW)
    key_id, wrapped = keys.wrap(new_data_key(), aad=aad)
    tampered = bytearray(wrapped)
    tampered[-1] ^= 0x01
    with pytest.raises(DecryptionFailed):
        keys.unwrap(key_id, bytes(tampered), aad=aad)


def test_the_newest_key_wraps_and_an_older_key_still_unwraps() -> None:
    old = ring(("old", KEY_A))
    aad = wrap_aad(TENANT, "ai_conversations", ROW)
    data_key = new_data_key()
    old_id, old_wrapped = old.wrap(data_key, aad=aad)
    assert old_id == "old"

    rotated = ring(("new", KEY_B), ("old", KEY_A))
    assert rotated.wrap(data_key, aad=aad)[0] == "new"
    assert rotated.unwrap(old_id, old_wrapped, aad=aad) == data_key


def test_an_unknown_key_id_fails() -> None:
    keys = ring(("k1", KEY_A))
    aad = wrap_aad(TENANT, "ai_conversations", ROW)
    _, wrapped = keys.wrap(new_data_key(), aad=aad)
    with pytest.raises(DecryptionFailed):
        keys.unwrap("gone", wrapped, aad=aad)


def test_a_key_of_the_same_id_but_other_bytes_cannot_unwrap() -> None:
    aad = wrap_aad(TENANT, "ai_conversations", ROW)
    key_id, wrapped = ring(("k1", KEY_A)).wrap(new_data_key(), aad=aad)
    with pytest.raises(DecryptionFailed):
        ring(("k1", KEY_B)).unwrap(key_id, wrapped, aad=aad)


def test_the_local_provider_is_a_key_provider() -> None:
    provider: KeyProvider = ring(("k1", KEY_A))
    assert provider.wrap(new_data_key(), aad=b"x")[0] == "k1"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n\n  ",
        "# only a comment",
        "no-colon-here",
        "k1:",
        ":" + base64.b64encode(KEY_A).decode(),
        "k1:not base64 !!",
        line("k1", KEY_A[:16]),
        line("k1", KEY_A + b"x"),
        line("k1", KEY_A) + "\n" + line("k1", KEY_B),  # a repeated ID
        "bad id:" + base64.b64encode(KEY_A).decode(),
    ],
    ids=[
        "empty",
        "blank",
        "comment-only",
        "no-colon",
        "no-key",
        "no-id",
        "not-base64",
        "short",
        "long",
        "repeated-id",
        "id-with-space",
    ],
)
def test_a_bad_keyring_is_refused_when_it_loads(text: str) -> None:
    with pytest.raises(ValueError, match="keyring"):
        LocalKeyProvider.from_keyring(text)


def test_a_refused_keyring_does_not_echo_the_key() -> None:
    secret = base64.b64encode(KEY_A[:16]).decode()
    with pytest.raises(ValueError, match="keyring") as excinfo:
        LocalKeyProvider.from_keyring(f"k1:{secret}")
    assert secret not in str(excinfo.value)


def test_blank_lines_and_comments_in_a_keyring_are_skipped() -> None:
    text = f"# newest first\n\n{line('k1', KEY_A)}\n  \n{line('k0', KEY_B)}\n"
    assert LocalKeyProvider.from_keyring(text).key_ids == ("k1", "k0")


def test_the_test_key_is_recognized() -> None:
    assert ring(("test", bytes(32))).uses_test_key
    assert ring(("k1", KEY_A), ("old", bytes(32))).uses_test_key
    assert not ring(("k1", KEY_A)).uses_test_key


def test_nothing_shows_key_bytes_in_a_repr_or_str() -> None:
    keys = ring(("k1", KEY_A), ("k0", KEY_B))
    data_key = new_data_key()
    shown: list[Any] = [keys, data_key, *vars(keys).values()]
    shown += [v for value in vars(keys).values() if isinstance(value, dict) for v in value.values()]
    needles = [
        KEY_A,
        KEY_B,
        bytes(data_key),
        base64.b64encode(KEY_A),
        base64.b64encode(KEY_B),
        base64.b64encode(bytes(data_key)),
        bytes(data_key).hex().encode(),
        KEY_A.hex().encode(),
    ]
    for thing in shown:
        for text in (repr(thing), str(thing), f"{thing!r}", f"{thing}"):
            for needle in needles:
                assert needle.decode("latin-1") not in text
            assert not re.search(r"\\x[0-9a-f]{2}", text)


def test_a_keyring_path_that_is_a_directory_is_refused_with_a_fixed_message(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "ring"
    directory.mkdir(mode=0o700)
    _refused_without_a_cause(directory)


def test_a_keyring_file_that_is_not_utf8_is_refused_with_a_fixed_message(tmp_path: Path) -> None:
    path = tmp_path / "ring"
    path.write_bytes(b"k1:\xff\xfe secret-looking bytes")
    path.chmod(0o600)
    error = _refused_without_a_cause(path)
    assert "secret-looking" not in str(error)


def _refused_without_a_cause(path: Path) -> ValueError:
    with pytest.raises(ValueError, match="keyring file") as excinfo:
        load_key_provider(keyring=None, keyring_file=str(path))
    error = excinfo.value
    assert str(error) == "The keyring file could not be read as text. Check that it is a file."
    assert error.__cause__ is None
    assert error.__context__ is None
    assert error.__suppress_context__
    return error


@pytest.mark.parametrize("size", [0, 16, 24, 31, 33, 64])
def test_a_data_key_of_the_wrong_length_is_refused_everywhere(size: int) -> None:
    short = bytes(size)
    good = new_data_key()
    sealed = seal(good, WORDS, place=PLACE)
    keys = ring(("k1", KEY_A))
    aad = wrap_aad(TENANT, "ai_conversations", ROW)
    with pytest.raises(ValueError, match="32 bytes"):
        seal(short, WORDS, place=PLACE)
    with pytest.raises(ValueError, match="32 bytes"):
        open_(short, sealed, place=PLACE)
    with pytest.raises(ValueError, match="32 bytes"):
        keys.wrap(short, aad=aad)


def test_a_wrapped_value_that_is_not_a_32_byte_key_does_not_unwrap() -> None:
    # Something sealed under the key-encryption key with the right aad, but not a data key.
    aad = wrap_aad(TENANT, "ai_conversations", ROW)
    keys = ring(("k1", KEY_A))
    odd = keys._keys["k1"].encrypt(bytes(16), aad)
    with pytest.raises(DecryptionFailed):
        keys.unwrap("k1", odd, aad=aad)


# --- The conversation cipher's tool-call summaries --------------------------------------------


def sealed_call() -> tuple[ConversationCipher, uuid.UUID, dict[str, Any]]:
    cipher = ConversationCipher(TENANT, uuid.uuid4(), new_data_key())
    turn_id = uuid.uuid4()
    [call] = cipher.seal_tool_calls(turn_id, [{"name": "search_handbook", "inputSummary": "sick"}])
    return cipher, turn_id, call


@pytest.mark.parametrize(
    "damage",
    [
        lambda s: s[:10] + "!" + s[10:],  # a stray character that a lenient decoder drops
        lambda s: s[:-1],  # bad padding
        lambda s: 7,  # not a string
        lambda s: None,
    ],
    ids=["stray-character", "bad-padding", "not-a-string", "none"],
)
def test_a_damaged_tool_call_summary_raises_decryption_failed_with_no_cause(
    damage: Callable[[str], Any],
) -> None:
    cipher, turn_id, call = sealed_call()
    # The untouched call opens.
    assert cipher.open_tool_calls(turn_id, [call])[0]["inputSummary"] == "sick"
    broken = {**call, "inputSummary": damage(call["inputSummary"])}
    with pytest.raises(DecryptionFailed) as raised:
        cipher.open_tool_calls(turn_id, [broken])
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_a_relative_keyring_path_resolves_against_apps_api_not_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.core import encryption

    monkeypatch.chdir(tmp_path)
    api_dir = Path(encryption.__file__).resolve().parents[2]
    assert api_dir.name == "api"
    assert (api_dir / "app").is_dir()
    assert encryption.resolve_keyring_path(".keys/keyring") == api_dir / ".keys" / "keyring"
    assert encryption.resolve_keyring_path(encryption.DEFAULT_KEYRING_PATH) == (
        api_dir / ".keys" / "keyring"
    )


def test_an_absolute_keyring_path_stays_as_given(tmp_path: Path) -> None:
    from app.core.encryption import resolve_keyring_path

    assert resolve_keyring_path(str(tmp_path / "ring")) == tmp_path / "ring"


def test_the_default_keyring_file_is_found_from_another_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.core import encryption

    api_dir = tmp_path / "api"
    ring = api_dir / ".keys" / "keyring"
    ring.parent.mkdir(parents=True)
    ring.write_text("k1:" + base64.b64encode(bytes(32)).decode() + "\n")
    ring.chmod(0o600)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(encryption, "_API_DIR", api_dir)
    monkeypatch.chdir(elsewhere)

    keys = encryption.load_key_provider(keyring=None, keyring_file=encryption.DEFAULT_KEYRING_PATH)

    assert keys.key_ids == ("k1",)
