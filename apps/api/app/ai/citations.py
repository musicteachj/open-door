"""Turning the model's citations into the passages a person can open.

A citation arrives as a `search_result_location`: which search result (`search_result_index`, which
counts every result in the request, across the whole conversation and every tool result), and which
of its text blocks (`start_block_index` up to, not including, `end_block_index`). The server keeps
the conversation's list of results (`SourceEntry`, one per result, in order), so result `i` and
block `b` are passage `passage_ids[b]` of entry `i`.

One mapper serves one turn. It starts from the conversation's earlier results (`search_sources`),
takes this turn's new ones with `add`, and numbers markers within the turn's one answer.
"""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from app.ai.conversations import SourceEntry
from app.ai.transport import SearchResultCitation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CitationEvent:
    """The `citation` event's payload: a marker to place, and the passage it opens."""

    marker: int
    # The answer's length in UTF-16 code units (a browser's string indexes) where the cited block
    # ends: where the marker goes. An emoji counts two.
    offset_utf16: int
    section_id: str
    passage_id: str
    title: str
    group_name: str
    audience_label: str
    last_updated: str
    deep_link: str
    # The text the model cited. When one citation spans several blocks the API gives the cited
    # text of the whole range only, so each passage's event carries that range's text.
    cited_text: str

    def to_json(self) -> dict[str, Any]:
        return {
            "marker": self.marker,
            "offsetUtf16": self.offset_utf16,
            "sectionId": self.section_id,
            "passageId": self.passage_id,
            "title": self.title,
            "groupName": self.group_name,
            "audienceLabel": self.audience_label,
            "lastUpdated": self.last_updated,
            "deepLink": self.deep_link,
            "citedText": self.cited_text,
        }


class CitationMapper:
    def __init__(self, sources: Iterable[SourceEntry] = ()) -> None:
        self._sources: list[SourceEntry] = list(sources)
        self._markers: dict[tuple[str, str], int] = {}

    def add(self, entries: Iterable[SourceEntry]) -> None:
        """Append the results this turn's tools returned, in the order they were sent."""
        self._sources.extend(entries)

    def restart_markers(self) -> None:
        """Number the markers from 1 again, for text that was taken back. The results stay:
        `search_result_index` counts across the whole conversation."""
        self._markers.clear()

    def on_block_end(
        self, answer_length: int, citations: Sequence[SearchResultCitation]
    ) -> list[CitationEvent]:
        """The events for a text block that has just ended, with its citations.

        A citation that doesn't fit the results (a wrong index, a block out of range, or a
        `source` other than the result's) is dropped and logged by its numbers only, never by the
        text it cited.
        """
        events: list[CitationEvent] = []
        seen: set[tuple[str, str]] = set()
        for citation in citations:
            source = self._source_for(citation)
            if source is None:
                continue
            for block in range(citation.start_block_index, citation.end_block_index):
                passage_id = source.passage_ids[block]
                key = (source.section_id, passage_id)
                if key in seen:
                    continue
                seen.add(key)
                marker = self._markers.setdefault(key, len(self._markers) + 1)
                events.append(
                    CitationEvent(
                        marker=marker,
                        offset_utf16=answer_length,
                        section_id=source.section_id,
                        passage_id=passage_id,
                        title=source.title,
                        group_name=source.group_name,
                        audience_label=source.audience_label,
                        last_updated=source.last_updated.isoformat(),
                        deep_link=f"/handbook/{source.section_id}?passage={passage_id}",
                        cited_text=citation.cited_text,
                    )
                )
        return events

    def _source_for(self, citation: SearchResultCitation) -> SourceEntry | None:
        index = citation.search_result_index
        start, end = citation.start_block_index, citation.end_block_index
        if not 0 <= index < len(self._sources):
            self._drop("result index out of range", citation)
            return None
        source = self._sources[index]
        if not 0 <= start < end <= len(source.passage_ids):
            self._drop("block range out of range", citation)
            return None
        if citation.source != source.deep_link:
            self._drop("source does not match", citation)
            return None
        return source

    def _drop(self, reason: str, citation: SearchResultCitation) -> None:
        logger.warning(
            "Dropped a citation (%s): result %d, blocks %d to %d, of %d results",
            reason,
            citation.search_result_index,
            citation.start_block_index,
            citation.end_block_index,
            len(self._sources),
        )
