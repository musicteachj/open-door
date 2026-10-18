"""The sections a turn retrieved, as the page lists them: each section once.

A turn that searches twice can retrieve one section twice, and the stored list has an entry for
each search result. The page keys its "Sections retrieved" list by section, so the API lists each
section once, in the order it was first retrieved, with its passages merged.
"""

from typing import Any

from app.modules.assistant.display import sections_out

NAMES = {"4.3": ("Sick leave", "Company handbook"), "4.2": ("Paid time off", "Company handbook")}


def stored(*entries: tuple[str, list[str]]) -> list[dict[str, Any]]:
    return [{"sectionId": section, "passageIds": passages} for section, passages in entries]


def test_a_section_retrieved_twice_is_listed_once_with_its_passages_merged() -> None:
    out = sections_out(stored(("4.3", ["p1", "p2"]), ("4.2", ["p1"]), ("4.3", ["p2", "p3"])), NAMES)

    assert [(s.section_id, s.passage_ids) for s in out] == [
        ("4.3", ["p1", "p2", "p3"]),
        ("4.2", ["p1"]),
    ]


def test_sections_keep_the_order_they_were_first_retrieved() -> None:
    out = sections_out(stored(("4.2", ["p1"]), ("4.3", ["p1"]), ("4.2", ["p2"])), NAMES)

    assert [s.section_id for s in out] == ["4.2", "4.3"]


def test_a_repeated_passage_is_not_repeated_and_the_first_order_stands() -> None:
    out = sections_out(stored(("4.3", ["p2", "p1"]), ("4.3", ["p1", "p2"])), NAMES)

    assert out[0].passage_ids == ["p2", "p1"]


def test_titles_and_groups_come_from_the_names_and_stay_none_when_unknown() -> None:
    out = sections_out(stored(("4.3", ["p1"]), ("GONE-9.9", ["p1"]), ("GONE-9.9", ["p2"])), NAMES)

    assert (out[0].title, out[0].group_name) == ("Sick leave", "Company handbook")
    assert (out[1].title, out[1].group_name) == (None, None)
    assert len(out) == 2


def test_the_stored_list_is_not_changed() -> None:
    entries = stored(("4.3", ["p1"]), ("4.3", ["p2"]))

    sections_out(entries, NAMES)

    assert entries == stored(("4.3", ["p1"]), ("4.3", ["p2"]))


def test_nothing_retrieved_is_an_empty_list() -> None:
    assert sections_out([], NAMES) == []
