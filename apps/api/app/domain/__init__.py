"""Pure domain logic. Nothing under this package may import a framework.

import-linter enforces the rule (see `[tool.importlinter]` in pyproject.toml), so the time-off
engine and anything like it stays testable with plain values and runs anywhere.
"""
