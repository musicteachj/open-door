"""An HR contact has one shape: the stream's `escalation` event and the conversation read agree.

The event is built by `HrContact.to_json` and the read by `hr_contact_out`, so the fields can't
drift apart: the second is made from the first.
"""

from app.ai.fixed_texts import HrContact
from app.api.contacts import HrContactOut, hr_contact_out

DANA = HrContact(
    name="Dana Whitfield",
    work_email="dana.whitfield@juniperrow.example",
    job_title="HR Business Partner",
    location_name="Denver HQ",
)
NO_DETAILS = HrContact(
    name="Sam Lee", work_email="sam@juniperrow.example", job_title=None, location_name=None
)


def test_the_read_and_the_event_have_the_same_keys_and_values() -> None:
    for contact in (DANA, NO_DETAILS):
        (out,) = hr_contact_out([contact])

        assert out.model_dump(by_alias=True) == contact.to_json()


def test_every_field_of_the_read_is_in_the_event() -> None:
    event_keys = set(DANA.to_json())
    read_keys = {field.alias or name for name, field in HrContactOut.model_fields.items()}

    assert event_keys == read_keys
