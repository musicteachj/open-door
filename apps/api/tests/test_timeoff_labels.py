"""The amount labels. Every expected string was worked out by hand.

Hours always; days in parentheses only from a full day up, in whole quarter days (a multiple of
120 minutes), so 600 minutes is 10 hours, 600 / 480 = 1.25 days.
"""

import pytest

from app.domain.timeoff.labels import label


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (480, "8 hours (1 day)"),  # 480 / 480 = 1
        (600, "10 hours (1.25 days)"),  # 600 / 480 = 1.25
        (720, "12 hours (1.5 days)"),  # 720 / 480 = 1.5
        (840, "14 hours (1.75 days)"),  # 840 / 480 = 1.75
        (960, "16 hours (2 days)"),  # 960 / 480 = 2
        (5400, "90 hours (11.25 days)"),  # 5400 / 60 = 90 hours; 5400 / 480 = 11.25
        (10800, "180 hours (22.5 days)"),  # the salaried ceiling: 10800 / 480 = 22.5
        (8640, "144 hours (18 days)"),  # the hourly ceiling: 8640 / 480 = 18
        (240, "4 hours (half a day)"),
        (180, "3 hours"),
        (120, "2 hours"),
        (300, "5 hours"),
        (360, "6 hours"),
        (60, "1 hour"),
        (0, "0 hours"),
        (540, "9 hours"),  # 540 is not a multiple of 120, so no days
        (90, "1 hour 30 minutes"),
        (121, "2 hours 1 minute"),
        (45, "45 minutes"),
        (1, "1 minute"),
        (-480, "-8 hours (-1 day)"),
        (-180, "-3 hours"),
        (-240, "-4 hours"),  # only +240 is "half a day"
        (-45, "-45 minutes"),
    ],
)
def test_label(minutes: int, expected: str) -> None:
    assert label(minutes) == expected
