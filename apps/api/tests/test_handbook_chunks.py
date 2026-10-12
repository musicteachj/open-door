"""Passages, chunks, and the content hash."""

import dataclasses
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from app.domain.handbook import hashing
from app.domain.handbook.blocks import Heading, Passage, blocks_to_json
from app.domain.handbook.chunks import CHUNKER_VERSION, Chunk, chunks_for
from app.domain.handbook.hashing import content_hash
from app.domain.handbook.models import Audience, Handbook, Section
from app.domain.handbook.parse import parse_body
from app.modules.handbook.source import read_handbook

FIXTURE = Path(__file__).parent / "fixtures" / "handbook"


@pytest.fixture(scope="module")
def handbook() -> Handbook:
    return read_handbook(FIXTURE)


def section_with(body: str) -> Section:
    """A company section, 4.3 "Sick leave" in "Time off", whose body is `body`."""
    parsed = parse_body("sections/4.3-sick-leave.md", body, 0)
    assert not parsed.errors
    return Section(
        id="4.3",
        title="Sick leave",
        kind="company",
        chapter=4,
        addendum_state=None,
        group_name="Time off",
        supplements=None,
        updated=date(2026, 10, 7),
        audience=Audience(),
        sources=(),
        blocks=parsed.blocks,
        path="sections/4.3-sick-leave.md",
    )


def paragraph(label: str, characters: int = 400) -> str:
    """A paragraph of exactly `characters` characters: 100 tokens at 4 characters a token."""
    return (label + " " + "word " * characters)[:characters].rstrip().ljust(characters, "x")


# Passages


def test_passages_are_numbered_in_order_across_paragraphs_and_lists(handbook: Handbook) -> None:
    blocks = handbook.sections[1].blocks

    passages = [block for block in blocks if isinstance(block, Passage)]
    assert [(p.id, p.kind) for p in passages] == [
        ("p1", "paragraph"),
        ("p2", "list"),
        ("p3", "paragraph"),
        ("p4", "list"),
    ]


def test_headings_get_no_passage_id(handbook: Handbook) -> None:
    headings = [b for b in handbook.sections[1].blocks if isinstance(b, Heading)]

    assert [(h.level, h.text) for h in headings] == [(2, "How much"), (3, "Notice")]
    assert not hasattr(headings[0], "id")


def test_blocks_serialize_to_camel_case_json(handbook: Handbook) -> None:
    blocks = blocks_to_json(handbook.sections[0].blocks)

    assert blocks[0] == {"type": "heading", "level": 2, "text": "Welcome"}
    assert blocks[1]["type"] == "passage"
    assert blocks[1]["id"] == "p1"
    assert blocks[1]["kind"] == "paragraph"
    assert blocks[1]["inlines"][1] == {  # type: ignore[index]
        "text": "demo content",
        "bold": True,
        "italic": False,
        "linkSectionId": None,
    }
    linked = blocks[1]["inlines"][-2]  # type: ignore[index]
    assert linked["linkSectionId"] == "4.3"


def test_a_list_serializes_its_items_and_whether_it_is_numbered(handbook: Handbook) -> None:
    blocks = blocks_to_json(handbook.sections[1].blocks)
    bulleted, numbered = (b for b in blocks if b.get("kind") == "list")

    assert bulleted["ordered"] is False
    assert numbered["ordered"] is True
    items = cast("list[list[dict[str, object]]]", numbered["items"])
    assert [item[0]["text"] for item in items] == ["Message them", "Call them"]


# Chunks


def test_a_chunk_is_the_run_of_passages_under_one_heading(handbook: Handbook) -> None:
    chunks = chunks_for(handbook.sections[1])

    assert [(c.position, c.heading, c.passage_ids) for c in chunks] == [
        (0, None, ("p1",)),
        (1, "How much", ("p2", "p3", "p4")),
    ]


def test_a_third_level_heading_stays_inside_its_chunk_as_a_line_of_text(
    handbook: Handbook,
) -> None:
    chunk = chunks_for(handbook.sections[1])[1]

    assert chunk.text == (
        "- 40 hours a year\n- Front-loaded on January 1\n\n"
        "Notice\n\n"
        "Tell your manager as soon as you can.\n\n"
        "- Message them\n- Call them"
    )


def test_text_before_the_first_second_level_heading_is_a_chunk_without_a_heading() -> None:
    chunks = chunks_for(section_with("Intro text.\n\n## Later\n\nMore."))

    assert [(c.heading, c.passage_ids, c.text) for c in chunks] == [
        (None, ("p1",), "Intro text."),
        ("Later", ("p2",), "More."),
    ]


def test_a_chunk_never_crosses_a_second_level_heading() -> None:
    body = "## A\n\nOne.\n\n## B\n\nTwo.\n\n## C\n\nThree."

    chunks = chunks_for(section_with(body))

    assert [(c.heading, c.passage_ids) for c in chunks] == [
        ("A", ("p1",)),
        ("B", ("p2",)),
        ("C", ("p3",)),
    ]


def test_a_heading_with_no_passages_makes_no_chunk() -> None:
    chunks = chunks_for(section_with("## Empty\n\n## Full\n\nText."))
    assert [(c.position, c.heading) for c in chunks] == [(0, "Full")]


def test_a_long_run_splits_before_the_token_cap_without_splitting_a_passage() -> None:
    body = "## Long\n\n" + "\n\n".join(paragraph(str(n)) for n in range(5))

    chunks = chunks_for(section_with(body), max_tokens=350)

    # Each paragraph is 100 tokens, so three fit (300) and a fourth would pass 350.
    assert [c.passage_ids for c in chunks] == [("p1", "p2", "p3"), ("p4", "p5")]
    assert [c.heading for c in chunks] == ["Long", "Long"]
    assert [c.position for c in chunks] == [0, 1]


def test_a_passage_larger_than_the_cap_is_its_own_chunk() -> None:
    body = "Small.\n\n" + paragraph("big", 2000) + "\n\nSmall again."

    chunks = chunks_for(section_with(body), max_tokens=350)

    assert [c.passage_ids for c in chunks] == [("p1",), ("p2",), ("p3",)]


def test_a_third_level_heading_travels_with_the_passage_after_a_split() -> None:
    body = (
        "## A\n\n" + paragraph("a") + "\n\n" + paragraph("b") + "\n\n### Sub\n\n" + paragraph("c")
    )

    chunks = chunks_for(section_with(body), max_tokens=250)

    assert [c.passage_ids for c in chunks] == [("p1", "p2"), ("p3",)]
    assert chunks[1].text.startswith("Sub\n\n")
    assert "Sub" not in chunks[0].text


def test_embed_text_has_the_id_title_group_heading_and_text(handbook: Handbook) -> None:
    chunk = chunks_for(handbook.sections[1])[1]

    assert chunk.embed_text == f"4.3 Sick leave · Time off\nHow much\n\n{chunk.text}"


def test_embed_text_leaves_out_a_missing_heading(handbook: Handbook) -> None:
    chunk = chunks_for(handbook.sections[1])[0]

    assert chunk.embed_text == "4.3 Sick leave · Time off\n\nEveryone gets sick leave."


def test_an_addendum_chunk_names_the_addendum(handbook: Handbook) -> None:
    chunk = chunks_for(handbook.sections[2])[0]

    assert chunk.embed_text.startswith("CA-4.3 Sick leave · California addendum\n\n")


def test_chunks_carry_their_section_id(handbook: Handbook) -> None:
    assert {c.section_id for c in chunks_for(handbook.sections[1])} == {"4.3"}
    assert isinstance(chunks_for(handbook.sections[1])[0], Chunk)


# The content hash


def hash_of(
    handbook: Handbook,
    *,
    model: str = "voyage-4",
    dimensions: int = 1024,
    vectors: list[list[float]] | None = None,
) -> str:
    return content_hash(
        handbook,
        model=model,
        dimensions=dimensions,
        vectors=[[1.0, 0.0], [0.0, 1.0]] if vectors is None else vectors,
    )


def test_the_hash_changes_when_one_vector_changes(handbook: Handbook) -> None:
    base = hash_of(handbook)

    assert hash_of(handbook, vectors=[[1.0, 0.0], [0.0, 0.5]]) != base
    assert hash_of(handbook, vectors=[[1.0, 0.0]]) != base


def test_the_hash_depends_on_the_order_of_the_vectors(handbook: Handbook) -> None:
    assert hash_of(handbook, vectors=[[0.0, 1.0], [1.0, 0.0]]) != hash_of(handbook)


def test_the_hash_is_a_sha256_hex_digest_and_stable(handbook: Handbook) -> None:
    digest = hash_of(handbook)

    assert len(digest) == 64
    int(digest, 16)
    assert hash_of(handbook) == digest


def test_the_hash_changes_when_a_section_file_changes(handbook: Handbook) -> None:
    files = list(handbook.files)
    files[2] = dataclasses.replace(files[2], text=files[2].text + "\n")

    assert hash_of(dataclasses.replace(handbook, files=tuple(files))) != hash_of(handbook)


def test_the_hash_changes_when_the_config_changes(handbook: Handbook) -> None:
    files = list(handbook.files)
    files[0] = dataclasses.replace(files[0], text=files[0].text + "# edit\n")

    assert hash_of(dataclasses.replace(handbook, files=tuple(files))) != hash_of(handbook)


def test_the_hash_changes_when_a_file_is_renamed(handbook: Handbook) -> None:
    files = list(handbook.files)
    files[1] = dataclasses.replace(files[1], path="sections/1.1-renamed.md")

    assert hash_of(dataclasses.replace(handbook, files=tuple(files))) != hash_of(handbook)


def test_the_hash_changes_with_the_model_and_the_dimensions(handbook: Handbook) -> None:
    base = hash_of(handbook)

    assert hash_of(handbook, model="voyage-4-lite") != base
    assert hash_of(handbook, dimensions=512) != base


def test_the_hash_changes_with_the_chunker_version(
    handbook: Handbook, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = hash_of(handbook)

    monkeypatch.setattr(hashing, "CHUNKER_VERSION", CHUNKER_VERSION + 1)

    assert hash_of(handbook) != base


def test_the_hash_ignores_the_order_the_files_were_read_in(handbook: Handbook) -> None:
    shuffled = dataclasses.replace(handbook, files=tuple(reversed(handbook.files)))

    assert hash_of(shuffled) == hash_of(handbook)


def test_moving_text_between_a_path_and_its_content_changes_the_hash(handbook: Handbook) -> None:
    a, b = handbook.files[1], handbook.files[2]
    swapped = (
        dataclasses.replace(a, text=b.text),
        dataclasses.replace(b, text=a.text),
    )
    files = (handbook.files[0], *swapped, *handbook.files[3:])

    assert hash_of(dataclasses.replace(handbook, files=files)) != hash_of(handbook)


def test_the_hash_changes_when_the_parsed_blocks_change_but_the_source_does_not(
    handbook: Handbook, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = hash_of(handbook)
    real = blocks_to_json

    def renumbered(blocks: Any) -> Any:
        return [*real(blocks), {"type": "extra"}]

    monkeypatch.setattr("app.domain.handbook.hashing.blocks_to_json", renumbered)

    assert hash_of(handbook) != base


def test_the_hash_changes_when_the_chunks_change_but_the_source_does_not(
    handbook: Handbook, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = hash_of(handbook)
    real = chunks_for

    def split_differently(section: Section) -> list[Chunk]:
        return [dataclasses.replace(c, passage_ids=(*c.passage_ids, "x")) for c in real(section)]

    monkeypatch.setattr("app.domain.handbook.hashing.chunks_for", split_differently)

    assert hash_of(handbook) != base


def test_the_same_files_in_a_different_order_give_the_same_hash(handbook: Handbook) -> None:
    shuffled = dataclasses.replace(handbook, files=tuple(reversed(handbook.files)))

    assert hash_of(shuffled) == hash_of(handbook)
