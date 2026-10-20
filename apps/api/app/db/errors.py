"""Reading the database's own refusals."""

from sqlalchemy.exc import DBAPIError


def has_sqlstate(error: DBAPIError, code: str) -> bool:
    """Whether the driver's error carries this SQLSTATE.

    For the custom codes our triggers raise (class OD is ours: OD001 for a new sandbox with no
    published handbook, OD002 for a change to a finished turn). They are not integrity errors, so
    SQLAlchemy wraps them as a plain DBAPIError, and the code is the one reliable thing to match.
    """
    return getattr(error.orig, "sqlstate", None) == code


def constraint_name(error: DBAPIError) -> str | None:
    """The name of the constraint a violation broke, from the driver's own error.

    SQLAlchemy's adapter is `error.orig`, and asyncpg's own error, which carries the name, is its
    cause.
    """
    cause = error.orig.__cause__ if error.orig is not None else None
    name = getattr(cause, "constraint_name", None)
    return name if isinstance(name, str) else None
