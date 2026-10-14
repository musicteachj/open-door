"""The real handbook, checked without a database or a network.

These keep the handbook honest against the rest of the build: it validates, it names the same
holidays the company calendar closes on, and every chunk has its embedding in the committed cache.
The location codes and states are checked against the seed in test_handbook_applicability.py.
"""

from pathlib import Path

import pytest

from app.ai.embeddings import DIMENSIONS, MODEL, EmbeddingCache
from app.domain.handbook.chunks import chunks_for
from app.domain.handbook.models import Handbook
from app.domain.holidays import LOCATION_CODES, holidays_for
from app.modules.handbook.source import read_handbook

HANDBOOK_DIR = Path(__file__).parents[3] / "handbook"
CACHE_PATH = HANDBOOK_DIR / "embeddings" / f"{MODEL}-{DIMENSIONS}.jsonl"
OBSERVED = " (observed)"


@pytest.fixture(scope="module")
def handbook() -> Handbook:
    return read_handbook(HANDBOOK_DIR)


@pytest.fixture(scope="module")
def holidays_section() -> str:
    (path,) = (HANDBOOK_DIR / "sections").glob("4.2-*.md")
    return path.read_text(encoding="utf-8")


def test_the_real_handbook_validates(handbook: Handbook) -> None:
    assert handbook.sections


@pytest.mark.parametrize("location_code", sorted(LOCATION_CODES))
def test_section_4_2_names_every_holiday_the_calendar_gives_each_location(
    location_code: str, holidays_section: str
) -> None:
    text = holidays_section.lower()
    # The calendar's "(observed)" suffix is how the date moved, not part of the holiday's name.
    names = {
        holiday.name.removesuffix(OBSERVED)
        for year in (2026, 2027, 2028, 2029)
        for holiday in holidays_for(location_code, year)
    }

    missing = sorted(name for name in names if name.lower() not in text)

    assert not missing, f"Section 4.2 doesn't mention {missing} for {location_code}"


def denver_only_claims(text: str) -> list[str]:
    """What section 4.2's text fails to say about the day after Thanksgiving."""
    missing = []
    if "Denver HQ also closes the day after Thanksgiving" not in text:
        missing.append("Denver HQ closes the day after Thanksgiving")
    if (
        "The Oakland store, the Austin warehouse, and the Atlanta store do not close that day"
        not in text
    ):
        missing.append("Oakland, Austin, and Atlanta do not close that day")
    return missing


def test_section_4_2_says_only_denver_hq_closes_the_day_after_thanksgiving(
    holidays_section: str,
) -> None:
    assert denver_only_claims(holidays_section) == []


def test_the_denver_only_check_fails_when_the_locations_are_swapped(
    holidays_section: str,
) -> None:
    swapped = holidays_section.replace("Denver HQ also closes", "The Oakland store also closes")

    assert denver_only_claims(swapped) == ["Denver HQ closes the day after Thanksgiving"]


def test_every_chunk_of_the_real_handbook_has_its_embedding_in_the_committed_cache(
    handbook: Handbook,
) -> None:
    cache = EmbeddingCache.load(CACHE_PATH)
    texts = [chunk.embed_text for section in handbook.sections for chunk in chunks_for(section)]

    missing = [text for text in texts if cache.get("document", text) is None]

    assert not missing, (
        f"{len(missing)} of {len(texts)} chunks have no embedding in {CACHE_PATH.name}: "
        "run `make embed` and commit the cache. First without one: " + repr(missing[0][:80])
    )
