from sqlalchemy import Column, Integer, MetaData, String, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.base import NAMING_CONVENTION


def test_composite_constraints_are_named_by_all_their_columns() -> None:
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    table = Table(
        "leave_requests",
        metadata,
        Column("employee_id", Integer),
        Column("year", Integer),
        Column("kind", String),
        UniqueConstraint("employee_id", "year"),
        UniqueConstraint("employee_id", "kind"),
    )

    # SQLAlchemy's stubs leave the dialect constructors untyped.
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    ddl = str(CreateTable(table).compile(dialect=dialect))

    assert "uq_leave_requests_employee_id_year" in ddl
    assert "uq_leave_requests_employee_id_kind" in ddl
