"""The base for every request and response body: snake_case in Python, camelCase in JSON."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """`given_name` in Python is `givenName` in JSON, both ways. FastAPI serializes by alias."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
        frozen=True,
    )
