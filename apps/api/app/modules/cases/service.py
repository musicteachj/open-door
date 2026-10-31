"""The case service: the only writer of cases, and the only reader of their words and summaries.

A case is a matter a person sends to HR in their own words. The words are sealed with the case's
own data key before they are stored, and opened only here, after the policy layer agrees, with the
read recorded in the same transaction (a `case_events` row and an audit event).

A refusal is a `ProblemError`. A case the actor cannot see, one that does not exist, and one that
belongs to someone else all raise the one `case-not-found` problem, which the routes answer with a
404, so no probe learns that a case exists. The words and the person's name are never in a problem,
a log line, or an audit event. Background work logs error names only.

Every function takes a session that `tenant_session` scoped to the actor (and, for HR, with the HR
flag set from the actor, as the session dependency does).
"""

import logging
from datetime import date, datetime, timedelta
from typing import Final, Literal, NamedTuple, Protocol
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.ai.case_summary import SUMMARY_TIMEOUT_SECONDS
from app.ai.fixed_texts import CRISIS_TEXT
from app.ai.guard import CaseGuard, GuardOutcome, screen_text
from app.ai.personal_data import kind_of_personal_data
from app.ai.text import error_name
from app.ai.transport import GUARD_TIMEOUT_SECONDS
from app.core.encryption import (
    DataKey,
    KeyProvider,
    Place,
    new_data_key,
    open_,
    seal,
    wrap_aad,
)
from app.core.problems import ProblemError
from app.db.errors import constraint_name, has_sqlstate
from app.db.locks import database_now
from app.db.models import Case, CaseSummary
from app.db.tenancy import TenantContext, tenant_session
from app.modules.audit.service import AuditAction, record_event
from app.modules.cases import queries, texts
from app.modules.cases.schemas import (
    CATEGORIES,
    CaseDetail,
    CaseOpened,
    CaseStatusView,
    Counts,
    OpenCase,
    QueueItem,
    QueuePage,
    SummaryFailed,
    SummaryRead,
    SummaryResult,
    SummaryRetry,
    SummaryState,
    SummaryWritten,
    TimelineEntry,
)
from app.policy import Action, Actor, CaseResource, PersonResource, can

logger = logging.getLogger(__name__)

CASES_TABLE: Final = "cases"
SUMMARIES_TABLE: Final = "case_summaries"
WORDS_COLUMN: Final = "text_ciphertext"
SUMMARY_COLUMN: Final = "ciphertext"

# The trigger's code for a status move it refuses (migration 0013).
STATUS_REFUSED_SQLSTATE: Final = "OD004"
ONE_SUMMARY_CONSTRAINT: Final = "uq_case_summaries_one_not_by_hr_per_case"
# The summary and event triggers' code for a write the person may not make (migration 0013).
TRIGGER_REFUSED_SQLSTATE: Final = "OD003"
SCREENING_REFUSED_SQLSTATE: Final = "OD005"
TURN_CONSTRAINTS: Final = frozenset({"fk_cases_turn_owner", "fk_cases_conversation_owner"})

NOT_FOUND_CODE: Final = "case-not-found"
TURN_NOT_FOUND_CODE: Final = "case-turn-not-found"
# A case with no summary at all can be retried once it is this old (the first one is the person's
# background task, which takes at most 30 seconds).
RETRY_AFTER: Final = timedelta(minutes=2)
# A retry's job is "in flight" this long after HR asks for it, unless it has recorded a summary
# by then. Its slowest honest run is the screening (the guard's 10 s limit) then the summary call
# (30 s), about 40 s; the extra 20 s is for queuing, the budget's reserve and settle, and the
# write. A crashed or canceled job therefore blocks HR's next try for at most a minute.
IN_FLIGHT_WINDOW: Final = timedelta(seconds=SUMMARY_TIMEOUT_SECONDS + GUARD_TIMEOUT_SECONDS + 20)


def _not_found() -> ProblemError:
    return ProblemError(404, NOT_FOUND_CODE, texts.NOT_FOUND_TEXT)


def _turn_not_found() -> ProblemError:
    # One problem for a turn that does not exist, one that is someone else's, and one that was
    # not flagged: a probe cannot tell them apart.
    return ProblemError(404, TURN_NOT_FOUND_CODE, texts.TURN_NOT_FOUND_TEXT)


def _words_place(tenant_id: UUID, case_id: UUID) -> Place:
    return Place(CASES_TABLE, WORDS_COLUMN, tenant_id, case_id)


class SealedWords(NamedTuple):
    """A new case's words sealed under a fresh data key, and the key wrapped for storage."""

    data_key: DataKey
    key_id: str
    wrapped_key: bytes
    text_ciphertext: bytes


def seal_case_words(keys: KeyProvider, tenant_id: UUID, case_id: UUID, words: str) -> SealedWords:
    """Make the case's data key, wrap it, and seal the words with it. The one place a case's key
    and words are sealed, for a case sent by a person and for a seeded one."""
    data_key = new_data_key()
    key_id, wrapped_key = keys.wrap(data_key, aad=wrap_aad(tenant_id, CASES_TABLE, case_id))
    return SealedWords(
        data_key,
        key_id,
        wrapped_key,
        seal(data_key, words.encode(), place=_words_place(tenant_id, case_id)),
    )


def seal_summary_text(data_key: DataKey, tenant_id: UUID, summary_id: UUID, text: str) -> bytes:
    """A summary's text sealed with its case's data key."""
    place = Place(SUMMARIES_TABLE, SUMMARY_COLUMN, tenant_id, summary_id)
    return seal(data_key, text.encode(), place=place)


def _case_key(keys: KeyProvider, case: Case) -> DataKey:
    """The case's data key, unwrapped. Raises `DecryptionFailed` if it does not open."""
    aad = wrap_aad(case.tenant_id, CASES_TABLE, case.id)
    return DataKey(keys.unwrap(case.key_id, case.wrapped_key, aad=aad))


def _open_words(keys: KeyProvider, case: Case) -> str:
    """The case's words, opened. The one place they are decrypted; callers check the policy."""
    place = _words_place(case.tenant_id, case.id)
    return open_(_case_key(keys, case), case.text_ciphertext, place=place).decode()


def _resource(case: Case, *, words_read: bool = False) -> CaseResource:
    return CaseResource(case.person_id, case.status, words_read)


class _StatusColumns(Protocol):
    """What the person's status view reads: a `Case`, or a row of just these columns."""

    @property
    def id(self) -> UUID: ...
    @property
    def category(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def created_at(self) -> datetime: ...
    @property
    def reply_by(self) -> date: ...
    @property
    def status_changed_at(self) -> datetime: ...


def _status_view(case: _StatusColumns) -> CaseStatusView:
    return CaseStatusView(
        id=case.id,
        category=case.category,
        status=case.status,
        sent_at=case.created_at,
        reply_by=case.reply_by,
        status_changed_at=case.status_changed_at,
    )


def _own_case() -> ProblemError:
    # HR knows their own case exists, so this is a 403, not the shared not-found.
    return ProblemError(403, "case-own", texts.OWN_CASE_TEXT)


def _require_hr_queue(actor: Actor) -> None:
    if not can(actor, Action.CASE_LIST, PersonResource(actor.person_id)):
        raise _not_found()


# --- opening a case ---


async def open_case(
    engine: AsyncEngine, keys: KeyProvider, guard: CaseGuard, actor: Actor, new: OpenCase
) -> CaseOpened:
    """Open the actor's own case.

    Call it with no session open (a route built on `signed_in_caller`): it opens its own short
    ones, and holds none while the model is waited on.

    In order: the policy; the words checked (empty, too long, a Social Security or card number),
    before anything is screened, stored, or sent; then, in a read-only session, the same submission
    (or turn), the turn, and the waiting limit, so a refused request is never screened; then the
    words are screened with no session, connection, or lock held; then, in a second session under
    the person's lock, the same three checks again and the insert. The case, its `opened` event,
    and `case.opened` commit together when that session ends. No HR flag is needed: a person reads
    and adds their own cases and turns without it, HR included.

    A double click can screen twice, since both sends pass the first look before either has
    written; the lock then makes the second return the first's case, and only the spend is doubled.
    """
    if not can(actor, Action.CASE_OPEN, PersonResource(actor.person_id)):
        raise _not_found()
    if new.category not in CATEGORIES:
        raise ProblemError(422, "case-invalid", texts.INVALID_CATEGORY_TEXT)
    if not new.text.strip():
        raise ProblemError(422, "case-empty-words", texts.EMPTY_WORDS_TEXT)
    if len(new.text) > texts.MAX_WORDS_CHARACTERS:
        raise ProblemError(422, "case-words-too-long", texts.TOO_LONG_TEXT)
    if kind_of_personal_data(new.text) is not None:
        # The kind is not named: the text is not echoed or classified in the problem.
        raise ProblemError(422, "case-personal-data", texts.PERSONAL_DATA_TEXT)

    context = TenantContext(actor.tenant_id, actor.person_id)
    # The read-only look. No lock: it only decides whether to spend on the screening.
    async with tenant_session(engine, context) as db:
        repeated, _ = await _look(db, keys, actor, new)
    if repeated is not None:
        return repeated
    screening = await _screen(guard, actor, new.text)
    async with tenant_session(engine, context) as db:
        return await _insert_case(db, keys, actor, new, screening)


async def _insert_case(
    db: AsyncSession, keys: KeyProvider, actor: Actor, new: OpenCase, screening: str
) -> CaseOpened:
    """The second session of `open_case`: under the person's lock, look again (another send may
    have won while the words were screened), then write the case, its event, and its audit row."""
    tenant_id = actor.tenant_id
    await queries.lock_person(db, tenant_id, actor.person_id)
    repeated, conversation_id = await _look(db, keys, actor, new)
    if repeated is not None:
        return repeated

    # The database stamps `created_at` with the transaction's `now()`, so the reply-by date is
    # worked out from that same instant.
    sent_at = await database_now(db)
    reply_by = await queries.reply_by_at(db, tenant_id, sent_at)

    # Made here, since the words' place includes the row's ID.
    case_id = uuid4()
    sealed = seal_case_words(keys, tenant_id, case_id, new.text)
    row = Case(
        id=case_id,
        tenant_id=tenant_id,
        person_id=actor.person_id,
        submission_id=new.submission_id,
        category=new.category,
        reply_by=reply_by,
        screening=screening,
        conversation_id=conversation_id,
        turn_id=new.turn_id,
        key_id=sealed.key_id,
        wrapped_key=sealed.wrapped_key,
        text_ciphertext=sealed.text_ciphertext,
    )
    db.add(row)
    try:
        # The person may read their own case back, so the insert can return the stamped times.
        await db.flush()
    except IntegrityError as error:
        # The lock makes a clash impossible here. A foreign key on the turn is the same problem
        # as an unknown turn; anything else is a bug and is raised as it is.
        if constraint_name(error) in TURN_CONSTRAINTS:
            raise _turn_not_found() from None
        raise
    await queries.add_event(
        db,
        tenant_id=tenant_id,
        case_id=case_id,
        actor_id=actor.person_id,
        kind="opened",
        event_id=uuid4(),
    )
    await record_event(
        db,
        tenant_id=tenant_id,
        actor_id=actor.person_id,
        action="case.opened",
        target_type="case",
        target_id=case_id,
        after={"screening": screening, "category": new.category},
        via="ui",
    )
    # No call is made for these two, so HR's detail shows "No AI summary" at once, with the reason.
    # Written in this transaction, so the case never exists without it.
    crisis = screening == "crisis"
    if crisis or screening == "unscreened":
        await record_summary(db, keys, case_id, SummaryFailed("crisis" if crisis else "unscreened"))
    return CaseOpened(
        case=_status_view(row),
        created=True,
        screening=screening,
        crisis_text=CRISIS_TEXT if crisis else None,
        summary_due=screening in {"ordinary", "sensitive"},
    )


async def _look(
    db: AsyncSession, keys: KeyProvider, actor: Actor, new: OpenCase
) -> tuple[CaseOpened | None, UUID | None]:
    """The case this send repeats, if any; otherwise the checks that refuse it (an unknown, foreign,
    or unflagged turn; the waiting limit) and the turn's conversation. Reads only."""
    tenant_id = actor.tenant_id
    earlier = await queries.case_by_submission(db, tenant_id, actor.person_id, new.submission_id)
    if earlier is None and new.turn_id is not None:
        earlier = await queries.case_by_turn(db, tenant_id, actor.person_id, new.turn_id)
    if earlier is not None:
        return _repeat(keys, earlier, new), None
    conversation_id: UUID | None = None
    if new.turn_id is not None:
        conversation_id = await queries.own_flagged_turn_conversation(
            db, tenant_id, actor.person_id, new.turn_id
        )
        if conversation_id is None:
            raise _turn_not_found()
    if await queries.count_waiting(db, tenant_id, actor.person_id) >= texts.MAX_WAITING_CASES:
        raise ProblemError(409, "case-waiting-limit", texts.WAITING_LIMIT_TEXT)
    return None, conversation_id


def _repeat(keys: KeyProvider, earlier: Case, new: OpenCase) -> CaseOpened:
    """The case a repeated submission (or a second tab for the same turn) already made. The same
    words get the same case and schedule nothing; different words are a conflict, which the person
    sees as "already sent", not as anyone's words."""
    words = _open_words(keys, earlier)
    # The same send names the same turn (or none), as well as the same words.
    if words != new.text or earlier.turn_id != new.turn_id:
        raise ProblemError(409, "case-submission-conflict", texts.SUBMISSION_CONFLICT_TEXT)
    return CaseOpened(
        case=_status_view(earlier),
        created=False,
        screening=earlier.screening,
        crisis_text=CRISIS_TEXT if earlier.screening == "crisis" else None,
        summary_due=False,
    )


async def _screen(guard: CaseGuard, actor: Actor, words: str) -> str:
    """The guard's label for the words, or `unscreened` when it could not give one. The case is
    saved either way."""
    ctx = TenantContext(actor.tenant_id, actor.person_id)
    try:
        outcome = await screen_text(guard, ctx, words)
    except Exception as error:
        logger.error("Screening a case failed (%s)", error_name(error))
        return "unscreened"
    if outcome is None:
        return "unscreened"
    return screening_label(outcome)


def screening_label(outcome: GuardOutcome) -> str:
    """The case's label for a guard outcome that screened the words: crisis, sensitive, or
    ordinary."""
    if outcome.route == "crisis":
        return "crisis"
    return "sensitive" if outcome.category == "sensitive" else "ordinary"


# --- the person's view and HR's queue ---


async def my_cases(
    db: AsyncSession, actor: Actor, *, limit: int | None = None
) -> list[CaseStatusView]:
    """The actor's own cases, newest first, at most `limit` of them when given. HR's session could
    read every case, so the filter is the actor's ID, not the database's rule. Only the columns of
    the view are read: the encrypted words and their key never leave the database here."""
    query = (
        select(
            Case.id,
            Case.category,
            Case.status,
            Case.created_at,
            Case.reply_by,
            Case.status_changed_at,
        )
        .where(Case.tenant_id == actor.tenant_id, Case.person_id == actor.person_id)
        .order_by(Case.created_at.desc(), Case.id.desc())
    )
    if limit is not None:
        query = query.limit(limit)
    return [_status_view(row) for row in await db.execute(query)]


async def queue(
    db: AsyncSession, actor: Actor, status: str | None, cursor: str | None
) -> QueuePage:
    """HR's queue, one page. No text. A non-HR actor is refused as for a case that is not there."""
    _require_hr_queue(actor)
    if status is not None and status not in {"open", "new", "in_review", "closed"}:
        raise ProblemError(422, "case-invalid", texts.INVALID_FILTER_TEXT)
    try:
        position = None if cursor is None else queries.decode_cursor(cursor)
    except ValueError:
        raise ProblemError(422, "case-invalid-cursor", texts.INVALID_CURSOR_TEXT) from None
    rows = await queries.queue_rows(db, actor.tenant_id, status, position, queries.PAGE_SIZE)
    page = rows[: queries.PAGE_SIZE]
    items = tuple(
        QueueItem(
            id=row.id,
            category=row.category,
            person_id=row.person_id,
            given_name=row.given_name,
            family_name=row.family_name,
            title=row.title,
            location_name=row.location_name,
            sent_at=row.created_at,
            reply_by=row.reply_by,
            status=row.status,
            status_changed_at=row.status_changed_at,
            # HR's own case hides the verdict, as the opener's view does.
            crisis=None if row.person_id == actor.person_id else (row.screening == "crisis"),
            is_own=row.person_id == actor.person_id,
        )
        for row in page
    )
    more = len(rows) > queries.PAGE_SIZE
    return QueuePage(items, queries.encode_cursor(page[-1]) if more else None)


async def counts(db: AsyncSession, actor: Actor) -> Counts:
    """New cases, and how many are due today or late (by Denver's calendar).

    HR's own cases are left out, though the queue lists them: HR can't act on their own case, so
    it isn't new for them."""
    _require_hr_queue(actor)
    new, due = await queries.counts(db, actor.tenant_id, actor.person_id)
    return Counts(new=new, reply_due=due)


async def case_detail(db: AsyncSession, actor: Actor, case_id: UUID) -> CaseDetail:
    """The metadata HR's detail page shows. No text, and not an audited read. For HR's own case it
    stops at the header: no person card, summary, or timeline."""
    _require_hr_queue(actor)
    row = await queries.load_case(db, actor.tenant_id, case_id)
    if row is None or not can(actor, Action.CASE_READ_STATUS, _resource(row)):
        raise _not_found()
    own = row.person_id == actor.person_id
    card = None
    summary = None
    entries = None
    if not own:
        card = await queries.person_card(db, actor.tenant_id, row.person_id)
        latest = await queries.newest_summary(db, actor.tenant_id, row.id)
        summary = _summary_state(latest, crisis=row.screening == "crisis")
        entries = tuple(
            TimelineEntry(
                kind=event.kind,
                occurred_at=event.occurred_at,
                actor_person_id=event.actor_person_id,
                actor_given_name=event.given_name,
                actor_family_name=event.family_name,
                from_status=event.from_status,
                to_status=event.to_status,
            )
            for event in await queries.timeline(db, actor.tenant_id, row.id)
        )
    return CaseDetail(
        id=row.id,
        category=row.category,
        status=row.status,
        sent_at=row.created_at,
        reply_by=row.reply_by,
        status_changed_at=row.status_changed_at,
        screening=None if own else row.screening,
        is_own=own,
        person_id=row.person_id,
        given_name=card.given_name if card else None,
        family_name=card.family_name if card else None,
        title=card.title if card else None,
        department_name=card.department_name if card else None,
        location_name=card.location_name if card else None,
        work_email=card.work_email if card else None,
        summary=summary,
        timeline=entries,
    )


def _summary_outcome(
    latest: CaseSummary | None, *, crisis: bool
) -> tuple[Literal["none", "written", "failed"], str | None]:
    """What a case's newest summary row amounts to, and the reason when it failed. The one place
    that a crisis case never shows a written summary, whatever the newest row is: two retries that
    interleave can stamp a written row after the crisis one (`created_at` is the transaction's
    start)."""
    if latest is None:
        return "none", None
    if crisis:
        return "failed", "crisis"
    if latest.status == "failed" or latest.ciphertext is None:
        return "failed", latest.reason
    return "written", None


def _summary_state(latest: CaseSummary | None, *, crisis: bool = False) -> SummaryState:
    state, reason = _summary_outcome(latest, crisis=crisis)
    if state == "none":
        return SummaryState("none")
    assert latest is not None  # noqa: S101  # only "none" comes from no row
    return SummaryState(state, reason, latest.created_at)


# --- audited reads ---


async def _readable(db: AsyncSession, actor: Actor, case_id: UUID, action: Action) -> Case:
    """The case, if the actor may take `action` on it. A case HR opened is refused to that HR
    person with a problem of its own (they know it exists); every other refusal is not-found."""
    row = await queries.load_case(db, actor.tenant_id, case_id)
    if row is None:
        raise _not_found()
    if actor.is_hr_admin and row.person_id == actor.person_id:
        raise _own_case()
    if not can(actor, action, _resource(row)):
        raise _not_found()
    return row


async def _record_read(
    db: AsyncSession, actor: Actor, case: Case, *, event: str, action: AuditAction
) -> None:
    await queries.add_event(
        db,
        tenant_id=case.tenant_id,
        case_id=case.id,
        actor_id=actor.person_id,
        kind=event,
        event_id=uuid4(),
    )
    await record_event(
        db,
        tenant_id=case.tenant_id,
        actor_id=actor.person_id,
        action=action,
        target_type="case",
        target_id=case.id,
        via="ui",
    )


async def case_summary_for(
    db: AsyncSession, keys: KeyProvider, actor: Actor, case_id: UUID
) -> SummaryRead:
    """The newest summary, opened for HR. An audited read: the timeline's `viewed` and `case.viewed`
    are written in this transaction, whatever the summary's state."""
    case = await _readable(db, actor, case_id, Action.CASE_READ_SUMMARY)
    latest = await queries.newest_summary(db, case.tenant_id, case.id)
    state, reason = _summary_outcome(latest, crisis=case.screening == "crisis")
    if state == "none":
        read = SummaryRead("none")
    elif state == "failed":
        assert latest is not None  # noqa: S101  # only "none" comes from no row
        # A crisis case's row says nothing about the model: the summary was never opened.
        crisis = reason == "crisis"
        read = SummaryRead(
            "failed",
            reason=reason,
            model=None if crisis else latest.model,
            prompt_version=None if crisis else latest.prompt_version,
            created_at=latest.created_at,
        )
    else:
        # "written" means the row has its ciphertext (`_summary_outcome` checked).
        assert latest is not None  # noqa: S101
        assert latest.ciphertext is not None  # noqa: S101
        place = Place(SUMMARIES_TABLE, SUMMARY_COLUMN, case.tenant_id, latest.id)
        words = open_(_case_key(keys, case), latest.ciphertext, place=place).decode()
        read = SummaryRead(
            "written",
            text=words,
            model=latest.model,
            prompt_version=latest.prompt_version,
            created_at=latest.created_at,
        )
    await _record_read(db, actor, case, event="viewed", action="case.viewed")
    return read


async def case_text_for(db: AsyncSession, keys: KeyProvider, actor: Actor, case_id: UUID) -> str:
    """The person's words, opened for HR. An audited read: `text_read` and `case.text.read` are
    written in this transaction, and a later status change needs that `text_read`."""
    case = await _readable(db, actor, case_id, Action.CASE_READ_TEXT)
    words = _open_words(keys, case)
    await _record_read(db, actor, case, event="text_read", action="case.text.read")
    return words


# --- changing the status ---


async def change_status(db: AsyncSession, actor: Actor, case_id: UUID, to: str) -> CaseStatusView:
    """Move a case to `in_review` or `closed`. HR only, never their own case, and only after this
    actor has read the words (`words-not-read`). The database's trigger decides the move itself."""
    case = await queries.load_case(db, actor.tenant_id, case_id)
    if case is None:
        raise _not_found()
    if actor.is_hr_admin and case.person_id == actor.person_id:
        raise _own_case()
    read = await queries.words_read_by(db, case.tenant_id, case.id, actor.person_id)
    if not can(actor, Action.CASE_UPDATE_STATUS, _resource(case, words_read=read)):
        if can(actor, Action.CASE_UPDATE_STATUS, _resource(case, words_read=True)):
            raise ProblemError(409, "words-not-read", texts.WORDS_NOT_READ_TEXT)
        raise _not_found()
    # Locked, so the "from" status written below is the one the trigger judges.
    before = (
        await db.execute(
            select(Case.status)
            .where(Case.tenant_id == case.tenant_id, Case.id == case.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if before is None:
        raise _not_found()
    try:
        async with db.begin_nested():
            changed = await db.execute(
                update(Case)
                .where(Case.tenant_id == case.tenant_id, Case.id == case.id)
                .values(status=to)
            )
    except IntegrityError:
        # A status outside the three, which the column's check refuses.
        raise ProblemError(409, "case-status-refused", texts.STATUS_REFUSED_TEXT) from None
    except DBAPIError as error:
        if has_sqlstate(error, STATUS_REFUSED_SQLSTATE):
            raise ProblemError(409, "case-status-refused", texts.STATUS_REFUSED_TEXT) from None
        raise
    # Row-level security can filter the row out of an update without an error. Nothing happened,
    # so nothing is recorded.
    if changed.rowcount != 1:  # type: ignore[attr-defined]
        raise _not_found()
    await queries.add_event(
        db,
        tenant_id=case.tenant_id,
        case_id=case.id,
        actor_id=actor.person_id,
        kind="status_changed",
        from_status=before,
        to_status=to,
        event_id=uuid4(),
    )
    await record_event(
        db,
        tenant_id=case.tenant_id,
        actor_id=actor.person_id,
        action="case.status_changed",
        target_type="case",
        target_id=case.id,
        before={"status": before},
        after={"status": to},
        via="ui",
    )
    await db.refresh(case)
    return _status_view(case)


# --- the summary ---


async def record_summary(
    db: AsyncSession,
    keys: KeyProvider,
    case_id: UUID,
    result: SummaryResult,
    *,
    actor: Actor | None = None,
) -> bool:
    """Record a summary, or the note that none could be written, with its timeline event and its
    audit event (`via` `assistant`).

    The session is scoped to the person who opened the case (the background task, no `actor`) or
    to HR (a retry, with the HR `actor`, who must be allowed to act on the case). A written summary
    for a case that holds a crisis is recorded as a failed one with the reason `crisis` instead.
    Returns False when nothing was recorded: the database allows the person's side one summary, in
    the case's first 10 minutes, so a second one (or a late one) is refused here as a value, and
    HR's retry is the way to add another.
    """
    # Row-level security limits this to the session's own sandbox, and to the case's opener or HR.
    case = await queries.load_case_by_id(db, case_id)
    if case is None:
        raise _not_found()
    actor_id = None if actor is None else actor.person_id
    if actor is not None:
        # A retry is HR's, and never on their own case. (The first summary, with no actor, is
        # written as the person who opened it, HR or not.) There is no action of its own for it:
        # the summary is HR's to read, so it is HR's to retry.
        if actor.is_hr_admin and actor.person_id == case.person_id:
            raise _own_case()
        if not can(actor, Action.CASE_READ_SUMMARY, _resource(case)):
            raise _not_found()
    if isinstance(result, SummaryWritten) and actor is not None:
        # HR's retry takes the case's row first, so the check below reads the label as it is once
        # a parallel retry's `record_screening` (which updates the same row) has committed. The
        # person's own first summary can't take it (row-level security lets only HR update a
        # case), and nothing can raise a crisis under it: a crisis comes only from a retry of an
        # unscreened case, which has no first summary job.
        case = await queries.lock_case(db, case.tenant_id, case.id)
    if isinstance(result, SummaryWritten) and case.screening == "crisis":
        # A crisis verdict gets no summary, whoever got there first (a second retry in flight can
        # have found the crisis before this one wrote). The text is dropped, never stored or
        # shown; the billed call is still recorded and audited, as a failed summary with the
        # reason `crisis`.
        result = SummaryFailed("crisis")
    summary_id = uuid4()
    values: dict[str, object] = {
        "id": summary_id,
        "tenant_id": case.tenant_id,
        "case_id": case.id,
    }
    action: AuditAction
    if isinstance(result, SummaryWritten):
        values |= {
            "status": "written",
            "ciphertext": seal_summary_text(
                _case_key(keys, case), case.tenant_id, summary_id, result.text
            ),
            "model": result.model,
            "prompt_version": result.prompt_version,
        }
        event, action, after = (
            "summary_written",
            "case.summary.written",
            {"model": result.model, "promptVersion": result.prompt_version},
        )
    else:
        values |= {"status": "failed", "reason": result.reason}
        event, action, after = (
            "summary_failed",
            "case.summary.failed",
            {"reason": result.reason},
        )
    try:
        # A savepoint, so a refused insert leaves the transaction usable.
        async with db.begin_nested():
            await db.execute(insert(CaseSummary).values(**values))
    except IntegrityError as error:
        if constraint_name(error) == ONE_SUMMARY_CONSTRAINT:
            return False
        raise
    except DBAPIError as error:
        if has_sqlstate(error, TRIGGER_REFUSED_SQLSTATE):
            return False
        raise
    await queries.add_event(
        db,
        tenant_id=case.tenant_id,
        case_id=case.id,
        actor_id=actor_id,
        kind=event,
        event_id=uuid4(),
    )
    await record_event(
        db,
        tenant_id=case.tenant_id,
        actor_id=actor_id,
        action=action,
        target_type="case",
        target_id=case.id,
        after=after,
        via="assistant",
    )
    return True


async def screening_of(db: AsyncSession, tenant_id: UUID, case_id: UUID) -> str | None:
    """The case's label as the session sees it now (HR's session sees every case in the sandbox).
    Like every case query it names the sandbox, on top of row-level security."""
    return await db.scalar(
        select(Case.screening).where(Case.tenant_id == tenant_id, Case.id == case_id)
    )


async def record_screening(db: AsyncSession, case_id: UUID, verdict: str, *, actor: Actor) -> bool:
    """Write the safety check's verdict, as HR (HR's retry screened the words): from `unscreened`
    to any verdict, or from `ordinary` or `sensitive` up to `crisis`, so the case's own label is
    the one place a crisis is kept. The database allows only those moves, with HR's flag set and
    not on HR's own case; a refusal (another retry got there first) returns False. The audit event
    holds the label only."""
    try:
        # A savepoint, so a refused update leaves the transaction usable for the summary.
        async with db.begin_nested():
            changed = await db.execute(
                update(Case)
                .where(
                    Case.tenant_id == actor.tenant_id,
                    Case.id == case_id,
                    Case.screening.in_(
                        ("unscreened", "ordinary", "sensitive")
                        if verdict == "crisis"
                        else ("unscreened",)
                    ),
                )
                .values(screening=verdict)
            )
    except DBAPIError as error:
        if has_sqlstate(error, SCREENING_REFUSED_SQLSTATE):
            return False
        raise
    if changed.rowcount != 1:  # type: ignore[attr-defined]
        return False
    await record_event(
        db,
        tenant_id=actor.tenant_id,
        actor_id=actor.person_id,
        action="case.screened",
        target_type="case",
        target_id=case_id,
        after={"screening": verdict},
        via="assistant",
    )
    return True


async def plan_summary_retry(
    db: AsyncSession, keys: KeyProvider, actor: Actor, case_id: UUID
) -> SummaryRetry:
    """HR's retry of the summary, checked: HR only, never their own case, and only when the newest
    summary failed (not for a crisis) or none exists 2 minutes after opening, and never on a closed
    case. Else a 409.

    The words are opened as a system read for the background task: no `text_read` and no
    `case.text.read`, since HR has not read them. The retry is audited as `case.summary.retried`
    here, and the job's summary event, with HR as the actor, records its result.
    """
    case = await _readable(db, actor, case_id, Action.CASE_READ_SUMMARY)
    # Take the case's row, then read: a second retry waits here until the first has recorded its
    # request, so one is in flight at a time. The row is read again under the lock, because the
    # screening and status read before it can be stale by the time the lock is held.
    case = await queries.lock_case(db, case.tenant_id, case.id)
    latest = await queries.newest_summary(db, case.tenant_id, case.id)
    asked_at = await queries.last_retry_at(db, case.tenant_id, case.id)
    # The database's clock, the one that stamped the case.
    now = await database_now(db)
    if (
        asked_at is not None
        and now - asked_at < IN_FLIGHT_WINDOW
        and (latest is None or latest.created_at < asked_at)
    ):
        raise ProblemError(409, "summary-retry-refused", texts.SUMMARY_RETRY_REFUSED_TEXT)
    if latest is None:
        allowed = now - case.created_at >= RETRY_AFTER
    else:
        allowed = latest.status == "failed" and latest.reason != "crisis"
    if case.screening == "crisis" or case.status == "closed" or not allowed:
        raise ProblemError(409, "summary-retry-refused", texts.SUMMARY_RETRY_REFUSED_TEXT)
    # Recorded here, in the request's own transaction: the background job can be canceled by a
    # shutdown before it records its summary event.
    await record_event(
        db,
        tenant_id=case.tenant_id,
        actor_id=actor.person_id,
        action="case.summary.retried",
        target_type="case",
        target_id=case.id,
        after={"screenFirst": case.screening == "unscreened"},
        via="ui",
    )
    return SummaryRetry(
        case_id=case.id,
        category=case.category,
        words=_open_words(keys, case),
        unscreened=case.screening == "unscreened",
    )


__all__ = [
    "SealedWords",
    "case_detail",
    "case_summary_for",
    "case_text_for",
    "change_status",
    "counts",
    "my_cases",
    "open_case",
    "plan_summary_retry",
    "queue",
    "record_screening",
    "record_summary",
    "screening_label",
    "seal_case_words",
    "seal_summary_text",
]
