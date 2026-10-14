"""The search excerpt (phase review). A result shows its excerpt on one line, so the first match
has to sit near the start, and it has to arrive whole."""

from app.modules.handbook.routes import MATCH_START, MATCH_STOP, _excerpt
from app.modules.handbook.schemas import Segment


def marked(before: str, match: str, after: str) -> str:
    return f"{before}{MATCH_START}{match}{MATCH_STOP}{after}"


def visible(segments: list[Segment]) -> str:
    return "".join(segment.text for segment in segments)


def matches(segments: list[Segment]) -> list[str]:
    return [segment.text for segment in segments if segment.match]


def test_a_match_early_in_its_sentence_keeps_the_sentence_start() -> None:
    segments = _excerpt(marked("Every employee may take ", "sick", " leave."))

    assert visible(segments) == "Every employee may take sick leave."


def test_a_match_past_the_first_line_starts_a_few_words_before_it() -> None:
    # About 116 characters in: the match would end past what one line shows at 1440 px.
    before = "Your manager approves each request " + "within the posted schedule " * 3
    segments = _excerpt(marked(before, "painted", " today."))

    text = visible(segments)
    assert segments[0].text == "…"
    assert matches(segments) == ["painted"]
    assert text.index("painted") <= 40
    assert text[1:].startswith("within the posted schedule painted")  # on a word boundary


def test_a_match_with_no_space_before_it_arrives_whole() -> None:
    before = "See the source at " + "x" * 120
    segments = _excerpt(marked(before, "statute", " for the details."))

    assert segments[0].text == "…"
    assert matches(segments) == ["statute"]
    assert visible(segments)[1:].startswith("statute")


def test_a_match_with_no_space_anywhere_after_the_lead_is_not_cut() -> None:
    before = "Read " + "y" * 120
    segments = _excerpt(marked(before, "zz", ""))

    assert matches(segments) == ["zz"]
    assert visible(segments) == "…zz"
