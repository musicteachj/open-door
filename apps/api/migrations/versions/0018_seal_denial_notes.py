"""Seal the denial note: a request's note is stored encrypted, in three columns.

Phase 8, stage 3. `time_off_requests.decision_note` was plaintext, text a person wrote (ADR 0015's
amendment moves it into the encrypted scope). Now each noted request has a data key of its own:

  - `note_key_id`, `note_wrapped_key`, `note_ciphertext`: all null or all set, and set only on a
    denied request. The 300-character limit can no longer be a CHECK on ciphertext, so the
    service enforces it (`checked_note`).
  - The "pending and recorded requests have no decision fields" CHECK reads the new columns.
  - The immutability trigger watches the new columns where it watched `decision_note`: they change
    only on pending to approved or denied.
  - The API's column-level UPDATE grant moves from `decision_note` to the three new columns.

Data step. Any existing non-blank note is sealed with the key provider the API's settings name
(ENCRYPTION_KEYRING or ENCRYPTION_KEYRING_FILE), then `decision_note` is dropped. The keyring is
loaded only if some row has a note, so an empty database (CI, `make prod-local`, Phase 9) needs
none. A blank note becomes no note. The downgrade opens sealed notes back into `decision_note` the
same way. The data step runs as the migration's owner, the table's owner, and an owner bypasses
row-level security unless it is FORCEd (0009 forces it here). So the step runs between `NO FORCE`
and `FORCE ROW LEVEL SECURITY` in the same transaction (DDL is transactional), and the owner sees
every row whether or not it is a superuser: no note can be dropped unseen. The data-step functions
take a connection and a loader so a test can run them on a scratch table. The app's modules are
imported inside the functions that need them, so an empty database upgrades without them.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-10
"""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from app.core.encryption import KeyProvider, Place

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The format of a stored note, frozen here: a later change to the app's helpers must not change
# what this migration reads or writes. A test keeps it equal to app/modules/timeoff/notes.py.
TABLE = "time_off_requests"
COLUMN = "decision_note"

_STATUS_CHECK_PREFIX = "(status NOT IN ('pending', 'recorded') OR (decided_by IS NULL AND "
_STATUS_CHECK_SUFFIX = (
    " AND canceled_at IS NULL))"
    " AND (status NOT IN ('approved', 'denied') OR (decided_by IS NOT NULL"
    " AND decided_at IS NOT NULL AND canceled_at IS NULL))"
    " AND (status <> 'canceled' OR (canceled_at IS NOT NULL"
    " AND (decided_by IS NULL) = (decided_at IS NULL)))"
)
OLD_STATUS_CHECK = (
    f"{_STATUS_CHECK_PREFIX}decided_at IS NULL AND decision_note IS NULL{_STATUS_CHECK_SUFFIX}"
)
NEW_STATUS_CHECK = (
    f"{_STATUS_CHECK_PREFIX}decided_at IS NULL AND note_key_id IS NULL"
    f" AND note_wrapped_key IS NULL AND note_ciphertext IS NULL{_STATUS_CHECK_SUFFIX}"
)
OLD_NOTE_CHECK = (
    "decision_note IS NULL OR (char_length(decision_note) <= 300 AND status = 'denied')"
)
NEW_NOTE_CHECK = (
    "(note_key_id IS NULL AND note_wrapped_key IS NULL AND note_ciphertext IS NULL)"
    " OR (note_key_id IS NOT NULL AND note_wrapped_key IS NOT NULL"
    " AND note_ciphertext IS NOT NULL AND status = 'denied')"
)

STATUS_CHECK_NAME = "ck_time_off_requests_decision_matches_status"
OLD_NOTE_CHECK_NAME = "ck_time_off_requests_decision_note_is_a_short_denial_note"
NEW_NOTE_CHECK_NAME = "ck_time_off_requests_sealed_note_is_whole_and_denied"
TRIGGER = "enforce_time_off_request_update"


def trigger_function(decision_columns: tuple[str, ...]) -> str:
    """0009's function, watching the given columns where it watched the decision fields."""
    new = ", ".join(f"NEW.{c}" for c in decision_columns)
    old = ", ".join(f"OLD.{c}" for c in decision_columns)
    return f"""
    CREATE OR REPLACE FUNCTION app.enforce_time_off_request_update() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        IF NOT (
            (OLD.status = 'pending' AND NEW.status IN ('approved', 'denied', 'canceled'))
            OR (OLD.status IN ('approved', 'recorded') AND NEW.status = 'canceled')
        ) THEN
            RAISE EXCEPTION 'a time-off request cannot change from % to %', OLD.status, NEW.status
                USING ERRCODE = 'OD003';
        END IF;
        IF ({new})
                IS DISTINCT FROM ({old})
            AND NOT (OLD.status = 'pending' AND NEW.status IN ('approved', 'denied'))
        THEN
            RAISE EXCEPTION 'the decision on a time-off request is written only when it is decided'
                USING ERRCODE = 'OD003';
        END IF;
        IF NEW.canceled_at IS DISTINCT FROM OLD.canceled_at AND NEW.status <> 'canceled' THEN
            RAISE EXCEPTION 'canceled_at is written only when a time-off request is canceled'
                USING ERRCODE = 'OD003';
        END IF;
        RETURN NEW;
    END
    $$
    """


OLD_DECISION_COLUMNS = ("decided_by", "decided_at", "decision_note")
NEW_DECISION_COLUMNS = (
    "decided_by",
    "decided_at",
    "note_key_id",
    "note_wrapped_key",
    "note_ciphertext",
)

CREATE_TRIGGER = f"""
    CREATE TRIGGER {TRIGGER} BEFORE UPDATE ON time_off_requests
        FOR EACH ROW EXECUTE FUNCTION app.enforce_time_off_request_update()
"""

KeyLoader = Callable[[], "KeyProvider"]


def settings_key_loader() -> "KeyProvider":
    """The key provider the API's settings name. Called only when a note has to be moved."""
    from app.core.config import get_settings
    from app.core.encryption import load_key_provider

    settings = get_settings()
    keyring = settings.encryption_keyring
    keyring_file = settings.encryption_keyring_file
    keys = load_key_provider(
        keyring=None if keyring is None else keyring.get_secret_value(),
        keyring_file=None if keyring_file is None else keyring_file.get_secret_value(),
    )
    # The API's own rule (`build_key_provider`): real notes are never sealed under the published
    # test key, which only APP_ENV=test accepts.
    if keys.uses_test_key and settings.app_env != "test":
        msg = "The keyring holds the test key, which only APP_ENV=test accepts. Run `make keyring`."
        raise ValueError(msg)
    return keys


def _place(tenant_id: UUID, request_id: UUID) -> "Place":
    from app.core.encryption import Place

    return Place(TABLE, COLUMN, tenant_id, request_id)


def seal_existing_notes(connection: sa.Connection, load_keys: KeyLoader) -> int:
    """Seal each non-blank `decision_note` into the three note columns and clear the plaintext.
    A blank note becomes no note. `load_keys` is called only if some row has a note. Returns how
    many notes were sealed."""
    rows = connection.execute(
        sa.text(
            "SELECT id, tenant_id, decision_note FROM time_off_requests"
            " WHERE decision_note IS NOT NULL"
        )
    ).all()
    if not rows:
        return 0
    from app.core.encryption import new_data_key, seal, wrap_aad

    keys = load_keys()
    sealed = 0
    for request_id, tenant_id, note in rows:
        if not note.strip():
            connection.execute(
                sa.text("UPDATE time_off_requests SET decision_note = NULL WHERE id = :id"),
                {"id": request_id},
            )
            continue
        data_key = new_data_key()
        key_id, wrapped = keys.wrap(data_key, aad=wrap_aad(tenant_id, TABLE, request_id))
        ciphertext = seal(data_key, note.encode(), place=_place(tenant_id, request_id))
        connection.execute(
            sa.text(
                "UPDATE time_off_requests SET decision_note = NULL, note_key_id = :key_id,"
                " note_wrapped_key = :wrapped, note_ciphertext = :ciphertext WHERE id = :id"
            ),
            {"id": request_id, "key_id": key_id, "wrapped": wrapped, "ciphertext": ciphertext},
        )
        sealed += 1
    return sealed


def open_sealed_notes(connection: sa.Connection, load_keys: KeyLoader) -> int:
    """The reverse: open each sealed note into `decision_note` and clear the three columns.
    `load_keys` is called only if some row has a sealed note. Returns how many were opened."""
    rows = connection.execute(
        sa.text(
            "SELECT id, tenant_id, note_key_id, note_wrapped_key, note_ciphertext"
            " FROM time_off_requests WHERE note_ciphertext IS NOT NULL"
        )
    ).all()
    if not rows:
        return 0
    from app.core.encryption import DataKey, open_, wrap_aad

    keys = load_keys()
    for request_id, tenant_id, key_id, wrapped, ciphertext in rows:
        aad = wrap_aad(tenant_id, TABLE, request_id)
        data_key = DataKey(keys.unwrap(key_id, bytes(wrapped), aad=aad))
        note = open_(data_key, bytes(ciphertext), place=_place(tenant_id, request_id)).decode()
        connection.execute(
            sa.text(
                "UPDATE time_off_requests SET decision_note = :note, note_key_id = NULL,"
                " note_wrapped_key = NULL, note_ciphertext = NULL WHERE id = :id"
            ),
            {"id": request_id, "note": note},
        )
    return len(rows)


def upgrade() -> None:
    op.add_column("time_off_requests", sa.Column("note_key_id", sa.Text(), nullable=True))
    op.add_column(
        "time_off_requests", sa.Column("note_wrapped_key", sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        "time_off_requests", sa.Column("note_ciphertext", sa.LargeBinary(), nullable=True)
    )
    op.drop_constraint(op.f(STATUS_CHECK_NAME), "time_off_requests", type_="check")
    op.drop_constraint(op.f(OLD_NOTE_CHECK_NAME), "time_off_requests", type_="check")
    # The old trigger refuses an update that leaves the status as it was, so it is out of the way
    # while the data step rewrites decided rows. The new one is created right after.
    op.execute(f"DROP TRIGGER {TRIGGER} ON time_off_requests")
    op.execute("ALTER TABLE time_off_requests NO FORCE ROW LEVEL SECURITY")
    seal_existing_notes(op.get_bind(), settings_key_loader)
    op.execute("ALTER TABLE time_off_requests FORCE ROW LEVEL SECURITY")
    op.drop_column("time_off_requests", "decision_note")
    op.create_check_constraint(op.f(STATUS_CHECK_NAME), "time_off_requests", NEW_STATUS_CHECK)
    op.create_check_constraint(op.f(NEW_NOTE_CHECK_NAME), "time_off_requests", NEW_NOTE_CHECK)
    op.execute(trigger_function(NEW_DECISION_COLUMNS))
    op.execute(CREATE_TRIGGER)
    # Dropping decision_note took its column grant with it; the new columns get theirs. The grant
    # list is per column, so the others are unchanged.
    op.execute(
        "GRANT UPDATE (note_key_id, note_wrapped_key, note_ciphertext)"
        " ON time_off_requests TO od_app"
    )


def downgrade() -> None:
    op.add_column("time_off_requests", sa.Column("decision_note", sa.Text(), nullable=True))
    op.drop_constraint(op.f(STATUS_CHECK_NAME), "time_off_requests", type_="check")
    op.drop_constraint(op.f(NEW_NOTE_CHECK_NAME), "time_off_requests", type_="check")
    op.execute(f"DROP TRIGGER {TRIGGER} ON time_off_requests")
    op.execute("ALTER TABLE time_off_requests NO FORCE ROW LEVEL SECURITY")
    open_sealed_notes(op.get_bind(), settings_key_loader)
    op.execute("ALTER TABLE time_off_requests FORCE ROW LEVEL SECURITY")
    op.drop_column("time_off_requests", "note_key_id")
    op.drop_column("time_off_requests", "note_wrapped_key")
    op.drop_column("time_off_requests", "note_ciphertext")
    op.create_check_constraint(op.f(STATUS_CHECK_NAME), "time_off_requests", OLD_STATUS_CHECK)
    op.create_check_constraint(op.f(OLD_NOTE_CHECK_NAME), "time_off_requests", OLD_NOTE_CHECK)
    op.execute(trigger_function(OLD_DECISION_COLUMNS))
    op.execute(CREATE_TRIGGER)
    op.execute("GRANT UPDATE (decision_note) ON time_off_requests TO od_app")
