"""What the time-off tools tell the model, shaped.

Every figure is the product's one label ("8 hours (1 day)"), never a number of minutes, so the
model has nothing to calculate with (invariant 2). Dates are ISO strings. The only IDs are request
IDs: no proposal, person, conversation, or turn ID, and no text a person wrote (a denial's note,
a coverage list). Rules are a handbook section and its title, for the model to cite.
"""

from collections.abc import Iterable, Sequence
from typing import Any

from app.ai.proposal_cards import CancelCard, DecideCard, RequestCard
from app.domain.timeoff.evaluate import SHORT_NOTICE_DAYS, SHORT_NOTICE_MIN_DAYS
from app.domain.timeoff.labels import label
from app.modules.timeoff.queries import RequestRow
from app.modules.timeoff.schemas import DrawOut, RuleRefOut, SkippedDay
from app.modules.timeoff.service import Balances, Preview, RuleRef
from app.modules.timeoff.texts import refusal_text

CONFIRM_REQUEST = "A confirm card is shown to the person. Nothing is booked until they confirm."
CONFIRM_DECISION = "A confirm card is shown to the person. Nothing is decided until they confirm."
CONFIRM_CANCEL = "A confirm card is shown to the person. Nothing is canceled until they confirm."

# Added to a proposal tool's note when its card replaced a pending one.
REPLACES_CARD = "This replaces the earlier card, which can no longer be confirmed."


def with_replacement(result: dict[str, Any], replaced: bool) -> dict[str, Any]:
    """The tool's result, its note extended when the new card replaced a pending one."""
    if replaced:
        result["note"] = f"{result['note']} {REPLACES_CARD}"
    return result


# A warning never refuses. The engine gives a code; this is its sentence for the model.
WARNING_TEXTS = {
    "short-notice": (
        f"This is more than {SHORT_NOTICE_MIN_DAYS} days of PTO and it starts less than "
        f"{SHORT_NOTICE_DAYS} days from today. The handbook asks for two weeks' notice where "
        "possible."
    ),
}


def rules_out(rules: Iterable[RuleRef | RuleRefOut]) -> list[dict[str, str]]:
    return [{"sectionId": rule.section_id, "title": rule.title} for rule in rules]


def balance_result(name: str, balances: Balances) -> dict[str, Any]:
    pto = balances.pto
    return {
        "person": name,
        "asOf": balances.today.isoformat(),
        "pto": {
            "earned": label(pto.earned_minutes),
            "taken": label(pto.taken_minutes),
            "booked": label(pto.booked_minutes),
            "pending": label(pto.pending_minutes),
            "available": label(pto.available_minutes),
            "ceiling": label(pto.ceiling_minutes),
            "nextEarning": {
                "date": None if pto.next_earning is None else pto.next_earning.isoformat(),
                "amount": label(pto.next_earning_minutes),
            },
        },
        "sick": [
            {
                "year": year.year,
                "granted": label(year.granted_minutes),
                "used": label(year.used_minutes),
                "booked": label(year.booked_minutes),
                "available": label(year.available_minutes),
            }
            for year in balances.sick
        ],
        "rules": rules_out(balances.rules),
    }


def request_row(row: RequestRow) -> dict[str, Any]:
    """One request of the list: no note, and nothing that says who may see more of it."""
    return {
        "id": str(row.id),
        "person": row.person_name,
        "type": row.type,
        "startDate": row.start_date.isoformat(),
        "endDate": row.end_date.isoformat(),
        "amount": label(row.amount_minutes),
        "status": row.status,
        "decidedBy": row.decided_by_name,
    }


def _draw(draw: DrawOut) -> dict[str, Any]:
    return {
        "year": draw.year,
        "amount": draw.amount_label,
        "availableBefore": draw.available_before_label,
        "availableAfter": draw.available_after_label,
    }


def _skipped(items: Sequence[SkippedDay]) -> list[dict[str, str]]:
    return [{"date": item.day.isoformat(), "reason": item.reason} for item in items]


def _warnings(codes: Iterable[str]) -> list[dict[str, str]]:
    return [{"code": code, "text": WARNING_TEXTS.get(code, "")} for code in codes]


def problem_sentences(preview: Preview) -> str:
    """The engine's refusal as plain sentences, from the fixed texts. For an overlap, the days
    that clash follow."""
    sentences = [refusal_text(code) for code in preview.problems]
    if "overlaps" in preview.problems and preview.overlapping:
        days = ", ".join(day.isoformat() for day in preview.overlapping)
        sentences.append(f"Days already covered: {days}.")
    return " ".join(sentences)


def check_result(preview: Preview) -> dict[str, Any]:
    """The engine's answer to "would this request work", whether or not it would."""
    evaluation = preview.evaluation
    amount = evaluation.amount_minutes
    return {
        "ok": preview.ok,
        "problems": [{"code": code, "text": refusal_text(code)} for code in preview.problems],
        "warnings": _warnings(evaluation.warnings),
        "countedDays": [day.isoformat() for day in evaluation.counted],
        "skippedDays": _skipped(
            [SkippedDay(day=item.day, reason=item.reason) for item in evaluation.skipped]
        ),
        "overlappingDays": [day.isoformat() for day in preview.overlapping],
        "amount": None if amount is None else label(amount),
        "draws": [_draw(DrawOut.of(draw)) for draw in evaluation.draws],
        "rules": rules_out(preview.rules),
    }


def request_card_result(card: RequestCard) -> dict[str, Any]:
    """The same answer, for a request that can be made, from the card that was stored."""
    return {
        "ok": True,
        "problems": [],
        "warnings": _warnings(card.warnings),
        "countedDays": [day.isoformat() for day in card.counted_days],
        "skippedDays": _skipped(card.skipped_days),
        "overlappingDays": [],
        "amount": card.amount_label,
        "draws": [_draw(draw) for draw in card.draws],
        "rules": rules_out(card.rules),
        "note": CONFIRM_REQUEST,
    }


def decide_card_result(request_id: str, card: DecideCard) -> dict[str, Any]:
    """The decision card's summary. Never the team coverage, which only the card and the page show
    to the manager (invariant 5), and never the requester's ID."""
    return {
        "requestId": request_id,
        "person": card.requester.name,
        "title": card.requester.title,
        "type": card.type,
        "startDate": card.start_date.isoformat(),
        "endDate": card.end_date.isoformat(),
        "amount": card.amount_label,
        "decision": card.decision,
        "rules": rules_out(card.rules),
        "note": CONFIRM_DECISION,
    }


def cancel_card_result(request_id: str, card: CancelCard) -> dict[str, Any]:
    return {
        "requestId": request_id,
        "type": card.type,
        "startDate": card.start_date.isoformat(),
        "endDate": card.end_date.isoformat(),
        "status": card.status,
        "amount": card.amount_label,
        "returns": card.returns_label,
        "availableAfter": card.available_after_label,
        "rules": rules_out(card.rules),
        "note": CONFIRM_CANCEL,
    }
