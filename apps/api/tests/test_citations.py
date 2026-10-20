"""Mapping the model's citations to the handbook passages they point at."""

import logging
from datetime import date

import pytest

from app.ai.citations import CitationEvent, CitationMapper
from app.ai.conversations import SourceEntry
from app.ai.transport import SearchResultCitation


def entry(section: str, passages: tuple[str, ...] = ("p1", "p2", "p3")) -> SourceEntry:
    return SourceEntry(
        section_id=section,
        passage_ids=passages,
        title=f"Title of {section}",
        group_name="California addendum",
        audience_label="California",
        last_updated=date(2026, 9, 12),
        deep_link=f"/handbook/{section}?passage={passages[0]}",
    )


def cite(
    entries: list[SourceEntry], index: int, start: int = 0, end: int = 1, text: str = "words"
) -> SearchResultCitation:
    return SearchResultCitation(
        search_result_index=index,
        start_block_index=start,
        end_block_index=end,
        source=entries[index].deep_link,
        title=entries[index].title,
        cited_text=text,
    )


ENTRIES = [entry("CA-4.1"), entry("CA-4.2"), entry("CA-4.3"), entry("CA-4.4"), entry("CA-4.5")]


def test_one_block_gives_one_event_with_the_whole_payload() -> None:
    mapper = CitationMapper(ENTRIES)
    [event] = mapper.on_block_end(214, [cite(ENTRIES, 2, 1, 2, "Sick leave accrues.")])
    assert event.to_json() == {
        "marker": 1,
        "offsetUtf16": 214,
        "sectionId": "CA-4.3",
        "passageId": "p2",
        "title": "Title of CA-4.3",
        "groupName": "California addendum",
        "audienceLabel": "California",
        "lastUpdated": "2026-09-12",
        "deepLink": "/handbook/CA-4.3?passage=p2",
        "citedText": "Sick leave accrues.",
    }


def test_result_index_3_is_the_fourth_result_across_the_whole_conversation() -> None:
    # Three results came from earlier turns, one is new this turn.
    mapper = CitationMapper(ENTRIES[:3])
    mapper.add([ENTRIES[3]])
    [event] = mapper.on_block_end(10, [cite(ENTRIES, 3)])
    assert event.section_id == "CA-4.4"


def test_blocks_1_to_3_give_two_events_for_passages_2_and_3() -> None:
    mapper = CitationMapper(ENTRIES)
    events = mapper.on_block_end(50, [cite(ENTRIES, 0, 1, 3, "two passages")])
    assert [(e.passage_id, e.marker) for e in events] == [("p2", 1), ("p3", 2)]
    assert [e.deep_link for e in events] == [
        "/handbook/CA-4.1?passage=p2",
        "/handbook/CA-4.1?passage=p3",
    ]
    assert {e.offset_utf16 for e in events} == {50}


def test_a_passage_cited_twice_keeps_its_marker() -> None:
    mapper = CitationMapper(ENTRIES)
    first = mapper.on_block_end(10, [cite(ENTRIES, 1)])
    other = mapper.on_block_end(20, [cite(ENTRIES, 2)])
    again = mapper.on_block_end(30, [cite(ENTRIES, 1)])
    assert [first[0].marker, other[0].marker, again[0].marker] == [1, 2, 1]
    assert again[0].offset_utf16 == 30


def test_the_same_passage_twice_in_one_block_is_one_event() -> None:
    mapper = CitationMapper(ENTRIES)
    events = mapper.on_block_end(10, [cite(ENTRIES, 1), cite(ENTRIES, 1)])
    assert len(events) == 1


def test_offset_is_the_answer_length_at_the_blocks_end() -> None:
    mapper = CitationMapper(ENTRIES)
    [event] = mapper.on_block_end(0, [cite(ENTRIES, 0)])
    assert event.offset_utf16 == 0
    [event] = mapper.on_block_end(1234, [cite(ENTRIES, 1)])
    assert event.offset_utf16 == 1234


def test_a_block_with_no_citations_gives_no_events() -> None:
    assert CitationMapper(ENTRIES).on_block_end(10, []) == []


def test_a_source_that_does_not_match_is_dropped_and_logged_without_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bad = SearchResultCitation(1, 0, 1, "/handbook/OTHER?passage=p1", "t", "SECRET CITED TEXT")
    mapper = CitationMapper(ENTRIES)
    with caplog.at_level(logging.WARNING):
        events = mapper.on_block_end(10, [bad, cite(ENTRIES, 2)])
    assert [e.section_id for e in events] == ["CA-4.3"]
    assert "SECRET CITED TEXT" not in caplog.text
    assert "OTHER" not in caplog.text
    assert "(source does not match): result 1, blocks 0 to 1, of 5 results" in caplog.text
    # The dropped one used no marker number.
    assert events[0].marker == 1


@pytest.mark.parametrize(
    ("index", "start", "end"),
    [(5, 0, 1), (-1, 0, 1), (0, 3, 4), (0, 0, 4), (0, -1, 1), (0, 2, 2), (0, 2, 1)],
)
def test_an_index_out_of_range_is_dropped_and_logged_without_text(
    index: int, start: int, end: int, caplog: pytest.LogCaptureFixture
) -> None:
    mapper = CitationMapper(ENTRIES)
    bad = SearchResultCitation(index, start, end, ENTRIES[0].deep_link, "t", "SECRET CITED TEXT")
    with caplog.at_level(logging.WARNING):
        assert mapper.on_block_end(10, [bad]) == []
    assert "SECRET CITED TEXT" not in caplog.text
    assert f"result {index}, blocks {start} to {end}, of 5 results" in caplog.text


def test_several_blocks_share_the_cited_text_of_the_range() -> None:
    # The API gives the cited text of the whole range, not of each block.
    mapper = CitationMapper(ENTRIES)
    events = mapper.on_block_end(10, [cite(ENTRIES, 0, 0, 2, "first second")])
    assert [e.cited_text for e in events] == ["first second", "first second"]


def test_an_event_is_frozen() -> None:
    [event] = CitationMapper(ENTRIES).on_block_end(1, [cite(ENTRIES, 0)])
    assert isinstance(event, CitationEvent)
    with pytest.raises(AttributeError):
        event.marker = 9  # type: ignore[misc]


def test_restarting_the_markers_numbers_from_one_again_but_keeps_every_result() -> None:
    mapper = CitationMapper(ENTRIES)
    [first] = mapper.on_block_end(10, [cite(ENTRIES, 1)])
    [second] = mapper.on_block_end(20, [cite(ENTRIES, 2)])
    assert (first.marker, second.marker) == (1, 2)

    mapper.restart_markers()

    # The result at index 4 still resolves, and a passage cited before is numbered afresh.
    [again] = mapper.on_block_end(5, [cite(ENTRIES, 2)])
    [other] = mapper.on_block_end(6, [cite(ENTRIES, 4)])
    assert (again.marker, again.section_id) == (1, "CA-4.3")
    assert (other.marker, other.section_id) == (2, "CA-4.5")
