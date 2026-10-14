"""The handbook: the list, one section, one passage, and full-text search.

Every route needs a session and reads only the version the sandbox is pinned to. The version comes
from the session's own tenant row (`pinned_version_id`), never from the request, and `appliesToMe`
is worked out here from the signed-in person (invariant 1). The handbook is company-public, so
`appliesToMe` marks relevance and never hides a section.

Search here is full-text only, and every word is required. Hybrid search (with the question's
embedding) is the assistant's tool in Phase 4; the browser's search box must never call Voyage.
"""

import re
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.api.problems import problem_responses
from app.db.models import HandbookChunk, HandbookSection, HandbookVersion, Location
from app.domain.handbook.applicability import Asker, applies, audience_label
from app.domain.handbook.models import Audience
from app.modules.handbook.asker import load_asker
from app.modules.handbook.queries import ENGLISH
from app.modules.handbook.schemas import (
    AudienceOut,
    HandbookOverview,
    ListPassage,
    ParagraphPassage,
    PassageView,
    SearchResultOut,
    SearchResults,
    SectionDetail,
    SectionLink,
    SectionRef,
    SectionSummary,
    Segment,
    VersionInfo,
)
from app.modules.handbook.search import clean_query, group_name, passage_texts, pinned_version_id
from app.modules.identity.deps import SignedInDep

router = APIRouter(prefix="/handbook", tags=["handbook"])

NO_VERSION = "This sandbox has no handbook version."
NO_SECTION = "This section isn't in your handbook version."
NO_PASSAGE = "This passage isn't in that section."
EMPTY_QUERY = "Enter a word or two to search for."

# Reads need a session (401). The section and passage routes can find nothing, and search checks
# its input (422). All of them 404 for a sandbox with no pinned version.
LIST_ERRORS = problem_responses(status.HTTP_401_UNAUTHORIZED, status.HTTP_404_NOT_FOUND)
SEARCH_ERRORS = problem_responses(
    status.HTTP_401_UNAUTHORIZED,
    status.HTTP_404_NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_CONTENT,
)

# `ts_headline` marks matches with these private control characters instead of tags. The query
# is cleaned of them first, and stored passage text is stripped of them, so neither can forge a
# marker.
MATCH_START = "\x02"
MATCH_STOP = "\x03"
NO_MARKERS = str.maketrans("", "", MATCH_START + MATCH_STOP)
# A passage's whole text with every match marked; the excerpt is cut from it in `_excerpt`.
PASSAGE_HEADLINE_OPTIONS = f"StartSel={MATCH_START}, StopSel={MATCH_STOP}, HighlightAll=true"
EXCERPT_MAX_CHARACTERS = 300
# A result shows its excerpt on one line, about 118 characters at 1440 px (about 43 at 390 px), so
# a first match later than the threshold starts the excerpt mid-sentence, a few words before it.
EXCERPT_LEAD_THRESHOLD = 90
EXCERPT_LEAD_CHARACTERS = 30  # at most this many characters before the match, on a word boundary
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")
MAX_RESULTS = 50


@dataclass(frozen=True, slots=True)
class Context:
    """What every handbook read needs, loaded once per request."""

    db: AsyncSession
    version: HandbookVersion
    asker: Asker
    location_names: dict[str, str]


async def handbook_context(signed_in: SignedInDep) -> Context:
    db = signed_in.db
    version_id = await pinned_version_id(db)
    version = None if version_id is None else await db.get(HandbookVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_VERSION)
    asker = await load_asker(db, signed_in.actor)
    names = {code: name for code, name in (await db.execute(select(Location.code, Location.name)))}
    return Context(db, version, asker, names)


ContextDep = Annotated[Context, Depends(handbook_context)]


def _summary(section: HandbookSection, context: Context) -> SectionSummary:
    audience = Audience.from_json(section.audience)
    return SectionSummary(
        id=section.section_key,
        title=section.title,
        kind=section.kind,
        chapter=section.chapter,
        addendum_state=section.addendum_state,
        group_name=group_name(section, context.version.group_names),
        audience=AudienceOut(
            states=list(audience.states),
            employment_types=list(audience.employment_types),
            locations=list(audience.locations),
        ),
        audience_label=audience_label(audience, context.location_names),
        applies_to_me=applies(audience, context.asker),
        last_updated=section.updated_on,
    )


def _ref(section: HandbookSection, context: Context) -> SectionRef:
    audience = Audience.from_json(section.audience)
    return SectionRef(
        id=section.section_key,
        title=section.title,
        group_name=group_name(section, context.version.group_names),
        audience_label=audience_label(audience, context.location_names),
        applies_to_me=applies(audience, context.asker),
    )


def _refuse_nul(section_id: str) -> None:
    """Postgres text can't hold NUL, so a section ID with one would be a 500 at the query. No
    section has one, so it is a 404 before any query."""
    if "\x00" in section_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_SECTION)


async def _sections_without_blocks(context: Context) -> list[HandbookSection]:
    """Every section of the version in the handbook's order, without their bodies."""
    statement = (
        select(HandbookSection)
        .options(defer(HandbookSection.blocks))
        .where(HandbookSection.version_id == context.version.id)
        .order_by(HandbookSection.position)
    )
    return list((await context.db.scalars(statement)).all())


async def _section_with_blocks(context: Context, section_id: str) -> HandbookSection:
    _refuse_nul(section_id)
    section = (
        await context.db.scalars(
            select(HandbookSection).where(
                HandbookSection.version_id == context.version.id,
                HandbookSection.section_key == section_id,
            )
        )
    ).first()
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_SECTION)
    return section


@router.get(
    "",
    operation_id="getHandbook",
    summary="The handbook: its version and every section, in order",
    response_model=HandbookOverview,
    responses=LIST_ERRORS,
)
async def get_handbook(context: ContextDep) -> HandbookOverview:
    sections = await _sections_without_blocks(context)
    names = context.version.group_names
    return HandbookOverview(
        version=VersionInfo(
            label=context.version.label,
            title=context.version.title,
            updated_on=context.version.updated_on,
        ),
        chapters=names.get("chapters", {}),
        addenda=names.get("addenda", {}),
        sections=[_summary(section, context) for section in sections],
    )


@router.get(
    "/search",
    operation_id="searchHandbook",
    summary="Full-text search of the handbook: every word required, applicable sections first",
    response_model=SearchResults,
    responses=SEARCH_ERRORS,
)
async def search_handbook_text(
    context: ContextDep, q: Annotated[str, Query(max_length=100)]
) -> SearchResults:
    try:
        question = clean_query(q)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, EMPTY_QUERY) from None

    tsquery = func.plainto_tsquery(ENGLISH, bindparam("question", question))
    rank = func.ts_rank_cd(HandbookChunk.search, tsquery)
    # The best chunk of each section.
    best = (
        select(HandbookChunk.id.label("chunk_id"), HandbookChunk.section_id, rank.label("rank"))
        .where(
            HandbookChunk.version_id == context.version.id, HandbookChunk.search.op("@@")(tsquery)
        )
        .ext(distinct_on(HandbookChunk.section_id))
        .order_by(HandbookChunk.section_id, rank.desc(), HandbookChunk.position)
        .subquery()
    )
    rows = (
        await context.db.execute(
            select(
                HandbookSection,
                best.c.rank,
                HandbookChunk.passage_ids,
            )
            .join(best, best.c.section_id == HandbookSection.id)
            .join(HandbookChunk, HandbookChunk.id == best.c.chunk_id)
        )
    ).all()

    ranked = sorted(
        rows,
        key=lambda row: (
            not applies(Audience.from_json(row.HandbookSection.audience), context.asker),
            -row.rank,
            row.HandbookSection.position,
        ),
    )[:MAX_RESULTS]
    # Each result's excerpt comes from one passage, so the deep link and the excerpt agree: the
    # first passage of the chunk whose own headline has a match. Failing that (the words were only
    # in a heading or the title), the chunk's first passage, unmarked.
    candidates: list[tuple[int, str, str]] = []
    first_texts: dict[int, str] = {}
    for index, row in enumerate(ranked):
        texts = passage_texts(row.HandbookSection.blocks)
        candidates.extend((index, pid, texts[pid]) for pid in row.passage_ids if pid in texts)
        # Stored text can't forge a marker: strip them, as the SQL does for the headlines.
        first_texts[index] = texts.get(row.passage_ids[0], "").translate(NO_MARKERS)
    headlines = await _passage_headlines(context.db, question, [c[2] for c in candidates])
    picked: dict[int, tuple[str, str]] = {}
    for (index, pid, _), line in zip(candidates, headlines, strict=True):
        if MATCH_START in line and index not in picked:
            picked[index] = (pid, line)

    results = []
    for index, row in enumerate(ranked):
        if index in picked:
            pid, whole = picked[index]
            excerpt = _excerpt(whole)
        else:
            pid, excerpt = row.passage_ids[0], _excerpt(first_texts[index])
        results.append(
            SearchResultOut(
                section=_summary(row.HandbookSection, context),
                passage_id=pid,
                excerpt=excerpt,
            )
        )
    return SearchResults(results=results)


async def _passage_headlines(db: AsyncSession, question: str, bodies: list[str]) -> list[str]:
    """`ts_headline` of each passage text, in order, with the markers stripped from the text
    first. One statement for all of them; the text and the question are bound parameters."""
    if not bodies:
        return []
    rows = await db.execute(
        text(
            "SELECT t.i, ts_headline('english', translate(t.body, :markers, ''),"
            " plainto_tsquery('english', :question), :options)"
            " FROM unnest(CAST(:bodies AS text[])) WITH ORDINALITY AS t(body, i) ORDER BY t.i"
        ),
        {
            "markers": MATCH_START + MATCH_STOP,
            "question": question,
            "options": PASSAGE_HEADLINE_OPTIONS,
            "bodies": bodies,
        },
    )
    return [line for _, line in rows]


def _excerpt(whole: str) -> list[Segment]:
    """An excerpt from a passage's whole marked text: it starts at the beginning of the sentence
    with the first match and runs to the end of the passage, capped at about 300 characters on a
    word boundary with an ellipsis. A list item is a sentence of its own: its "- " is dropped and
    the items are joined with "; " (a space after an item that ends in punctuation)."""
    whole = re.sub(r"(?m)^- ", "", whole)
    first = max(whole.find(MATCH_START), 0)
    breaks = list(SENTENCE_BREAK.finditer(whole, 0, first))
    cut = whole[breaks[-1].end() :] if breaks else whole
    joined = re.sub(r"\n+", "; ", re.sub(r"(?<=[.!?])\n+", " ", cut))
    segments = _segments(joined)
    visible = "".join(segment.text for segment in segments)
    # A match far into a long sentence would be cut off, so start a few words before it instead.
    first_match = next((i for i, segment in enumerate(segments) if segment.match), 0)
    match_at = sum(len(segment.text) for segment in segments[:first_match])
    lead: list[Segment] = []
    if match_at > EXCERPT_LEAD_THRESHOLD:
        # With no space just before the match, the excerpt starts at the match itself.
        space = visible.find(" ", match_at - EXCERPT_LEAD_CHARACTERS, match_at)
        begin = space + 1 if space >= 0 else match_at
        segments = _slice(segments, begin, len(visible))
        visible = visible[begin:]
        lead = [Segment(text="…", match=False)]
    limit = EXCERPT_MAX_CHARACTERS - len(lead)
    if len(visible) <= limit:
        return [*lead, *segments]
    end = visible.rfind(" ", 0, limit + 1)
    end = end if end > 0 else limit
    kept = _slice(segments, 0, end)
    kept[-1] = Segment(text=kept[-1].text.rstrip(), match=kept[-1].match)
    return [*lead, *kept, Segment(text="…", match=False)]


def _slice(segments: list[Segment], begin: int, end: int) -> list[Segment]:
    """The segments' visible characters from `begin` to `end`, with their match flags kept."""
    sliced: list[Segment] = []
    at = 0
    for segment in segments:
        piece = segment.text[max(begin - at, 0) : max(end - at, 0)]
        at += len(segment.text)
        if piece:
            sliced.append(Segment(text=piece, match=segment.match))
    return sliced


def _segments(headline: str) -> list[Segment]:
    """Split `ts_headline`'s text on the private markers: `[{text, match}]`, never HTML."""
    segments: list[Segment] = []
    matching = False
    for piece in re.split(f"([{MATCH_START}{MATCH_STOP}])", headline):
        if piece == MATCH_START:
            matching = True
        elif piece == MATCH_STOP:
            matching = False
        elif piece:
            segments.append(Segment(text=piece, match=matching))
    return segments


@router.get(
    "/sections/{section_id}",
    operation_id="getHandbookSection",
    summary="One section: its text, related sections, sources, and neighbors",
    response_model=SectionDetail,
    responses=LIST_ERRORS,
)
async def get_section(section_id: str, context: ContextDep) -> SectionDetail:
    section = await _section_with_blocks(context, section_id)
    everything = await _sections_without_blocks(context)
    place = next(i for i, other in enumerate(everything) if other.section_key == section_id)
    supplements = [
        _ref(other, context) for other in everything if other.section_key == section.supplements_key
    ]
    supplemented_by = [
        _ref(other, context) for other in everything if other.supplements_key == section_id
    ]
    before = everything[place - 1] if place > 0 else None
    after = everything[place + 1] if place + 1 < len(everything) else None
    summary = _summary(section, context)
    return SectionDetail(
        **summary.model_dump(),
        blocks=section.blocks,
        sources=list(section.sources),
        supplements=supplements[0] if supplements else None,
        supplemented_by=supplemented_by,
        previous=None if before is None else SectionLink(id=before.section_key, title=before.title),
        next=None if after is None else SectionLink(id=after.section_key, title=after.title),
    )


@router.get(
    "/sections/{section_id}/passages/{passage_id}",
    operation_id="getHandbookPassage",
    summary="One passage with the passages around it: what the passage panel shows",
    response_model=PassageView,
    responses=LIST_ERRORS,
)
async def get_passage(section_id: str, passage_id: str, context: ContextDep) -> PassageView:
    # The passage ID is matched here, never sent to Postgres, so a NUL in it is just "not found".
    section = await _section_with_blocks(context, section_id)
    passages = [block for block in section.blocks if block["type"] == "passage"]
    place = next((i for i, block in enumerate(passages) if block["id"] == passage_id), None)
    if place is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_PASSAGE)

    def passage(block: dict[str, Any]) -> ParagraphPassage | ListPassage:
        model = ParagraphPassage if block["kind"] == "paragraph" else ListPassage
        return model.model_validate(block)

    return PassageView(
        section=_summary(section, context),
        passage=passage(passages[place]),
        previous=passage(passages[place - 1]) if place > 0 else None,
        next=passage(passages[place + 1]) if place + 1 < len(passages) else None,
    )
