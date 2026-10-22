"""One way to build the permission rules' view of a request, from a stored request or a page row."""

from datetime import date
from uuid import uuid4

from app.modules.timeoff import queries, service
from app.policy import TimeOffRequestResource


def test_a_stored_request_and_a_page_row_become_the_same_resource() -> None:
    person = uuid4()
    stored = queries.StoredRequest(
        uuid4(), person, "pto", "pending", date(2026, 11, 9), date(2026, 11, 10)
    )

    assert service.request_resource(stored) == TimeOffRequestResource(
        person, "pto", "pending", date(2026, 11, 9)
    )
