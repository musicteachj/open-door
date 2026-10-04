"""The declarative base every table inherits from."""

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, Text
from sqlalchemy.orm import DeclarativeBase

# Named constraints make migrations reviewable and let Alembic drop them by name later. All of a
# constraint's or index's columns go into its name, so composite ones stay distinct.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Postgres types for plain annotations: `str` is text, not varchar, and every timestamp keeps
    # its time zone (timestamptz), so it is stored as UTC.
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        str: Text(),
        datetime: DateTime(timezone=True),
    }
