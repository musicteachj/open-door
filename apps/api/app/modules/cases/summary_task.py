"""The case summary, written in the background after the case commits (or after HR's retry).

The job is given the words in memory: they are never read from the database here. Nothing is held
while the model is waited on: the budget's reserve and settle each open and close a short session
of their own, and the summary is recorded in one more afterward. The task catches everything, since
a background task must never raise, and logs error names only, never an error's text or the words.
A shutdown can cancel it; HR's retry covers that.

Every failure is a `failed` summary row with its code: `transport`, `refusal`, `timeout`, `budget`,
or `checks`; HR's retry, which screens an unscreened case first, can also write `unscreened`,
`crisis`, or `screening-conflict` (its screening found another verdict than the one a parallel
retry already wrote). Only that retry changes the case: it writes the verdict to
`cases.screening`, once, in the same transaction as the summary row.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, replace
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.budget import BudgetExceeded, Reservation, reserve, settle
from app.ai.case_summary import (
    Summarizer,
    SummaryRefused,
    SummaryRequest,
    SummaryUnavailable,
    build_summary_request,
    summary_problem,
)
from app.ai.guard import CaseGuard, screen_text
from app.ai.pricing import (
    IterationUsage,
    Usage,
    estimate_request_tokens,
    is_priced,
    reservation_usd,
    turn_call_cost,
)
from app.ai.text import error_name
from app.ai.transport import SpendLimitReached
from app.core.encryption import KeyProvider
from app.db.tenancy import TenantContext, set_is_hr, tenant_session
from app.modules.cases import service
from app.modules.cases.schemas import SummaryFailed, SummaryResult, SummaryWritten
from app.policy import Actor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SummaryJob:
    """What the background task needs. `ctx` is the case's opener for the first summary, or HR for
    a retry (with `actor` set). With `screen_first`, the words are screened before any summary."""

    guard: CaseGuard
    keys: KeyProvider
    summarizer: Summarizer | None
    ctx: TenantContext
    case_id: UUID
    category: str
    words: str = field(repr=False)
    actor: Actor | None = None
    screen_first: bool = False


def summary_reservation_usd(request: SummaryRequest) -> Decimal:
    """What to reserve for one summary call: the whole request (the system prompt and the message)
    as input and a full `max_tokens`."""
    text = json.dumps(
        {"system": request.system, "messages": list(request.messages)}, ensure_ascii=False
    )
    return reservation_usd(
        request.model,
        estimated_input_tokens=estimate_request_tokens(text),
        max_tokens=request.max_tokens,
    )


async def _settle(
    job: SummaryJob,
    reservation: Reservation,
    request_model: str,
    served: str,
    usage: Usage | None,
) -> None:
    """Bring the ledgers to the real cost. With no usage the cost is unknown, so the reservation
    stays counted."""
    if usage is None:
        return
    # A served name with no pinned price is charged at the request's model, as the guard does.
    priced = served if is_priced(served) else request_model
    cost = turn_call_cost([IterationUsage(priced, usage)])
    try:
        await settle(job.guard.engine, job.ctx, reservation, actual_usd=cost)
    except Exception as error:
        logger.warning("Settling a summary failed (%s); keeping its reservation", error_name(error))


async def generate_summary(job: SummaryJob) -> SummaryResult:
    """One summary: reserve, call under the time limit, settle, check. Never raises except for a
    cancellation."""
    if job.summarizer is None:
        return SummaryFailed("transport")
    request = build_summary_request(job.category, job.words)
    try:
        reservation = await reserve(
            job.guard.engine,
            job.ctx,
            turn_id=None,
            amount_usd=summary_reservation_usd(request),
            caps=job.guard.caps,
            purpose="case_summary",
        )
    except BudgetExceeded:
        return SummaryFailed("budget")
    except Exception as error:
        logger.error("Reserving for a summary failed (%s)", error_name(error))
        return SummaryFailed("transport")
    try:
        async with asyncio.timeout(request.timeout_seconds):
            answer = await job.summarizer.summarize(request)
    except TimeoutError:
        # The cost is unknown, so the reservation stays counted.
        return SummaryFailed("timeout")
    except SummaryRefused as refused:
        await _settle(job, reservation, request.model, request.model, refused.usage)
        return SummaryFailed("refusal")
    except SummaryUnavailable as unavailable:
        await _settle(job, reservation, request.model, request.model, unavailable.usage)
        return SummaryFailed("transport")
    except SpendLimitReached:
        # The API refused the request, so nothing was billed.
        await _settle(job, reservation, request.model, request.model, Usage(0, 0, 0, 0))
        return SummaryFailed("transport")
    except Exception as error:
        logger.error("A summary call failed (%s)", error_name(error))
        return SummaryFailed("transport")
    await _settle(job, reservation, request.model, answer.model, answer.usage)
    # The checks run on every summary, whatever wrote it, before it is stored.
    if summary_problem(answer.text, job.words) is not None:
        return SummaryFailed("checks")
    return SummaryWritten(answer.text, answer.model, answer.prompt_version)


@dataclass(frozen=True)
class JobResult:
    """What a job found: the summary result, and the verdict if this job screened the words."""

    summary: SummaryResult
    screening: str | None = None


async def _result_of(job: SummaryJob) -> JobResult:
    verdict = None
    if job.screen_first:
        try:
            outcome = await screen_text(job.guard, job.ctx, job.words)
        except Exception as error:
            logger.error("Screening a case failed (%s)", error_name(error))
            outcome = None
        if outcome is None:
            return JobResult(SummaryFailed("unscreened"))
        verdict = service.screening_label(outcome)
        if verdict == "crisis":
            return JobResult(SummaryFailed("crisis"), verdict)
    return JobResult(await generate_summary(job), verdict)


async def _after_screening(db: AsyncSession, job: SummaryJob, found: JobResult) -> SummaryResult:
    """Write this job's verdict, and say what this job may record. A verdict that was already
    written (another retry screened first) is read back in the same transaction: a crisis there
    (or a crisis verdict of this job's own, which raises an ordinary or sensitive label) means this
    job records the `crisis` note and no summary; two different non-crisis verdicts mean
    this job records a `screening-conflict` note and no summary (the other job's verdict stands,
    and the AI action is still audited); the same verdict changes nothing."""
    if found.screening is None or job.actor is None:
        return found.summary
    if await service.record_screening(db, job.case_id, found.screening, actor=job.actor):
        return found.summary
    current = await service.screening_of(db, job.actor.tenant_id, job.case_id)
    if current == "crisis":
        return SummaryFailed("crisis")
    if found.screening == "crisis":
        # The write-back should have raised the label to crisis; it was refused (the HR flag gone,
        # say). The crisis is still the job's result: no summary, the crisis note.
        return SummaryFailed("crisis")
    if current in (None, "unscreened"):
        # Nothing screened the case (the HR flag was gone or the row hidden): not a conflict.
        return SummaryFailed("unscreened")
    if current != found.screening:
        logger.warning(
            "A retry found another verdict than the case's (case %s, %s)",
            job.case_id,
            "ScreeningConflict",
        )
        return SummaryFailed("screening-conflict")
    return found.summary


async def run_summary_job(job: SummaryJob) -> None:
    """The background task: write the summary (or the note that none could be written) and its
    events. Catches everything and logs the error's name only.

    A verdict found by a retry's screening is written back to the case in the same transaction as
    the summary row and its events, before them. One transaction keeps the timeline and the case
    in step (a queue that shows a crisis always has the `crisis` row beside it), and a refused
    write-back (another retry screened first) is a savepoint that costs the summary nothing."""
    try:
        found = await _result_of(job)
        async with tenant_session(job.guard.engine, job.ctx) as db:
            if job.actor is not None:
                # The tenant context, the HR flag included, resets with each transaction.
                await set_is_hr(db, job.actor.is_hr_admin)
                if found.screening is not None:
                    found = replace(found, summary=await _after_screening(db, job, found))
            recorded = await service.record_summary(
                db, job.keys, job.case_id, found.summary, actor=job.actor
            )
        if not recorded:
            logger.warning("A case summary was not recorded (case %s)", job.case_id)
    except Exception as error:
        logger.error("Writing a case summary failed (%s)", error_name(error))
