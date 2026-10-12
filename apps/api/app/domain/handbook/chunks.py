"""Split a section into the chunks retrieval searches.

A chunk is the run of passages under one `##` heading, split before it passes a size cap. A
passage is never split, so a citation maps to whole passages, and a chunk never crosses a `##`.
A `###` heading stays inside its `##` run, as a line of the chunk's text, and travels with the
passage after it if the run splits there.
"""

from dataclasses import dataclass

from app.domain.handbook.blocks import Heading, Passage
from app.domain.handbook.models import Section

# Bump when the chunking rules change: it is part of the content hash, so a change makes a new
# version.
CHUNKER_VERSION = 1
CHARACTERS_PER_TOKEN = 4


@dataclass(frozen=True, slots=True)
class Chunk:
    section_id: str
    # The chunk's place among its section's chunks, from 0.
    position: int
    # The `##` heading it sits under; None for text before the section's first `##`.
    heading: str | None
    passage_ids: tuple[str, ...]
    text: str
    # What gets embedded: "4.3 Sick leave · Time off\nHow much\n\n<text>". With no heading, that
    # line is left out.
    embed_text: str


@dataclass
class _Run:
    heading: str | None
    parts: list[str]
    passage_ids: list[str]
    tokens: int = 0


def estimated_tokens(text: str) -> int:
    """A rough count, at four characters a token. The cap is only a size guide."""
    return -(-len(text) // CHARACTERS_PER_TOKEN)


def chunks_for(section: Section, *, max_tokens: int = 350) -> list[Chunk]:
    runs: list[_Run] = []
    current = _Run(None, [], [])
    pending: list[str] = []  # `###` headings waiting for the passage they introduce

    def close() -> None:
        if current.passage_ids:
            runs.append(current)

    for block in section.blocks:
        if isinstance(block, Heading) and block.level == 2:
            close()
            current = _Run(block.text, [], [])
            pending = []
        elif isinstance(block, Heading):
            pending.append(block.text)
        elif isinstance(block, Passage):
            unit = [*pending, block.text]
            pending = []
            tokens = sum(estimated_tokens(part) for part in unit)
            if current.passage_ids and current.tokens + tokens > max_tokens:
                close()
                current = _Run(current.heading, [], [])
            current.parts.extend(unit)
            current.passage_ids.append(block.id)
            current.tokens += tokens
    close()

    return [_chunk(section, position, run) for position, run in enumerate(runs)]


def _chunk(section: Section, position: int, run: _Run) -> Chunk:
    text = "\n\n".join(run.parts)
    title = f"{section.id} {section.title} · {section.group_name}"
    heading_line = f"{run.heading}\n" if run.heading else ""
    return Chunk(
        section_id=section.id,
        position=position,
        heading=run.heading,
        passage_ids=tuple(run.passage_ids),
        text=text,
        embed_text=f"{title}\n{heading_line}\n{text}",
    )
