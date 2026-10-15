"""Telling one of our own database refusals from another by its SQLSTATE."""

from sqlalchemy.exc import DBAPIError

from app.db.errors import constraint_name, has_sqlstate


class DriverError(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        super().__init__("driver error")
        self.sqlstate = sqlstate


def refusal(sqlstate: str | None) -> DBAPIError:
    return DBAPIError("SELECT 1", None, DriverError(sqlstate))


def test_a_matching_code_is_recognized() -> None:
    assert has_sqlstate(refusal("OD002"), "OD002")


def test_another_code_is_not() -> None:
    assert not has_sqlstate(refusal("OD001"), "OD002")
    assert not has_sqlstate(refusal("23505"), "OD002")


def test_an_error_without_a_code_is_not() -> None:
    assert not has_sqlstate(refusal(None), "OD002")
    assert not has_sqlstate(DBAPIError("SELECT 1", None, Exception("plain")), "OD002")


class AsyncpgViolationError(Exception):
    """Stands in for asyncpg's error, which carries the constraint's name."""

    constraint_name = "uq_ai_turns_one_running_per_conversation"


def wrapped_violation() -> DBAPIError:
    # SQLAlchemy's adapter is the `orig`, and asyncpg's own error is its cause.
    adapter = Exception("adapter")
    adapter.__cause__ = AsyncpgViolationError()
    return DBAPIError("INSERT", None, adapter)


def test_the_name_of_the_broken_constraint_is_read_from_the_drivers_error() -> None:
    assert constraint_name(wrapped_violation()) == "uq_ai_turns_one_running_per_conversation"


def test_an_error_without_a_constraint_has_no_name() -> None:
    assert constraint_name(DBAPIError("INSERT", None, Exception("no cause"))) is None
