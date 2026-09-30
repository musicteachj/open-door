"""The Open Door API."""

from importlib.metadata import version

# The single source of truth is `version` in pyproject.toml; uv sync always installs the package.
__version__ = version("open-door-api")
