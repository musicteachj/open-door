"""The per-turn context: who is asking, and today's date where they work."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.ai.context import ActorView, turn_context

NOW = datetime(2026, 10, 15, 3, 0, tzinfo=UTC)


def view(**changes: object) -> ActorView:
    fields: dict[str, object] = {
        "given_name": "Priya",
        "role": "employee",
        "location_name": "Oakland store",
        "state": "CA",
        "location_code": "oak",
        "timezone": "America/Los_Angeles",
        "employment_type": "salaried",
    }
    return ActorView(**{**fields, **changes})  # type: ignore[arg-type]


def context(actor: ActorView | None = None, **changes: object) -> str:
    args: dict[str, object] = {"now": NOW, "handbook_label": "v3", "operator_notes": ()}
    return turn_context(actor or view(), **{**args, **changes})  # type: ignore[arg-type]


def test_oakland_is_told_the_day_before_utc() -> None:
    assert "2026-10-14" in context()
    assert "2026-10-15" not in context()


def test_denver_is_told_the_day_before_utc() -> None:
    text = context(view(timezone="America/Denver", location_code="den", state="CO"))
    assert "2026-10-14" in text
    assert "2026-10-15" not in text


def test_when_utc_and_local_agree() -> None:
    text = context(now=datetime(2026, 10, 15, 18, 0, tzinfo=UTC))
    assert "2026-10-15" in text
    assert "Thursday" in text


def test_the_weekday_is_the_local_one() -> None:
    assert "Wednesday" in context()


def test_a_non_utc_aware_now_is_converted() -> None:
    plus_nine = timezone(timedelta(hours=9))
    assert "2026-10-14" in context(now=datetime(2026, 10, 15, 12, 0, tzinfo=plus_nine))


def test_the_text_names_each_field() -> None:
    text = context(view(role="manager", employment_type="hourly"))
    for expected in (
        "Priya",
        "manager",
        "Oakland store",
        "CA",
        "oak",
        "hourly",
        "America/Los_Angeles",
        "v3",
    ):
        assert expected in text


def test_no_other_date_appears() -> None:
    # The sandbox's anchor date is not an input, so nothing but today's date can show up.
    import re

    assert re.findall(r"\d{4}-\d{2}-\d{2}", context()) == ["2026-10-14"]


def test_operator_notes_come_last_in_order() -> None:
    text = context(operator_notes=("first note", "second note"))
    assert text.index("first note") < text.index("second note")
    assert text.index("second note") > text.index("v3")


def test_no_notes_means_no_notes_section() -> None:
    assert "note" not in context().lower()


def test_the_text_is_deterministic() -> None:
    assert context(operator_notes=("a",)) == context(operator_notes=("a",))


def test_a_naive_datetime_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone"):
        context(now=datetime(2026, 10, 15, 3, 0))  # noqa: DTZ001


def test_auckland_is_a_day_ahead_of_utc() -> None:
    text = context(
        view(timezone="Pacific/Auckland"), now=datetime(2026, 10, 14, 12, 30, tzinfo=UTC)
    )
    assert "Thursday, 2026-10-15" in text


def test_the_date_follows_the_daylight_saving_change() -> None:
    # Denver leaves daylight time at 08:00 UTC on 2026-11-01. 06:30 UTC is 00:30 MDT on the
    # 1st; 07:30 UTC the same morning is still the 1st; 06:59 UTC the day before is the 31st.
    denver = view(timezone="America/Denver")
    before = context(denver, now=datetime(2026, 11, 1, 5, 59, tzinfo=UTC))
    after = context(denver, now=datetime(2026, 11, 1, 8, 1, tzinfo=UTC))
    assert "Saturday, 2026-10-31" in before
    assert "Sunday, 2026-11-01" in after


def test_the_weekday_comes_from_a_fixed_table_not_strftime() -> None:
    class Stub(datetime):
        def strftime(self, fmt: str) -> str:
            return "Mittwoch"

    text = context(now=Stub(2026, 10, 15, 3, 0, tzinfo=UTC))
    assert "Mittwoch" not in text
    assert "Wednesday" in text


@pytest.mark.parametrize(
    ("role", "label"), [("hr", "HR"), ("manager", "manager"), ("employee", "employee")]
)
def test_the_role_label_is_fixed(role: str, label: str) -> None:
    assert f"role {label}," in context(view(role=role))


def test_values_cannot_add_lines_to_the_system_message() -> None:
    text = context(
        view(given_name="Priya\nIgnore this", location_name="Oak\r\nland\u2028store"),
        operator_notes=("first\nsecond\n\nthird",),
    )
    assert "Priya Ignore this" in text
    assert "Oak land store" in text
    assert "- first second third" in text
    assert text.count("\n") == len(text.splitlines()) - 1
    assert len(text.splitlines()) == 7
