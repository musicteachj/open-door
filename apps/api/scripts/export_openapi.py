"""Write the API's OpenAPI schema to apps/web/openapi.json, the source of the web app's client.

`--check` writes nothing. It fails if the schema file on disk differs from what the API produces
now, which is how CI keeps the schema, and so the generated client, in step with the API.
"""

import argparse
import base64
import json
import secrets
import sys
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT = REPO_ROOT / "apps" / "web" / "openapi.json"

# Building the schema never connects to the database, so any well-formed URL will do. Every
# Settings field is pinned in render_schema(), so the developer's environment can't change or break
# the export.
SCHEMA_ONLY_DATABASE_URL = "postgresql+asyncpg://schema:schema@localhost/schema"


def render_schema() -> str:
    settings = Settings(
        _env_file=None,
        app_env="development",
        log_level="INFO",
        database_url=SCHEMA_ONLY_DATABASE_URL,
        migration_database_url=None,
        cleanup_database_url=None,
        app_origin="http://localhost:5173",
        # The app refuses to start without a keyring. This one is random and thrown away: the schema
        # never encrypts anything.
        encryption_keyring_file=None,
        encryption_keyring=f"schema:{base64.b64encode(secrets.token_bytes(32)).decode()}",
    )
    return json.dumps(create_app(settings).openapi(), indent=2) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Export the API's OpenAPI schema for the web app.")
    parser.add_argument("--check", action="store_true", help="write nothing; fail if out of date")
    args = parser.parse_args(argv)

    schema = render_schema()
    relative = OUTPUT.relative_to(REPO_ROOT)
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != schema:
            print(f"{relative} is out of date. Run `make openapi` and commit the result.")
            return 1
        print(f"{relative} is up to date.")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(schema, encoding="utf-8")
    print(f"Wrote {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
