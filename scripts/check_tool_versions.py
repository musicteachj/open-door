"""Fail when a tool's version differs between the places that name it: `make check-workflows`.

gitleaks is pinned in three places that cannot read one another: the Security workflow downloads
it (`GITLEAKS_VERSION`), `make audit` runs its container (`GITLEAKS` in the Makefile), and the
pre-commit hook has its own `rev:`. ruff is pinned in two: the pre-commit hook's `rev:` and the
API's lockfile, which CI's lint uses. Dependabot watches none of the hooks (the owner's choice of
2026-11-11), so a bump by hand that misses one is caught here, naming the files. Standard library
only; needs Python 3.10 or newer (the Makefile runs it with 3.13); run from anywhere.

    python3 scripts/check_tool_versions.py
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# (file, what it names, the pattern whose first group is the version), for gitleaks
GITLEAKS_SOURCES = (
    (
        ".github/workflows/security.yml",
        "GITLEAKS_VERSION",
        re.compile(r"^\s*GITLEAKS_VERSION:\s*v?(\d+(?:\.\d+)+)\s*$", re.MULTILINE),
    ),
    (
        "Makefile",
        "GITLEAKS",
        re.compile(r"^GITLEAKS\s*:?=\s*\S*gitleaks:v?(\d+(?:\.\d+)+)\s*$", re.MULTILINE),
    ),
    (
        ".pre-commit-config.yaml",
        "the gitleaks hook's rev",
        re.compile(
            r"repo:\s*https://github\.com/gitleaks/gitleaks\s*\n\s*rev:\s*v?(\d+(?:\.\d+)+)",
        ),
    ),
)


# The same, for ruff.
RUFF_SOURCES = (
    (
        ".pre-commit-config.yaml",
        "the ruff hook's rev",
        re.compile(
            r"repo:\s*https://github\.com/astral-sh/ruff-pre-commit\s*\n\s*rev:\s*v?(\d+(?:\.\d+)+)",
        ),
    ),
    (
        "apps/api/uv.lock",
        "ruff in the API's lockfile",
        re.compile(r'^name = "ruff"\nversion = "(\d+(?:\.\d+)+)"$', re.MULTILINE),
    ),
)

TOOLS = {"gitleaks": GITLEAKS_SOURCES, "ruff": RUFF_SOURCES}


def version_in(text: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def problems_in(versions: dict[str, str | None], tool: str) -> list[str]:
    """`versions` maps each file to the version of `tool` found in it, or None when none was."""
    problems = [f"{file}: no {tool} version found" for file, found in versions.items() if not found]
    found = {file: version for file, version in versions.items() if version}
    if len(set(found.values())) > 1:
        listing = ", ".join(f"{file} has {version}" for file, version in found.items())
        problems.append(f"{tool} versions differ: {listing}")
    return problems


def main(root: Path = REPO) -> int:
    problems: list[str] = []
    agreed: list[str] = []
    for tool, sources in TOOLS.items():
        versions = {
            file: version_in((root / file).read_text(), pattern) for file, _name, pattern in sources
        }
        found = problems_in(versions, tool)
        problems += found
        if not found:
            agreed.append(f"{tool} {next(iter(versions.values()))} in all {len(versions)} places")
    if problems:
        print("check_tool_versions FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("; ".join(agreed) + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
