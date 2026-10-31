"""The HR contacts as the API shows them. Apart from the base schema module so that one, which
every schema imports, does not pull in the AI package."""

from collections.abc import Sequence

from app.ai.fixed_texts import HrContact
from app.api.schemas import CamelModel


class HrContactOut(CamelModel):
    name: str
    work_email: str
    job_title: str | None
    location_name: str | None


def hr_contact_out(contacts: Sequence[HrContact]) -> list[HrContactOut]:
    """The contacts as the conversation read shows them, built from the event's own form
    (`HrContact.to_json`), so the two can't drift apart."""
    return [HrContactOut.model_validate(c.to_json()) for c in contacts]
