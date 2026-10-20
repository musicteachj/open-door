"""A stored turn as the page shows it again after a reload.

The fixed texts come from `fixed_texts` at the time of the request, never from the database: they
are written by a person, and nothing generated or stored can change what a person is told.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal, NamedTuple

from app.ai.conversations import is_abandoned
from app.ai.fixed_texts import (
    CRISIS_TEXT,
    ERROR_TEXTS,
    SENSITIVE_TEXT,
    UNAVAILABLE_TEXT,
    HrContact,
)
from app.db.models import AiFeedback, AiTurn
from app.modules.assistant.schemas import (
    CitationOut,
    EscalationOut,
    FeedbackOut,
    GuardOut,
    HrContactOut,
    SectionOut,
    ToolCallOut,
    TurnErrorOut,
    TurnOut,
)

EscalationKind = Literal["sensitive", "crisis", "unavailable"]
MAX_TOKENS_CODE = "max-tokens"
# The turn never read the message (the guard could not run), so the person was sent the text for
# "can't answer right now" after the error.
GUARD_ERROR_CODE = "guard-error"
# Set by `recover_abandoned` on a `running` turn whose task died.
ABANDONED_CODE = "abandoned"


def escalation_kind(
    status: str, error_code: str | None, guard_verdict: dict[str, Any] | None
) -> EscalationKind | None:
    """Which escalation the stream sent for this turn, if any. Mirrors the turn's own rule: crisis
    and an unavailable guard have their own statuses, an unscreened message got the "can't answer"
    text, and a sensitive message got the HR contact after its answer or its error. A budget stop
    before the guard ran has none (its error text already gives 911 and 988, and there is no
    verdict). A sensitive turn that hits the budget later, at the model call, does get the
    sensitive escalation, as its stream did, and so does one the person stopped or whose stream was
    cut: sensitive topics go to a person on every ending (invariant 6)."""
    if status == "crisis":
        return "crisis"
    if status == "guard_unavailable":
        return "unavailable"
    if status not in ("completed", "failed", "stopped"):
        return None
    if error_code == ABANDONED_CODE:
        # Its task died, so its stream sent nothing: no escalation, only the plain error.
        return None
    if error_code == GUARD_ERROR_CODE:
        return "unavailable"
    if guard_verdict is not None and (
        guard_verdict.get("category") == "sensitive" or guard_verdict.get("kind") is not None
    ):
        return "sensitive"
    return None


_ESCALATION_TEXTS: dict[EscalationKind, str] = {
    "crisis": CRISIS_TEXT,
    "unavailable": UNAVAILABLE_TEXT,
    "sensitive": SENSITIVE_TEXT,
}


def error_for(status: str, error_code: str | None) -> TurnErrorOut | None:
    """The `error` event a failed turn had. A code the person never sees by name (a prompt leak,
    an abandoned turn) was sent as the plain `internal` error, and shows as that."""
    if status != "failed":
        return None
    code = error_code if error_code in ERROR_TEXTS else "internal"
    return TurnErrorOut(code=str(code), message=ERROR_TEXTS[str(code)])


def ending(turn: AiTurn, now: datetime) -> tuple[str, str | None]:
    """The turn's status and error code as the page shows them. A `running` turn older than the
    abandoned limit has a dead task: the page shows it as failed (`abandoned`), as the next turn
    will record it, and not as "answering" for good. `now` is the database's clock, the one
    `recover_abandoned` and `has_running_turn` use, so the page and the POST agree. A read writes
    nothing."""
    if turn.status == "running" and is_abandoned(turn.started_at, now):
        return "failed", ABANDONED_CODE
    return turn.status, turn.error_code


def is_not_found(
    *,
    status: str,
    error_code: str | None,
    guard_verdict: dict[str, Any] | None,
    citations: Sequence[Any],
    tool_calls: Sequence[dict[str, Any]],
) -> bool:
    """Whether the turn searched the handbook and found nothing to cite, so the page offers the HR
    team (invariant 4). Decided from what the turn stored, never from the model's words: it
    completed whole (not stopped, failed, or cut off), cited nothing, has no escalation of its own,
    the guard judged it ordinary (a turn with no verdict was never screened), and a
    `search_handbook` call ran. A refusal that never searched, or an answer from the directory
    alone, is not a miss. An uncited answer after a search is shown as one too, which is
    harmless."""
    if status != "completed" or error_code == MAX_TOKENS_CODE or citations:
        return False
    if escalation_kind(status, error_code, guard_verdict) is not None:
        return False
    if guard_verdict is None or guard_verdict.get("category") != "ordinary":
        return False
    return any(call["name"] == "search_handbook" for call in tool_calls)


class Shown(NamedTuple):
    """What a turn shows as, worked out once per read: its ending, its escalation, and whether the
    page offers the HR team for a miss. `needs_hr_contact` and `turn_out` both use it."""

    status: str
    error_code: str | None
    kind: EscalationKind | None
    not_found: bool


def shown(turn: AiTurn, now: datetime) -> Shown:
    status, error_code = ending(turn, now)
    kind = escalation_kind(status, error_code, turn.guard_verdict)
    not_found = is_not_found(
        status=status,
        error_code=error_code,
        guard_verdict=turn.guard_verdict,
        citations=turn.citations,
        tool_calls=turn.tool_calls,
    )
    return Shown(status, error_code, kind, not_found)


def needs_hr_contact(turns: Sequence[Shown]) -> bool:
    """Whether any turn shows an escalation or a not-found card."""
    return any(t.kind is not None or t.not_found for t in turns)


def hr_contact_out(contacts: Sequence[HrContact]) -> list[HrContactOut]:
    """The contacts as the conversation read shows them, built from the event's own form
    (`HrContact.to_json`), so the two can't drift apart."""
    return [HrContactOut.model_validate(c.to_json()) for c in contacts]


def sections_out(
    sections: Sequence[Mapping[str, Any]],
    section_names: Mapping[str, tuple[str | None, str | None]],
) -> list[SectionOut]:
    """Each retrieved section once, in the order it was first retrieved, with its passage IDs
    merged (order kept, no repeats). The stored list has an entry for each search result, so a
    section two searches found appears twice there, and the page keys its list by section. Nothing
    stored changes. A section `section_names` doesn't hold has no title or group."""
    merged: dict[str, list[str]] = {}
    for section in sections:
        passages = merged.setdefault(section["sectionId"], [])
        passages.extend(p for p in section["passageIds"] if p not in passages)
    out: list[SectionOut] = []
    for section_id, passage_ids in merged.items():
        title, group_name = section_names.get(section_id, (None, None))
        out.append(
            SectionOut(
                section_id=section_id, passage_ids=passage_ids, title=title, group_name=group_name
            )
        )
    return out


def turn_out(
    turn: AiTurn,
    shows: Shown,
    feedback: AiFeedback | None,
    hr_contact: Sequence[HrContact],
    section_names: Mapping[str, tuple[str | None, str | None]],
) -> TurnOut:
    """`shows` is what `shown` worked out for the turn. `section_names` maps a section ID to its
    (title, group name), from the conversation's stored sources. A section it doesn't hold is shown
    without them."""
    status, error_code, kind = shows.status, shows.error_code, shows.kind
    verdict = turn.guard_verdict
    return TurnOut(
        id=turn.id,
        question=turn.question,
        status=status,
        answer_text=turn.answer_text,
        citations=[CitationOut.model_validate(c) for c in turn.citations],
        incomplete=status == "completed" and error_code == MAX_TOKENS_CODE,
        error=error_for(status, error_code),
        escalation=None
        if kind is None
        else EscalationOut(
            kind=kind,
            message=_ESCALATION_TEXTS[kind],
            hr_contact=hr_contact_out(hr_contact),
        ),
        not_found=shows.not_found,
        guard=None
        if verdict is None
        else GuardOut(category=verdict["category"], kind=verdict.get("kind")),
        tool_calls=[
            ToolCallOut(
                name=t["name"],
                input_summary=t["inputSummary"],
                ok=t["ok"],
                duration_ms=t["durationMs"],
            )
            for t in turn.tool_calls
        ],
        sections=sections_out(turn.sections_retrieved, section_names),
        feedback=None
        if feedback is None
        else FeedbackOut(helpful=feedback.helpful, reason=feedback.reason),
        started_at=turn.started_at,
        ended_at=turn.ended_at,
    )
