"""Fail when the gitleaks version differs between the places that name it: `make check-workflows`.

gitleaks is pinned in three places that cannot read one another: the Security workflow downloads
it (`GITLEAKS_VERSION`), `make audit` runs its container (`GITLEAKS` in the Makefile), and the
pre-commit hook has its own `rev:`. Dependabot cannot bump the first two, so a bump by hand that
misses one is caught here, naming the files. Standard library only; needs Python 3.10 or newer
(the Makefile runs it with 3.13); run from anywhere.

    python3 scripts/check_tool_versions.py
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# (file, what it names, the pattern whose first group is the version)
SOURCES = (
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


def version_in(text: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def problems_in(versions: dict[str, str | None]) -> list[str]:
    """`versions` maps each file to the version found in it, or None when none was found."""
    problems = [
        f"{file}: no gitleaks version found" for file, found in versions.items() if not found
    ]
    found = {file: version for file, version in versions.items() if version}
    if len(set(found.values())) > 1:
        listing = ", ".join(f"{file} has {version}" for file, version in found.items())
        problems.append(f"gitleaks versions differ: {listing}")
    return problems


def main(root: Path = REPO) -> int:
    versions = {
        file: version_in((root / file).read_text(), pattern) for file, _name, pattern in SOURCES
    }
    problems = problems_in(versions)
    if problems:
        print("check_tool_versions FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"gitleaks {next(iter(versions.values()))} in all {len(versions)} places.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
