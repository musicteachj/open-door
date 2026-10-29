"""Let HR's summary retry write a case's safety-check verdict back, once (Phase 6).

A case the safety check could not screen is saved as `unscreened`. HR's "Try again" on its summary
screens the words first (the screening runs on the retry's own request), and a crisis found then
must show in HR's queue like any other. Until now the app's login could change only a case's status
and its stamp, so the verdict lived on the summary row and the queue's crisis line stayed off.

This adds `screening` to the columns the app's login may update, behind a trigger of its own
(SQLSTATE OD005, a code that is neither OD003, the insert refusals, nor OD004, a refused status
move). A change to `screening` is allowed only when all of these hold:

  - the move is one of two: from `unscreened` to a real verdict (ordinary, sensitive, or crisis),
    or from `ordinary` or `sensitive` to `crisis`. Nothing else moves: a crisis stays a crisis, a
    case never goes from ordinary to sensitive or the other way, and it never goes back to
    `unscreened`. So `cases.screening` is the one place a crisis is kept, even when a later retry
    finds it after another label was written (the owner's call)
  - the HR flag is set, and the case is not the caller's own (the same rule as the restrictive
    update rule from 0013, which already hides any other case from an UPDATE; the trigger says it
    again so it holds if that rule changes)
  - nothing else on the row changes with it: the status and its stamp stay as they are (the grants
    keep every other column read-only)

The status trigger from 0013 now runs only when `screening` did not change, so a verdict change
neither trips its "new to new" refusal nor re-stamps `status_changed_at`. A statement that changes
the status together with the screening is refused by the new trigger.

A parallel retry whose screening disagrees with the verdict already written used to record nothing,
so that AI action went unaudited. It now records a failed summary with the reason
`screening-conflict`, so this also widens the reason check on case_summaries.

Like the other triggers it runs as the caller, its search_path is pinned, and EXECUTE is revoked
from PUBLIC.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCREENING_TRIGGER = (
    """
    CREATE FUNCTION app.enforce_case_screening() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = pg_catalog, pg_temp
    AS $$
    BEGIN
        IF NOT (
            (OLD.screening = 'unscreened' AND NEW.screening IN ('ordinary', 'sensitive', 'crisis'))
            OR (OLD.screening IN ('ordinary', 'sensitive') AND NEW.screening = 'crisis')
        ) THEN
            RAISE EXCEPTION 'that screening move is not allowed' USING ERRCODE = 'OD005';
        END IF;
        IF NOT app.current_is_hr()
            OR app.current_person_id() IS NULL
            OR OLD.person_id = app.current_person_id()
        THEN
            RAISE EXCEPTION 'only HR screens a case, and never their own' USING ERRCODE = 'OD005';
        END IF;
        IF NEW.status IS DISTINCT FROM OLD.status
            OR NEW.status_changed_at IS DISTINCT FROM OLD.status_changed_at
        THEN
            RAISE EXCEPTION 'nothing else changes with a case''s screening'
                USING ERRCODE = 'OD005';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    """
    CREATE TRIGGER enforce_case_screening BEFORE UPDATE ON cases
        FOR EACH ROW WHEN (OLD.screening IS DISTINCT FROM NEW.screening)
        EXECUTE FUNCTION app.enforce_case_screening()
    """,
    "REVOKE EXECUTE ON FUNCTION app.enforce_case_screening() FROM PUBLIC",
)

# The status trigger now skips a screening change.
STATUS_TRIGGER_WHEN = (
    "DROP TRIGGER enforce_case_status ON cases",
    """
    CREATE TRIGGER enforce_case_status BEFORE UPDATE ON cases
        FOR EACH ROW WHEN (OLD.screening IS NOT DISTINCT FROM NEW.screening)
        EXECUTE FUNCTION app.enforce_case_status()
    """,
)
STATUS_TRIGGER_ALWAYS = (
    "DROP TRIGGER enforce_case_status ON cases",
    """
    CREATE TRIGGER enforce_case_status BEFORE UPDATE ON cases
        FOR EACH ROW EXECUTE FUNCTION app.enforce_case_status()
    """,
)


REASON_CHECK = "ck_case_summaries_reason"
OLD_REASONS = "'transport', 'refusal', 'timeout', 'budget', 'checks', 'crisis', 'unscreened'"


def upgrade() -> None:
    op.execute(f"ALTER TABLE case_summaries DROP CONSTRAINT {REASON_CHECK}")
    op.execute(
        f"ALTER TABLE case_summaries ADD CONSTRAINT {REASON_CHECK} CHECK"
        f" (reason IS NULL OR reason IN ({OLD_REASONS}, 'screening-conflict'))"
    )
    for statement in (
        "GRANT UPDATE (screening) ON cases TO od_app",
        *STATUS_TRIGGER_WHEN,
        *SCREENING_TRIGGER,
    ):
        op.execute(statement)


def downgrade() -> None:
    # NOT VALID: the table is insert-only, so a `screening-conflict` row is kept as it was written;
    # the old list still refuses any new one.
    op.execute(f"ALTER TABLE case_summaries DROP CONSTRAINT {REASON_CHECK}")
    op.execute(
        f"ALTER TABLE case_summaries ADD CONSTRAINT {REASON_CHECK} CHECK"
        f" (reason IS NULL OR reason IN ({OLD_REASONS})) NOT VALID"
    )
    op.execute("DROP TRIGGER enforce_case_screening ON cases")
    op.execute("DROP FUNCTION app.enforce_case_screening()")
    for statement in STATUS_TRIGGER_ALWAYS:
        op.execute(statement)
    op.execute("REVOKE UPDATE (screening) ON cases FROM od_app")
