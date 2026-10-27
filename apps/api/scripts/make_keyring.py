"""Write a development keyring: one random 256-bit key under a new ID, mode 600.

`make setup` and `make keyring` run it. It never overwrites a file, since replacing the keyring
would make every encrypted row unreadable. The key is never printed.
"""

import argparse
import base64
import os
import secrets
import sys
from datetime import UTC, datetime

from pydantic import ValidationError

from app.core.config import Settings
from app.core.encryption import DEFAULT_KEYRING_PATH, KEY_BYTES, resolve_keyring_path


def configured_path() -> str:
    """The keyring file the API will read: ENCRYPTION_KEYRING_FILE, or the default when it's unset
    or the settings can't load yet."""
    try:
        keyring_file = Settings().encryption_keyring_file
    except ValidationError:
        return DEFAULT_KEYRING_PATH
    return DEFAULT_KEYRING_PATH if keyring_file is None else keyring_file.get_secret_value()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Write a development keyring.")
    parser.add_argument("path", nargs="?", default=None)
    path = resolve_keyring_path(parser.parse_args(argv).path or configured_path())

    key_id = f"k{datetime.now(UTC):%Y%m%d}-{secrets.token_hex(3)}"
    line = f"{key_id}:{base64.b64encode(secrets.token_bytes(KEY_BYTES)).decode()}\n"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        # O_EXCL fails on an existing file or a symlink, so this can't overwrite or follow one.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"{path} already exists; leaving it alone.")
        return 0
    with os.fdopen(fd, "w", encoding="utf-8") as keyring:
        keyring.write(line)
    print(f"Wrote {path} (key {key_id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
