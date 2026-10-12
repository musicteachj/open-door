"""What validation reports: every problem at once, each with the file and line."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HandbookError:
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


class HandbookInvalid(Exception):  # noqa: N818 (the name the plan and callers use)
    """The handbook's sources break a rule. `errors` lists every break, in file and line order."""

    def __init__(self, errors: list[HandbookError]) -> None:
        self.errors = sorted(errors, key=lambda error: (error.path, error.line, error.message))
        count = len(self.errors)
        lines = "\n".join(f"  {error}" for error in self.errors)
        super().__init__(f"The handbook has {count} error{'s' if count != 1 else ''}:\n{lines}")
