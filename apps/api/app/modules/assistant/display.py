"""A stored turn as the page shows it again after a reload.

The fixed texts come from `fixed_texts` at the time of the request, never from the database: they
are written by a person, and nothing generated or stored can change what a person is told.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

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
    sensitive escalation, as its stream did: sensitive topics go to a person (invariant 6)."""
    if status == "crisis":
        return "crisis"
    if status == "guard_unavailable":
        return "unavailable"
    if status not in ("completed", "failed"):
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


def needs_hr_contact(turns: Sequence[AiTurn], now: datetime) -> bool:
    """Whether any turn shows an escalation, by the same endings `turn_out` shows."""
    return any(escalation_kind(*ending(t, now), t.guard_verdict) for t in turns)


def turn_out(
    turn: AiTurn, feedback: AiFeedback | None, hr_contact: Sequence[HrContact], now: datetime
) -> TurnOut:
    status, error_code = ending(turn, now)
    kind = escalation_kind(status, error_code, turn.guard_verdict)
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
            hr_contact=[HrContactOut(name=c.name, work_email=c.work_email) for c in hr_contact],
        ),
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
        sections=[
            SectionOut(section_id=s["sectionId"], passage_ids=s["passageIds"])
            for s in turn.sections_retrieved
        ],
        feedback=None
        if feedback is None
        else FeedbackOut(helpful=feedback.helpful, reason=feedback.reason),
        started_at=turn.started_at,
        ended_at=turn.ended_at,
    )
