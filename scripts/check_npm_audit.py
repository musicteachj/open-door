"""Fail on a high or critical npm advisory, except the dated exceptions below: the Security
workflow's web audit and `make audit`.

`npm audit --audit-level=high` can't accept one advisory, so both run `npm audit --json` and pass
the report here, with the lockfile. Every high or critical advisory fails the check, as before,
unless it is listed in `ACCEPTED` for that package, at no more than the agreed severity, before the
exception's last day has passed; an exception for build tools only also needs every installed copy
of the package to be a dev dependency in the lockfile, so it can't cover a production dependency
(the lockfile can't tell whether a build bundles a dev dependency into the app; this one doesn't).
An advisory whose severity is missing or unknown fails, as worse than critical.
An exception that no longer holds fails, so it is looked at again; one whose advisory is no longer
reported at high or critical is noted, so it gets removed. A report that isn't a whole audit (a
registry error, an empty file, a package whose advisory is missing) fails. Standard library only;
needs Python 3.11 or newer (CI's runner has 3.12, `make audit` uses 3.13); run from anywhere.

    cd apps/web; npm audit --json > report.json
    uv run --no-project --python 3.13 ../../scripts/check_npm_audit.py report.json package-lock.json
"""

import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

SEVERITIES = ("info", "low", "moderate", "high", "critical")
# Only these pass on their own; a severity npm leaves out or names otherwise fails, as worse.
PASSING = SEVERITIES[: SEVERITIES.index("high")]
FAILING = SEVERITIES[SEVERITIES.index("high") :]
GHSA = re.compile(r"GHSA(?:-[0-9a-z]{4}){3}")
UNUSABLE = "The npm audit report is unusable: it is not a whole audit."


@dataclass(frozen=True)
class Accepted:
    advisory: str
    package: str
    # The severity agreed to; the advisory raised above it fails again.
    severity: str
    # The last day the exception holds: the check fails from the day after.
    until: date
    reason: str
    # Accepted because only build and test tools use the package: every installed copy must be a
    # dev dependency in the lockfile.
    build_only: bool


ACCEPTED: tuple[Accepted, ...] = (
    Accepted(
        advisory="GHSA-fc5q-39xc-vjpf",
        package="picomatch",
        severity="high",
        until=date(2027, 1, 17),
        reason=(
            "A ReDoS in picomatch's extglob matching. On 2026-11-17 the advisory was widened to "
            "every version up to 4.0.7, the latest, with no fixed release (still none on "
            "2026-11-17, when the owner extended this to 2027-01-17). Only build and test "
            "tools use picomatch (Vite, Vitest, Orval): the shipped app has none, and the globs "
            "they match come from the repository's own config, not from visitors."
        ),
        build_only=True,
    ),
)


@dataclass(frozen=True)
class Found:
    advisory: str
    package: str
    severity: str
    title: str


def advisories_in(vulnerabilities: dict[str, object]) -> list[Found] | None:
    """Each advisory the report names once, in order; None for a report that isn't whole."""
    found: dict[tuple[str, ...], Found] = {}
    for entry in vulnerabilities.values():
        if not isinstance(entry, dict) or not isinstance(entry.get("via"), list):
            return None
        for via in entry["via"]:
            # A string names the package the advisory came through, whose own entry must be in
            # the report; only a mapping is an advisory.
            if isinstance(via, str):
                if via not in vulnerabilities:
                    return None
                continue
            if not isinstance(via, dict):
                return None
            package = str(via.get("name", ""))
            title = str(via.get("title", ""))
            match = GHSA.search(str(via.get("url", "")))
            source = via.get("source")
            if match:
                advisory, key = match.group(0), (match.group(0), package)
            elif source is not None:
                advisory = f"npm advisory {source}"
                key = (advisory, package)
            else:
                # No id to tell two apart: the title does, so neither hides the other.
                advisory = "an npm advisory with no id"
                key = (advisory, package, title)
            item = Found(advisory, package, str(via.get("severity", "")), title)
            # Reported more than once (through different entries): the highest severity counts.
            if key not in found or rank(item.severity) > rank(found[key].severity):
                found[key] = item
    return list(found.values())


def rank(severity: str) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES)


def not_build_only(
    package: str, vulnerabilities: dict[str, object], lockfile: object
) -> str | None:
    """Why the package may be a production dependency, or None when every installed copy is a
    dev dependency."""
    if not isinstance(lockfile, dict) or not isinstance(lockfile.get("packages"), dict):
        return "no lockfile to check it against"
    entry = vulnerabilities.get(package)
    nodes = entry.get("nodes") if isinstance(entry, dict) else None
    if not isinstance(nodes, list) or not nodes:
        return "the report names no install path for it"
    for node in nodes:
        installed = lockfile["packages"].get(node)
        if not isinstance(installed, dict):
            return f"{node} is not in the lockfile"
        if installed.get("dev") is not True:
            return f"{node} is not a dev dependency"
    return None


def problems_in(
    report: object,
    today: date,
    accepted: tuple[Accepted, ...] = ACCEPTED,
    lockfile: object = None,
) -> tuple[list[str], list[str]]:
    """What fails the check, and what is only said."""
    # npm's audit report since npm 7 says its version; anything else isn't one, however it looks.
    if not isinstance(report, dict) or "error" in report or report.get("auditReportVersion") != 2:
        return [UNUSABLE], []
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return [UNUSABLE], []
    # The report counts its own entries; a different number means one is missing (or added).
    metadata = report.get("metadata")
    counts = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    total = counts.get("total") if isinstance(counts, dict) else None
    if type(total) is not int or total != len(vulnerabilities):
        return [UNUSABLE], []
    found = advisories_in(vulnerabilities)
    if found is None:
        return [UNUSABLE], []
    problems: list[str] = []
    notes: list[str] = []
    for item in found:
        if item.severity in PASSING:
            continue
        label = f"{item.advisory} ({item.package}, {item.severity})"
        exception = next(
            (a for a in accepted if (a.advisory, a.package) == (item.advisory, item.package)),
            None,
        )
        if exception is None:
            problems.append(f"{label}: {item.title}")
            continue
        if rank(item.severity) > rank(exception.severity):
            problems.append(f"{label}: accepted only at {exception.severity}; look at it again")
        elif today > exception.until:
            problems.append(f"{label}: its exception ended on {exception.until.isoformat()}")
        elif exception.build_only and (
            why := not_build_only(item.package, vulnerabilities, lockfile)
        ):
            problems.append(f"{label}: accepted for build tools only, but {why}")
        else:
            notes.append(f"{label}: accepted until {exception.until.isoformat()}")
    # Reported at a severity that fails: one lowered below high needs its exception no more.
    reported = {(item.advisory, item.package) for item in found if item.severity not in PASSING}
    for exception in accepted:
        if (exception.advisory, exception.package) not in reported:
            notes.append(
                f"{exception.advisory} ({exception.package}): no longer reported at high or "
                "critical; remove its exception"
            )
    return problems, notes


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: check_npm_audit.py <npm audit --json report> <package-lock.json>",
            file=sys.stderr,
        )
        return 2
    try:
        report = json.loads(Path(argv[0]).read_text())
        lockfile = json.loads(Path(argv[1]).read_text())
    except (OSError, ValueError) as error:
        print(f"The npm audit report or the lockfile is unusable: {error}", file=sys.stderr)
        return 1
    # An exception's date is a UTC day, as CI's clock is.
    problems, notes = problems_in(report, datetime.now(UTC).date(), ACCEPTED, lockfile)
    for note in notes:
        print(note)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(
            "Fix the advisories above, or, if none can be fixed yet, add a dated exception to "
            "scripts/check_npm_audit.py with the owner's agreement.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
