"""The context line for a case the person opened from this conversation (ADR 0013, ADR 0014).

A person opens a case with the HR panel's button, outside any turn, so the model learns of it the
way it learns what happened to a confirm card: one line in the next turn's per-turn context, made
from structured data only (the category and the reply-by date, worded by `case_opened_sentence`),
never from anything the person wrote. Each case is told once: the context message that carries
the line stores `case:<id>:new` in `ai_messages.reported_outcomes`, and a case already named by a
stored context of the conversation is left out. A turn that failed or ended in a crisis stored no
context, so the line is still news the next time.

A case opened from "My cases" has no conversation, and a case opened from another conversation
belongs to that one, so neither adds a line here.
"""

from uuid import UUID

from sqlalchemy import Text, any_, exists, func, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import case_opened_sentence
from app.ai.proposals import OUTCOME_PREFIX, join_outcome_sentences
from app.db.models import AiMessage, Case


def case_entry(case_id: UUID) -> str:
    """What a stored context records for a case it told the model about."""
    return f"case:{case_id}:new"


async def unreported_cases(
    db: AsyncSession, tenant_id: UUID, person_id: UUID, conversation_id: UUID
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The context sentences for the person's own cases opened from this conversation that no stored
    context has told yet (oldest first), and the entry to store for each. Filtered by the person,
    though HR's session could read more."""
    told = (
        exists()
        .where(
            AiMessage.conversation_id == conversation_id,
            AiMessage.role == "system",
            func.concat("case:", sql_cast(Case.id, Text), ":new")
            == any_(AiMessage.reported_outcomes),
        )
        .correlate(Case)
    )
    rows = (
        await db.execute(
            select(Case.id, Case.category, Case.reply_by)
            .where(
                Case.tenant_id == tenant_id,
                Case.person_id == person_id,
                Case.conversation_id == conversation_id,
                ~told,
            )
            .order_by(Case.created_at, Case.id)
        )
    ).all()
    sentences = tuple(case_opened_sentence(row.category, row.reply_by) for row in rows)
    return sentences, tuple(case_entry(row.id) for row in rows)


def with_case_sentences(outcomes: tuple[str, ...], sentences: tuple[str, ...]) -> tuple[str, ...]:
    """The one "Since the last message:" line: the cards' outcomes first, then the cases. `outcomes`
    is `unreported_outcomes`' own line (none, or one); with no sentences it is returned as it is."""
    if not sentences:
        return outcomes
    if outcomes:
        # The cards' sentences end the line so far, so the first case sentence starts a new one.
        first, *rest = sentences
        return (outcomes[0] + " " + join_outcome_sentences([first[0].upper() + first[1:], *rest]),)
    return (OUTCOME_PREFIX + join_outcome_sentences(sentences),)
