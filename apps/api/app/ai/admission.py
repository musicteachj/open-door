"""Whether a turn may start: the room it needs in the budget, and how long the history has grown.

Both are pure, so the stream route's refusal and the conversation route's banner use the same
numbers and cannot disagree.

**Room.** `budget_state` says a cap is reached only at zero, but `reserve` refuses any call bigger
than what is left (a reservation is the most the call could cost). So a sandbox with a few cents
left would show no banner and then fail on its first call. A turn needs room for the guard and for
one main-model call, each at its reservation; the loop's later calls reserve again, and a turn that
runs out then ends with a budget `error` event (spec, "Budgets").

**History.** The history is sent in full on every call, so a long conversation costs more each
time and eventually will not fit. A new conversation is offered past 60,000 tokens, and a turn is
refused past 80,000 (spec, "Budgets", the History row). The size is the estimate the budget uses
for a call's input (`estimate_request_tokens`: two bytes a token), which never undercounts. So the
offer comes earlier than a real token count would put it, and that is the safe side.
"""

import json
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from app.ai.budget import BudgetState
from app.ai.context import ActorView, turn_context
from app.ai.guard import (
    INJECTION_NOTE,
    PREVIOUS_ANSWER_MAX_CHARACTERS,
    SENSITIVE_NOTE,
    build_guard_request,
    guard_reservation_usd,
)
from app.ai.pricing import estimate_request_tokens, reservation_usd
from app.ai.tools.base import text_block
from app.ai.turn import MAX_TOKENS, first_call_input_tokens, model_request

HISTORY_OFFER_TOKENS = 60_000
HISTORY_REFUSE_TOKENS = 80_000

# A character that takes four bytes in UTF-8, the most one can. The estimate counts bytes, so a
# previous answer of these is the largest the guard's slot can hold.
WIDEST_CHARACTER = "\U0001f600"

# The shortest question a person can send, for the banner: it asks "is there room for any turn at
# all?" The 429 asks the same of the question actually sent.
SMALLEST_QUESTION = "x"


def history_tokens(history: Sequence[dict[str, Any]]) -> int:
    """The estimated input tokens the stored history takes on every call."""
    return estimate_request_tokens(json.dumps(list(history), ensure_ascii=False))


def room_needed_usd(
    *,
    model: str,
    guard_model: str,
    effort: str,
    history: Sequence[dict[str, Any]],
    question: str,
    actor_view: ActorView,
    handbook_label: str,
    now: datetime,
) -> Decimal:
    """The room a turn needs: the guard's reservation plus the first model call's.

    Both are built the way the loop builds them. The guard's is for the very request it would send,
    with its previous-answer slot filled to the full 1,000 characters it may take, each the widest
    in UTF-8 (the stream route has not read the last answer, and a wider one only raises the
    amount). The model call's is
    `first_call_input_tokens` of the request the loop would send: the stored history, the question,
    and the per-turn context. The context is not built until the guard has spoken, so it is built
    here with the real asker, handbook label, and date, and with both operator notes the guard can
    add (the sensitive one and the injection one), which is the most it can hold.
    """
    guard = guard_reservation_usd(
        build_guard_request(
            question, WIDEST_CHARACTER * PREVIOUS_ANSWER_MAX_CHARACTERS, guard_model
        )
    )
    context = turn_context(
        actor_view,
        now=now,
        handbook_label=handbook_label,
        operator_notes=(SENSITIVE_NOTE, INJECTION_NOTE),
    )
    request = model_request(
        model=model,
        effort=effort,
        messages=(
            *history,
            {"role": "user", "content": [text_block(question)]},
            {"role": "system", "content": [text_block(context)]},
        ),
    )
    call = reservation_usd(
        model, estimated_input_tokens=first_call_input_tokens(request), max_tokens=MAX_TOKENS
    )
    return guard + call


def short_scopes(state: BudgetState, needed_usd: Decimal) -> tuple[bool, bool]:
    """Whether the sandbox and the day each have less than `needed_usd` left, in that order. The
    banner shows these; `reserve` refuses when spent + amount is over the cap, so equal fits."""
    return state.sandbox_remaining_usd < needed_usd, state.daily_remaining_usd < needed_usd


def scope_without_room(
    state: BudgetState, needed_usd: Decimal
) -> Literal["sandbox", "daily"] | None:
    """Which cap refuses a turn needing `needed_usd`, or None. The sandbox is named first, as
    `reserve` does, so a visitor at their own cap is told so and not that the demo is full."""
    sandbox_short, daily_short = short_scopes(state, needed_usd)
    if sandbox_short:
        return "sandbox"
    if daily_short:
        return "daily"
    return None
