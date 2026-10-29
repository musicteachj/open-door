"""The case routes: a person opens and follows their own cases, and HR works the queue.

The service does the work and the policy layer decides who may act; a refusal is a `ProblemError`
and becomes an RFC 9457 problem. A case someone cannot see is a 404 `case-not-found` from every
route, so a probe cannot tell it from one that does not exist. The one exception is HR's own case,
which the service refuses with a 403 `case-own`: HR already sees it in the queue.

Fixed paths (`/mine`, `/texts`, `/counts`) are declared before `/{case_id}`, or the UUID parameter
would answer them with a 422.

The two reads that decrypt (`/summary` and `/text`) need the `X-CSRF-Token` header on a GET, are
audited by the service, and send `Cache-Control: no-store` (the middleware covers refusals).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status

from app.ai.budget import Caps
from app.ai.case_summary import Summarizer
from app.ai.guard import CaseGuard
from app.api.deps import get_app_settings, get_engine, get_keys, get_summarizer, get_transport
from app.api.problems import problem_responses
from app.core.cache_control import CACHE_CONTROL_HEADER, NO_STORE
from app.core.encryption import KeyProvider
from app.db.locks import database_now
from app.db.tenancy import TenantContext
from app.modules.cases import queries, service, texts
from app.modules.cases.api_schemas import (
    CaseDetailOut,
    CaseListOut,
    CaseSentOut,
    CaseStatusOut,
    CaseSummaryOut,
    CaseTextOut,
    CaseTextsOut,
    CountsOut,
    OpenCaseBody,
    QueuePageOut,
    StatusBody,
    SummaryRetryOut,
    sent_line_out,
)
from app.modules.cases.schemas import OpenCase, QueueFilter
from app.modules.cases.summary_task import SummaryJob, run_summary_job
from app.modules.identity.deps import AuditedReadDep, CallerDep, SignedInDep

router = APIRouter(prefix="/cases", tags=["cases"])

READ_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)
AUDITED_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)
WRITE_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_409_CONFLICT,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)


def get_case_guard(request: Request) -> CaseGuard:
    """The guard a case's words are screened by: the app's transport, engine, and budget caps."""
    return CaseGuard(
        get_transport(request), get_engine(request), Caps.from_settings(get_app_settings(request))
    )


def schedule_summary(background: BackgroundTasks, job: SummaryJob) -> None:
    """The one place a summary job is scheduled: a new case's first summary and HR's retry. The job
    holds the words in memory: they are never read from the database for it."""
    background.add_task(run_summary_job, job)


@router.post(
    "",
    operation_id="openCase",
    summary="Open a confidential case in the person's own words",
    response_model=CaseSentOut,
    responses={
        status.HTTP_200_OK: {"description": "The submission already had a case: the same one."},
        **WRITE_ERRORS,
    },
    status_code=status.HTTP_201_CREATED,
)
async def open_case(
    body: OpenCaseBody,
    caller: CallerDep,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    guard: Annotated[CaseGuard, Depends(get_case_guard)],
    keys: Annotated[KeyProvider, Depends(get_keys)],
    summarizer: Annotated[Summarizer | None, Depends(get_summarizer)],
) -> CaseSentOut:
    opened = await service.open_case(
        get_engine(request),
        keys,
        guard,
        caller.actor,
        OpenCase(body.submission_id, body.category, body.text, body.turn_id),
    )
    if opened.created:
        if opened.summary_due:
            job = SummaryJob(
                guard=guard,
                keys=keys,
                summarizer=summarizer,
                # The case's opener, who may add the first summary in the first 10 minutes.
                ctx=TenantContext(caller.actor.tenant_id, caller.actor.person_id),
                case_id=opened.case.id,
                category=body.category,
                words=body.text,
            )
            schedule_summary(background, job)
    else:
        response.status_code = status.HTTP_200_OK
    return CaseSentOut(
        case=CaseStatusOut.model_validate(opened.case, from_attributes=True),
        sent_line=sent_line_out(opened.case.reply_by, is_hr=caller.actor.is_hr_admin),
        created=opened.created,
        crisis_text=opened.crisis_text,
    )


# The fixed paths come before "/{case_id}".
@router.get(
    "/mine",
    operation_id="listMyCases",
    summary="The signed-in person's own cases: status and dates, never the words",
    response_model=CaseListOut,
    responses=READ_ERRORS,
)
async def list_my_cases(signed_in: SignedInDep) -> CaseListOut:
    views = await service.my_cases(signed_in.db, signed_in.actor)
    return CaseListOut(
        items=[CaseStatusOut.model_validate(view, from_attributes=True) for view in views]
    )


@router.get(
    "/texts",
    operation_id="getCaseTexts",
    summary="The case form's fixed texts, with today's reply-by date",
    response_model=CaseTextsOut,
    responses=READ_ERRORS,
)
async def get_case_texts(signed_in: SignedInDep) -> CaseTextsOut:
    # The database's clock, the one the reply-by date of a case sent now would come from.
    now = await database_now(signed_in.db)
    reply_by = await queries.reply_by_at(signed_in.db, signed_in.actor.tenant_id, now)
    return CaseTextsOut(
        bullets=list(texts.form_texts(reply_by)),
        reply_by=reply_by,
        waiting_limit=texts.WAITING_LIMIT_TEXT,
    )


@router.get(
    "/counts",
    operation_id="getCaseCounts",
    summary="HR's new cases and the ones due for a reply, for the nav and the home card",
    response_model=CountsOut,
    responses=READ_ERRORS,
)
async def get_case_counts(signed_in: SignedInDep) -> CountsOut:
    counts = await service.counts(signed_in.db, signed_in.actor)
    return CountsOut(new=counts.new, reply_due=counts.reply_due)


@router.get(
    "",
    operation_id="listCases",
    summary="HR's queue of cases, a page at a time: no words",
    response_model=QueuePageOut,
    responses=READ_ERRORS,
)
async def list_cases(
    signed_in: SignedInDep,
    status_filter: Annotated[QueueFilter | None, Query(alias="status")] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> QueuePageOut:
    page = await service.queue(signed_in.db, signed_in.actor, status_filter, cursor)
    return QueuePageOut.model_validate(page, from_attributes=True)


@router.get(
    "/{case_id}",
    operation_id="getCase",
    summary="One case's metadata for HR: no words, and not an audited read",
    response_model=CaseDetailOut,
    responses=READ_ERRORS,
)
async def get_case(case_id: UUID, signed_in: SignedInDep) -> CaseDetailOut:
    detail = await service.case_detail(signed_in.db, signed_in.actor, case_id)
    return CaseDetailOut.model_validate(detail, from_attributes=True)


@router.get(
    "/{case_id}/summary",
    operation_id="getCaseSummary",
    summary="A case's AI summary, for HR. An audited read; needs the CSRF header.",
    response_model=CaseSummaryOut,
    responses=AUDITED_ERRORS,
    dependencies=[AuditedReadDep],
)
async def get_case_summary(
    case_id: UUID,
    signed_in: SignedInDep,
    keys: Annotated[KeyProvider, Depends(get_keys)],
    response: Response,
) -> CaseSummaryOut:
    read = await service.case_summary_for(signed_in.db, keys, signed_in.actor, case_id)
    # The middleware covers refusals; this keeps the success response's header explicit.
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE
    return CaseSummaryOut.model_validate(read, from_attributes=True)


@router.get(
    "/{case_id}/text",
    operation_id="getCaseText",
    summary="A case's words, for HR. An audited read; needs the CSRF header.",
    response_model=CaseTextOut,
    responses=AUDITED_ERRORS,
    dependencies=[AuditedReadDep],
)
async def get_case_text(
    case_id: UUID,
    signed_in: SignedInDep,
    keys: Annotated[KeyProvider, Depends(get_keys)],
    response: Response,
) -> CaseTextOut:
    words = await service.case_text_for(signed_in.db, keys, signed_in.actor, case_id)
    # The middleware covers refusals; this keeps the success response's header explicit.
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE
    return CaseTextOut(text=words)


@router.post(
    "/{case_id}/status",
    operation_id="changeCaseStatus",
    summary="Move a case on, after reading its words (HR only, never their own case)",
    response_model=CaseStatusOut,
    responses=WRITE_ERRORS,
)
async def change_case_status(
    case_id: UUID, body: StatusBody, signed_in: SignedInDep
) -> CaseStatusOut:
    view = await service.change_status(signed_in.db, signed_in.actor, case_id, body.to)
    return CaseStatusOut.model_validate(view, from_attributes=True)


@router.post(
    "/{case_id}/summary",
    operation_id="retryCaseSummary",
    summary="Try the AI summary again (HR only, never their own case): written in the background",
    response_model=SummaryRetryOut,
    responses={
        status.HTTP_202_ACCEPTED: {"description": "The retry was scheduled."},
        **WRITE_ERRORS,
    },
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_case_summary(
    case_id: UUID,
    signed_in: SignedInDep,
    background: BackgroundTasks,
    guard: Annotated[CaseGuard, Depends(get_case_guard)],
    keys: Annotated[KeyProvider, Depends(get_keys)],
    summarizer: Annotated[Summarizer | None, Depends(get_summarizer)],
) -> SummaryRetryOut:
    plan = await service.plan_summary_retry(signed_in.db, keys, signed_in.actor, case_id)
    actor = signed_in.actor
    # Screening and the model call run after the response, with no session held.
    job = SummaryJob(
        guard=guard,
        keys=keys,
        summarizer=summarizer,
        ctx=TenantContext(actor.tenant_id, actor.person_id),
        case_id=plan.case_id,
        category=plan.category,
        words=plan.words,
        actor=actor,
        screen_first=plan.unscreened,
    )
    schedule_summary(background, job)
    return SummaryRetryOut(status="writing")
