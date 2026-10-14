"""Handbook validation: every rule, each with the file and line it reports.

The fixture handbook under tests/fixtures/handbook is valid. Each test breaks it in one way by
replacing a piece of one file's text, so the line numbers below are lines of that file.
"""

from pathlib import Path

import pytest

from app.domain.handbook.blocks import Inline, Passage
from app.domain.handbook.errors import HandbookError, HandbookInvalid
from app.domain.handbook.models import Handbook
from app.domain.handbook.validate import load_handbook
from app.modules.handbook.source import parse_config, parse_section, read_handbook

FIXTURE = Path(__file__).parent / "fixtures" / "handbook"
COMPANY = "sections/4.3-sick-leave.md"
ADDENDUM = "addenda/ca/CA-4.3-sick-leave.md"
INTRO = "sections/1.1-about.md"
# Line 7 of COMPANY, the first line of its body.
FIRST_BODY_LINE = 7
FIRST_BODY_TEXT = "Everyone gets sick leave."


def fixture_texts() -> dict[str, str]:
    return {
        path.relative_to(FIXTURE).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(FIXTURE.rglob("*"))
        if path.is_file()
    }


def build(texts: dict[str, str]) -> Handbook:
    config = parse_config("handbook.yaml", texts["handbook.yaml"])
    files = [parse_section(p, t) for p, t in texts.items() if p != "handbook.yaml"]
    return load_handbook(config, files)


def errors_of(texts: dict[str, str]) -> list[HandbookError]:
    with pytest.raises(HandbookInvalid) as raised:
        build(texts)
    return raised.value.errors


def body_edit(old_text: str, new_text: str, path: str = COMPANY) -> dict[str, str]:
    """The fixture with `old_text` replaced by `new_text` in one file."""
    texts = fixture_texts()
    assert old_text in texts[path], f"{old_text!r} isn't in {path}"
    texts[path] = texts[path].replace(old_text, new_text)
    return texts


def only_error(texts: dict[str, str]) -> HandbookError:
    errors = errors_of(texts)
    assert len(errors) == 1, errors
    return errors[0]


def test_a_valid_handbook_loads() -> None:
    handbook = build(fixture_texts())

    assert handbook.version == "2026.10"
    assert [section.id for section in handbook.sections] == ["1.1", "4.3", "CA-4.3"]
    ca = handbook.sections[2]
    assert ca.kind == "addendum"
    assert ca.addendum_state == "CA"
    assert ca.supplements == "4.3"
    assert ca.group_name == "California addendum"
    assert ca.audience.states == ("CA",)
    assert handbook.sections[1].chapter == 4
    assert handbook.sections[1].group_name == "Time off"


def test_read_handbook_loads_the_fixture_from_disk() -> None:
    assert len(read_handbook(FIXTURE).sections) == 3


# Front matter


def test_a_missing_field_is_reported_at_the_top_of_the_file() -> None:
    error = only_error(body_edit("title: Sick leave\n", ""))

    assert (error.path, error.line) == (COMPANY, 1)
    assert "missing front matter field `title`" in error.message


def test_an_unknown_field_is_reported_at_its_line() -> None:
    error = only_error(body_edit("updated: 2026-10-07\n", "updated: 2026-10-07\nauthor: Dana\n"))

    assert (error.path, error.line) == (COMPANY, 5)
    assert "unknown front matter field `author`" in error.message


def test_a_bad_date_is_reported_at_its_line() -> None:
    error = only_error(body_edit("updated: 2026-10-07", "updated: 2026-13-45"))

    assert (error.path, error.line) == (COMPANY, 4)
    assert "`updated` must be a date" in error.message


def test_a_date_with_a_time_is_refused() -> None:
    error = only_error(body_edit("updated: 2026-10-07", "updated: 2026-10-07 09:30:00"))

    assert (error.path, error.line) == (COMPANY, 4)


def test_an_unquoted_id_is_refused_because_yaml_makes_it_a_number() -> None:
    error = only_error(body_edit('id: "1.1"', "id: 1.1", INTRO))

    assert (error.path, error.line) == (INTRO, 2)
    assert "quoted string" in error.message


def test_an_unknown_state_is_reported_at_its_list() -> None:
    error = only_error(body_edit("states: [CA]", "states: [CA, NY]", ADDENDUM))

    assert (error.path, error.line) == (ADDENDUM, 6)
    assert "unknown state 'NY'" in error.message


def test_an_unknown_employment_type_is_reported() -> None:
    texts = body_edit(
        "updated: 2026-10-07\n", "updated: 2026-10-07\napplies_to:\n  employment_types: [temp]\n"
    )
    error = only_error(texts)

    assert (error.path, error.line) == (COMPANY, 6)
    assert "unknown employment type 'temp'" in error.message


def test_an_unknown_location_code_is_reported() -> None:
    texts = body_edit(
        "updated: 2026-10-07\n", "updated: 2026-10-07\napplies_to:\n  locations: [nyc]\n"
    )
    error = only_error(texts)

    assert (error.path, error.line) == (COMPANY, 6)
    assert "unknown location 'nyc'" in error.message


def test_an_unknown_applies_to_key_is_reported() -> None:
    error = only_error(body_edit("states: [CA]", "states: [CA]\n  teams: [x]", ADDENDUM))

    assert (error.path, error.line) == (ADDENDUM, 5)
    assert "unknown `applies_to` field `teams`" in error.message


def test_an_id_that_does_not_match_the_file_name_is_reported() -> None:
    error = only_error(body_edit('id: "1.1"', 'id: "1.2"', INTRO))

    assert (error.path, error.line) == (INTRO, 2)
    assert "doesn't match the file name" in error.message


def test_a_chapter_missing_from_the_config_is_reported() -> None:
    texts = body_edit("  4: Time off\n", "", "handbook.yaml")
    error = only_error(texts)

    assert (error.path, error.line) == (COMPANY, 2)
    assert "chapter 4" in error.message


def test_an_addendum_in_the_wrong_folder_is_reported() -> None:
    texts = fixture_texts()
    texts["addenda/tx/CA-4.3-sick-leave.md"] = texts.pop(ADDENDUM)
    error = only_error(texts)

    assert error.path == "addenda/tx/CA-4.3-sick-leave.md"
    assert error.line == 2
    assert "doesn't belong in the folder addenda/tx/" in error.message


def test_an_addendum_must_apply_to_its_own_state() -> None:
    error = only_error(body_edit("states: [CA]", "states: [TX]", ADDENDUM))

    assert (error.path, error.line) == (ADDENDUM, 6)
    assert "must be [CA]" in error.message


def test_an_addendum_without_applies_to_is_reported() -> None:
    texts = body_edit("applies_to:\n  states: [CA]\n", "", ADDENDUM)
    error = only_error(texts)

    assert (error.path, error.line) == (ADDENDUM, 2)
    assert "an addendum applies to its own state" in error.message
    assert "must be [CA]" in error.message


def test_a_company_section_may_omit_applies_to() -> None:
    assert "applies_to" not in fixture_texts()[COMPANY]
    assert build(fixture_texts()).sections


def test_an_addendum_without_supplements_is_reported() -> None:
    error = only_error(body_edit('supplements: "4.3"\n', "", ADDENDUM))

    assert (error.path, error.line) == (ADDENDUM, 2)
    assert "needs `supplements`" in error.message


def test_a_company_section_with_supplements_is_reported() -> None:
    error = only_error(
        body_edit("updated: 2026-10-07\n", 'updated: 2026-10-07\nsupplements: "1.1"\n')
    )

    assert (error.path, error.line) == (COMPANY, 5)
    assert "only an addendum" in error.message


def test_supplements_naming_a_missing_section_is_reported() -> None:
    error = only_error(body_edit('supplements: "4.3"', 'supplements: "4.9"', ADDENDUM))

    assert (error.path, error.line) == (ADDENDUM, 7)
    assert "isn't a section" in error.message


def test_supplements_naming_an_addendum_is_reported() -> None:
    texts = fixture_texts()
    texts["addenda/ca/CA-5.1-leave.md"] = (
        texts[ADDENDUM].replace("CA-4.3", "CA-5.1").replace('"4.3"', '"CA-4.3"')
    )
    errors = errors_of(texts)

    assert len(errors) == 1
    assert (errors[0].path, errors[0].line) == ("addenda/ca/CA-5.1-leave.md", 7)
    assert "isn't a company section" in errors[0].message


def test_supplements_must_be_a_string() -> None:
    error = only_error(body_edit('supplements: "4.3"', "supplements: 4.3", ADDENDUM))

    assert (error.path, error.line) == (ADDENDUM, 7)
    assert "quoted string" in error.message


def test_a_duplicate_id_is_reported_in_the_second_file() -> None:
    texts = fixture_texts()
    texts["sections/4.3-other.md"] = texts[COMPANY]
    error = only_error(texts)

    assert (error.path, error.line) == ("sections/4.3-other.md", 2)
    assert "duplicate ID '4.3'" in error.message
    assert COMPANY in error.message


# The markdown subset


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("<div>raw</div>", "raw HTML"),
        ("Some <b>inline</b> html", "raw HTML"),
        ("An image ![alt](https://example.com/a.png) here", "images"),
        ("| a | b |\n| - | - |\n| 1 | 2 |", "tables"),
        ("```\ncode\n```", "code blocks"),
        ("    indented code", "code blocks"),
        ("Some `inline code` here", "inline code"),
        ("> a quote", "quotes"),
        ("# A title", "`#` heading"),
        ("#### Too deep", "`####` heading"),
        ("A [link](https://example.com) here", "links must look like"),
        ("A [link](/relative) here", "links must look like"),
        ("A <https://example.com> autolink", "links must look like"),
        ("Some ~~struck~~ text", "strikethrough"),
        ("---", "horizontal rules"),
    ],
)
def test_markdown_outside_the_subset_is_refused_with_its_line(markdown: str, expected: str) -> None:
    error = only_error(body_edit(FIRST_BODY_TEXT, markdown))

    assert (error.path, error.line) == (COMPANY, FIRST_BODY_LINE)
    assert expected in error.message


@pytest.mark.parametrize(
    ("markdown", "message"),
    [
        ("line one  \nline two", "forced line breaks aren't allowed"),
        ("line one\\\nline two", "forced line breaks aren't allowed"),
        ("- <b>bold</b> item\n- fine", "raw HTML isn't allowed"),
        (
            "A [reference][r] link.\n\n[r]: https://example.com",
            "link to 'https://example.com' isn't allowed: links must look like `handbook:4.3`",
        ),
        (
            "A [link](HANDBOOK:4.3) here",
            "link to 'HANDBOOK:4.3' isn't allowed: links must look like `handbook:4.3`",
        ),
        (
            "A [link](handbook:) here",
            "link to 'handbook:' isn't allowed: links must look like `handbook:4.3`",
        ),
    ],
)
def test_more_markdown_outside_the_subset_is_refused_with_its_message(
    markdown: str, message: str
) -> None:
    error = only_error(body_edit(FIRST_BODY_TEXT, markdown))

    assert (error.path, error.line, error.message) == (COMPANY, FIRST_BODY_LINE, message)


def test_an_empty_list_item_is_refused_at_its_line() -> None:
    error = only_error(body_edit(FIRST_BODY_TEXT, "-\n- b"))

    assert (error.path, error.line) == (COMPANY, FIRST_BODY_LINE)
    assert error.message == "a list item can't be empty"


def test_a_link_in_a_heading_is_refused_at_the_heading_line() -> None:
    error = only_error(body_edit("## Welcome", "## Welcome [x](handbook:4.3)", INTRO))

    assert (error.path, error.line) == (INTRO, 9)
    assert error.message == "links aren't allowed in headings"


def test_a_link_around_bold_text_has_no_empty_runs() -> None:
    texts = body_edit(FIRST_BODY_TEXT, "[**x**](handbook:4.3) and after")
    section = build(texts).sections[1]

    assert section.blocks[0] == Passage(
        "p1",
        "paragraph",
        inlines=(Inline("x", bold=True, link_section_id="4.3"), Inline(" and after")),
    )


@pytest.mark.parametrize("path", [COMPANY, INTRO])
def test_a_section_with_no_paragraph_or_list_is_refused(path: str) -> None:
    texts = fixture_texts()
    front_matter = texts[path].split("\n---\n", 1)[0] + "\n---\n"
    offset = front_matter.count("\n")
    for body in ("", "\n## Only a heading\n\n### And another\n"):
        texts[path] = front_matter + body
        errors = [e for e in errors_of(texts) if e.path == path]
        assert [(e.line, e.message) for e in errors] == [
            (offset + 1, "a section needs at least one paragraph or list")
        ]


def test_a_nested_list_is_refused_at_the_nested_line() -> None:
    error = only_error(body_edit(FIRST_BODY_TEXT, "- one\n  - nested"))

    assert (error.path, error.line) == (COMPANY, FIRST_BODY_LINE + 1)
    assert "nested lists" in error.message


def test_a_markdown_error_deeper_in_the_file_reports_that_line() -> None:
    # "- Front-loaded on January 1" is line 12 of the fixture.
    error = only_error(body_edit("- Front-loaded on January 1", "- A [link](https://x.example)"))

    assert (error.path, error.line) == (COMPANY, 12)


def test_a_handbook_link_to_a_missing_section_is_reported() -> None:
    error = only_error(body_edit("[§4.3 Sick leave](handbook:4.3)", "[x](handbook:9.9)", INTRO))

    assert error.path == INTRO
    assert "no such section" in error.message
    assert "'9.9'" in error.message


def test_a_handbook_link_to_a_real_section_is_kept_in_the_blocks() -> None:
    handbook = build(fixture_texts())
    paragraph = handbook.sections[0].blocks[1]

    assert isinstance(paragraph, Passage)
    assert ("§4.3 Sick leave", "4.3") in [
        (run.text, run.link_section_id) for run in paragraph.inlines
    ]


# Several at once, and the YAML layer


def test_every_error_is_reported_together() -> None:
    texts = fixture_texts()
    texts[COMPANY] = (
        texts[COMPANY]
        .replace("updated: 2026-10-07", "updated: soon")
        .replace(FIRST_BODY_TEXT, "<div>raw</div>")
    )
    texts[ADDENDUM] = texts[ADDENDUM].replace("states: [CA]", "states: [NY]")

    found = {(e.path, e.line) for e in errors_of(texts)}

    assert found == {(COMPANY, 4), (COMPANY, 7), (ADDENDUM, 6)}


def test_errors_come_in_file_and_line_order() -> None:
    texts = body_edit("title: Sick leave\n", "")
    texts[COMPANY] = texts[COMPANY].replace(FIRST_BODY_TEXT, "<div>raw</div>")

    errors = errors_of(texts)

    assert errors == sorted(errors, key=lambda e: (e.path, e.line, e.message))
    assert [e.line for e in errors] == [1, 6]


def test_a_yaml_syntax_error_reports_its_file_and_line() -> None:
    texts = fixture_texts()
    broken = texts[COMPANY].replace("title: Sick leave", "title: [unclosed")

    with pytest.raises(HandbookInvalid) as raised:
        parse_section(COMPANY, broken)

    (error,) = raised.value.errors
    assert error.path == COMPANY
    assert 3 <= error.line <= 5
    assert "YAML" in error.message


def test_a_file_without_front_matter_is_reported_at_line_one() -> None:
    with pytest.raises(HandbookInvalid) as raised:
        parse_section(COMPANY, "Just some text\n")

    assert raised.value.errors == [
        HandbookError(COMPANY, 1, "the file must start with `---` and YAML front matter")
    ]


def test_front_matter_that_never_closes_is_reported() -> None:
    with pytest.raises(HandbookInvalid) as raised:
        parse_section(COMPANY, '---\nid: "4.3"\n')

    assert raised.value.errors[0].line == 1
    assert "never closed" in raised.value.errors[0].message


def test_read_handbook_reports_yaml_errors_alone(tmp_path: Path) -> None:
    for path, text in fixture_texts().items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (tmp_path / COMPANY).write_text("---\nid: [oops\n---\n", encoding="utf-8")
    (tmp_path / INTRO).write_text("no front matter\n", encoding="utf-8")

    with pytest.raises(HandbookInvalid) as raised:
        read_handbook(tmp_path)

    paths = {error.path for error in raised.value.errors}
    assert paths == {COMPANY, INTRO}


# handbook.yaml


def test_a_config_without_a_version_is_reported() -> None:
    error = only_error(body_edit('version: "2026.10"\n', "", "handbook.yaml"))

    assert error.path == "handbook.yaml"
    assert "`version`" in error.message


def test_a_chapter_key_that_is_not_a_number_is_reported() -> None:
    error = only_error(body_edit("  4: Time off", "  4: Time off\n  four: Extra", "handbook.yaml"))

    assert error.path == "handbook.yaml"
    assert error.line == 6
